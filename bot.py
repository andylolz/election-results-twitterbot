import json
import os
import pickle
import time
import urllib

import feedparser
import redis
import requests
from slugify import slugify

import twitter


# Abbreviated party names, for 140 character convenience
PARTY_LOOKUP = {
    'Labour Party': '#Labour',
    'Labour and Co-operative Party': '#Labour / Co-op',
    'Conservative Party': '#Conservative',
    'Liberal Democrats': '#LibDems',
    'Scottish Green Party': '#Greens',
    'Green Party': '#Greens',
    'UK Independence Party (UK I P)': '#UKIP',
    'UK Independence Party (UKIP)': '#UKIP',
    'Democratic Unionist Party - D.U.P.': '#DUP',
    'Scottish National Party (SNP)': '#SNP',
    'Plaid Cymru - The Party of Wales': '#Plaid15',
    'SDLP (Social Democratic & Labour Party)': '#SDLP',
    'The Respect Party': '#RespectParty',

    'Traditional Unionist Voice - TUV': 'TUV',
    'The Eccentric Party of Great Britain': 'Eccentric Party',
    'British National Party': 'BNP',
    'The Socialist Party of Great Britain': 'Socialist Party',
    'Alliance - Alliance Party of Northern Ireland': 'Alliance',
    'Pirate Party UK': 'Pirate Party',
    'Alter Change - Politics. Only Different': 'Alter Change',
    'Christian Party "Proclaiming Christ\'s Lordship': 'Christian',
    'Lincolnshire Independents Lincolnshire First': 'Lincolnshire Ind.',
    'An Independence from Europe': 'Independence from Europe',
    'People First - Gwerin Gyntaf': 'People First',
    'Mebyon Kernow - The Party for Cornwall': 'Mebyon Kernow',
    'Communist Party of Britain': 'Communist',
    'Speaker seeking re-election': 'Speaker',
    'Liberty Great Britain': 'Liberty GB',
    'National Liberal Party - True Liberalism': 'National Liberal',
    'Official Monster Raving Loony Party': 'Raving Loony',
    'Trade Unionist and Socialist Coalition': 'TUSC',
    'Young People\'s Party YPP': 'Young People\'s Party',
    'Communist League Election Campaign': 'Communist League',
    'The Peace Party - Non-violence, Justice, Environment': 'Peace Party',
    'Left Unity - Trade Unionists and Socialists': 'Left Unity / TUSC',
    'Cannabis is Safer than Alcohol': 'CISTA',
    'Magna Carta Conservation Party Great Britain': 'Magna Carta Conservation',
    'Christian Peoples Alliance': 'CPA',
    'Restore the Family For Children\'s Sake': 'Restore the Family',
    'Red Flag - Anti-Corruption': 'Red Flag',
    'Al-Zebabist Nation of Ooog': 'Ooog',
    'Children of the Atom': 'Atom',
    'Bournemouth Independent Alliance': 'BIA',
}

CONSTITUENCY_LOOKUP = {
    'South Basildon and East Thurrock': 'South Basildon',
    'Carmarthen West and South Pembrokeshire': 'Carmarthen West',
    'Caithness, Sutherland and Easter Ross': 'Caithness',
    'Cumbernauld, Kilsyth and Kirkintilloch East': 'Cumbernauld',
    'East Kilbride, Strathaven and Lesmahagow': 'East Kilbride',
    'Dumfriesshire, Clydesdale and Tweeddale': 'Dumfriesshire',
    'Inverness, Nairn, Badenoch and Strathspey': 'Inverness',
    'Middlesbrough South and East Cleveland': 'Middlesbrough South',
    'Dumfriesshire, Clydesdale and Tweeddale': 'Dumfriesshire',
    'Normanton, Pontefract and Castleford': 'Normanton',
}

# Abbreviate party names, using lookup and other hacks
def abbrev_party(party):
    if party in PARTY_LOOKUP:
        return PARTY_LOOKUP[party]
    if party.endswith(' Party'):
        party = party[:-6]
    if party.startswith('The '):
        party = party[4:]
    return party

def abbrev_constituency(constituency):
    constituency = CONSTITUENCY_LOOKUP.get(constituency, constituency)
    return constituency.replace(' and ', ' & ')

# fetch locations (for geopositioning tweets)
with open('locations.json') as f:
    locations = json.load(f)

# print('fetching redis ...')
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url)

def parse_feed():
    # print('fetching results feed ...')
    ge2017_slug = 'parl.2017-06-08'
    feed = feedparser.parse('https://candidates.democracyclub.org.uk/results/all.atom')

    api_tmpl = 'https://candidates.democracyclub.org.uk/api/v0.9/persons/{}/?format=json'
    status_tmpl = '{constituency}! Your new MP is: {person_name} ({party}) https://whocanivotefor.co.uk/person/{person_id}/{slug}{twitter_str}'

    winners = {item['post_id']: item['winner_person_id'] for item in feed.entries if item['election_slug'] == ge2017_slug and item['retraction'] != '1'}

    # log in
    tw = twitter.TwitterAPI()

    for item in feed.entries:
        if item['election_slug'] != ge2017_slug:
            continue
        if item['retraction'] == '1':
            # TODO: ignoring retractions for now
            continue
        person_id = item['winner_person_id']
        post_id = item['post_id']
        tweeted = db.get(post_id)
        if tweeted:
            tweeted = pickle.loads(tweeted)
            if tweeted['person_id'] == winners.get(post_id):
                # we've already tweeted the winner here
                continue
            else:
                print('delete old tweet: {}'.format(tweeted['tweet_id']))
                tw.delete(tweeted['tweet_id'])
                if tweeted['twitter_handle']:
                    print('remove old twitter handle: @{}'.format(tweeted['twitter_handle']))
                    _ = tw.remove_from_list(os.getenv('TWITTER_LIST_ID'), tweeted['twitter_handle'])
        kw = {}
        person = requests.get(api_tmpl.format(person_id)).json()

        if person.get('thumbnail'):
            thumbnail_url = person.get('thumbnail')
            kw['filename'] = thumbnail_url.rsplit('/', 1)[1]
            # fetch the image
            urllib.urlretrieve(thumbnail_url, kw['filename'])

        # cc the candidate (if they're on twitter)
        twitter_handle = person['versions'][0]['data'].get('twitter_username')
        twitter_str = ' @{}'.format(twitter_handle) if twitter_handle else ''
        if twitter_handle:
            _ = tw.add_to_list(os.getenv('TWITTER_LIST_ID'), twitter_handle)

        # compose the tweet
        constituency_name = abbrev_constituency(item['post_name'])
        party_name = abbrev_party(item['winner_party_name'])
        person_name = item['winner_person_name']

        kw['status'] = status_tmpl.format(
            constituency=constituency_name,
            person_name=person_name,
            party=party_name,
            person_id=person_id,
            twitter_str=twitter_str,
            slug=slugify(person_name)
        )

        # add a location if we have one
        l = locations[post_id] if post_id in locations else None
        if l:
            kw['lat'], kw['long'] = l

        # Send a tweet here!
        print('Tweeting:')
        print(json.dumps(kw, indent=4))
        tweet = tw.tweet(**kw)

        if tweet:
            # Save the tweet to redis
            db.set(post_id, pickle.dumps({
                'person_id': person_id,
                'tweet_id': tweet.id,
                'twitter_handle': twitter_handle,
            }))

        if kw.get('filename'):
            # Delete the downloaded image
            os.remove(kw['filename'])

        time.sleep(1)

while True:
    print('Working ...')
    parse_feed()
    print('Sleeping ...')
    time.sleep(60)
