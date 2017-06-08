import feedparser


url = 'https://candidates.democracyclub.org.uk/results/all.atom'
feed = feedparser.parse(url)

entries = {x['post_id']: x for x in feed.entries}.values()

results = {}
for x in entries:
    if x['winner_party_name'] not in results:
        results[x['winner_party_name']] = 0
    results[x['winner_party_name']] += 1

for x, y in results.items():
    print(x, y)

print(len(entries))
