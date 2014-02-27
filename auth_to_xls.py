import argparse
import requests
import xlwt
from wikia_authority import MinMaxScaler
from nlp_services.caching import use_caching
from nlp_services.authority import WikiAuthorityService, WikiTopicsToAuthorityService, WikiAuthorTopicAuthorityService
from nlp_services.authority import WikiAuthorsToIdsService


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wiki-id', dest="wiki_id", required=True,
                    help="The ID of the wiki ")
    ap.add_argument('--num_processes', dest="num_processes", default=96,
                    help="Number of processes to run to compute this shiz")
    return ap.parse_args()


def load_title_list_for_wiki(wiki_url, limit=5000, offset=0, max_pages=None):
    results = requests.get("%sapi/v1/Articles/List" % wiki_url,
                           params={'limit': limit, 'offset': offset, 'namespaces': 0}).json()
    items = results.get('items', [])
    if len(items) < limit or limit+offset > max_pages:
        return items
    else:
        return items + load_title_list_for_wiki(wiki_url, limit=limit, offset=offset+limit)


def get_api_data(wiki_id):
    return requests.get('http://www.wikia.com/api/v1/Wikis/Details',
                        params=dict(ids=wiki_id)).json()['items'][wiki_id]


def get_page_authority(api_data):
    num_pages = api_data['stats']['articles']
    print "Getting Title Data for %d Pages" % num_pages
    page_ids_to_title = {}
    for obj in load_title_list_for_wiki(api_data['url'], max_pages=num_pages):
        page_ids_to_title[obj['id']] = obj['title']

    print "Getting Authority Data"
    authority_data = WikiAuthorityService().get_value(str(api_data['id']))

    print "Cross-Referencing Authority Data"
    return sorted([(page_ids_to_title[int(z[0].split('_')[-1])], z[1])
                   for z in authority_data.items() if int(z[0].split('_')[-1]) in page_ids_to_title],
                  key=lambda y: y[1], reverse=True)


def get_author_authority(api_data):
    topic_authority_data = WikiAuthorTopicAuthorityService().get_value(str(api_data['id']))

    authors_to_topics = sorted(topic_authority_data['weighted'].items(),
                               key=lambda y: sum(y[1].values()),
                               reverse=True)

    a2ids = WikiAuthorsToIdsService().get_value(str(api_data['id']))

    authors_dict = dict([(x[0], dict(name=x[0],
                                     total_authority=sum(x[1].values()),
                                     topics=sorted(x[1].items(), key=lambda z: z[1], reverse=True)))
                         for x in authors_to_topics])

    user_strs = [str(a2ids[user]) for user, contribs in authors_to_topics]
    user_api_data = []
    for i in range(0, len(user_strs), 100):
        user_api_data += requests.get(api_data['url']+'/api/v1/User/Details',
                                      params={'ids': ','.join(user_strs[i:i+100]),
                                      'format': 'json'}).json()['items']

    for user_data in user_api_data:
        authors_dict[user_data['name']].update(user_data)
        authors_dict[user_data['name']]['url'] = authors_dict[user_data['name']]['url'][1:]

    author_objects = sorted(authors_dict.values(), key=lambda z: z['total_authority'], reverse=True)
    return author_objects


def main():
    use_caching()
    args = get_args()
    api_data = get_api_data(args.wiki_id)

    workbook = xlwt.Workbook()
    pages_sheet = workbook.add_sheet("Pages by Authority")
    pages_sheet.write(0, 0, "Page")
    pages_sheet.write(0, 1, "Authority")

    print "Getting Page Data..."
    page_authority = get_page_authority(api_data)

    print "Writing Page Data..."
    pages, authorities = zip(*page_authority)
    scaler = MinMaxScaler(authorities, enforced_min=0, enforced_max=100)
    for i, page in enumerate(pages):
        pages_sheet.write(i+1, 0, page)
        pages_sheet.write(i+1, 1, scaler.scale(authorities[i]))

    print "Getting Author and Topic Data..."
    author_authority = get_author_authority(api_data)
    topic_authority = sorted(WikiTopicsToAuthorityService().get_value(args.wiki_id),
                             key=lambda y: y[1]['authority'], reverse=True)

    print "Writing Author Data..."
    authors_sheet = workbook.add_sheet("Authors by Authority")
    authors_sheet.write(0, 0, "Author")
    authors_sheet.write(0, 1, "Authority")

    authors_topics_sheet = workbook.add_sheet("Topics for Best Authors")
    authors_topics_sheet.write(0, 0, "Author")
    authors_topics_sheet.write(0, 1, "Topic")
    authors_topics_sheet.write(0, 2, "Rank")
    authors_topics_sheet.write(0, 3, "Score")

    scaler = MinMaxScaler([author['total_authority'] for author in author_authority], enforced_min=0, enforced_max=100)
    pivot_counter = 1
    for i, author in enumerate(author_authority):
        authors_sheet.write(i+1, 0, author['name'])
        authors_sheet.write(i+1, 1, scaler.scale(author['total_authority']))
        for rank, topic in enumerate(author['topics'][:10]):
            authors_topics_sheet.write(pivot_counter, 0, author['name'])
            authors_topics_sheet.write(pivot_counter, 1, topic[0])
            authors_topics_sheet.write(pivot_counter, 2, rank+1)
            authors_topics_sheet.write(pivot_counter, 3, topic[1])
            pivot_counter += 1

    print "Writing Topic Data"
    topics_sheet = workbook.add_sheet("Topics by Authority")
    topics_sheet.write(0, 0, "Topic")
    topics_sheet.write(0, 1, "Authority")

    topics_authors_sheet = workbook.add_sheet("Authors for Best Topics")
    topics_authors_sheet.write(0, 0, "Topic")
    topics_authors_sheet.write(0, 1, "Author")
    topics_authors_sheet.write(0, 2, "Rank")
    topics_authors_sheet.write(0, 3, "Authority")

    scaler = MinMaxScaler([x[1]['authority'] for x in topic_authority], enforced_min=0, enforced_max=100)
    pivot_counter = 1
    for i, topic in enumerate(topic_authority):
        topics_sheet.write(i+1, 0, topic[0])
        topics_sheet.write(i+1, 1, scaler.scale(topic[1]['authority']))
        authors = topic[1]['authors']
        for rank, author in enumerate(authors[:10]):
            topics_authors_sheet.write(pivot_counter, 0, topic[0])
            topics_authors_sheet.write(pivot_counter, 1, author['author'])
            topics_authors_sheet.write(pivot_counter, 2, rank+1)
            topics_authors_sheet.write(pivot_counter, 3, author['topic_authority'])
            pivot_counter += 1

    print "Saving to Excel"
    workbook.save("%s-authority-data.xls" % args.wiki_id)


if __name__ == '__main__':
    main()