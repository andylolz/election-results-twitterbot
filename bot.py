import json
import os
import pickle
import time
import urllib.request

import feedparser
import redis
import requests
from slugify import slugify

import twitter


# Abbreviated party names, for 140 character convenience
PARTY_LOOKUP = {
    'Labour Party': '@UKLabour',
    'Labour and Co-operative Party': '@UKLabour / Co-op',
    'Conservative and Unionist Party': '@Conservatives',
    'Liberal Democrats': '@LibDems',
    'Scottish Green Party': '@TheGreenParty',
    'Green Party': '@TheGreenParty',
    'UK Independence Party (UKIP)': '@UKIP',
    'Democratic Unionist Party - D.U.P.': '@duponline',
    'Scottish National Party (SNP)': '@theSNP',
    'Plaid Cymru - The Party of Wales': '@Plaid_Cymru',
    'SDLP (Social Democratic & Labour Party)': '@SDLPlive',

    'Speaker seeking re-election': 'Speaker',
    'Christian Peoples Alliance': 'CPA',
    'Official Monster Raving Loony Party': 'Raving Loony',
    'Communist League Election Campaign': 'Communist League',
    'Pirate Party UK': 'Pirate Party',
    'Scotland\'s Independence Referendum Party': 'Scots Indy Ref',
    'Independent Save Withybush Save Lives': 'Save Withybush Save Lives',
    'Greater Manchester Homeless Voice': 'Homeless Voice',
    'People Before Profit Alliance': 'People Before Profit',
    'Traditional Unionist Voice - TUV': 'TUV',
    'British National Party': 'BNP',
    'The Socialist Party of Great Britain': 'Socialist Party',
    'Alliance - Alliance Party of Northern Ireland': 'Alliance',
    'Christian Party "Proclaiming Christ\'s Lordship"': 'Christian',
    'Young People\'s Party YPP': 'Young People\'s Party',
    'The Peace Party - Non-violence, Justice, Environment': 'Peace Party',
}

CONSTITUENCY_LOOKUP = {
    'Birmingham, Selly Oak': 'B\'ham Selly Oak',
    'Houghton & Sunderland S': 'Sunderland S',
    'Newcastle upon Tyne N': 'Newcastle N',
    'Stoke-on-Trent Ctl': 'Stoke Ctl',
    'Wyre Forest': 'Wyre',
    'Kingston upon Hull W': 'Kingston on Hull W',
}

PERSON_NAME_LOOKUP = {
    'Michael Andrew Christopher Deem': 'Michael Deem',
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
    return constituency.replace(' and ', ' & ')

# fetch locations (for geopositioning tweets)
with open('locations.json') as f:
    locations = json.load(f)

# print('fetching redis ...')
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url)

def delete_old_tweet(tw, tweeted):
    print('delete old tweet: {}'.format(tweeted['tweet_id']))
    tw.delete(tweeted['tweet_id'])
    if tweeted['twitter_handle']:
        print('remove old twitter handle: @{}'.format(tweeted['twitter_handle']))
        _ = tw.remove_from_list(os.getenv('TWITTER_LIST_ID'), tweeted['twitter_handle'])

def parse_feed():
    # print('fetching results feed ...')
    ge2017_slug = 'parl.2017-06-08'
    # I can't remember why this is correct
    max_tweet_length = 91
    feed = feedparser.parse('https://candidates.democracyclub.org.uk/results/all.atom')

    api_tmpl = 'https://candidates.democracyclub.org.uk/api/v0.9/persons/{}/?format=json'
    status_tmpl = '{constituency_name}! Your MP is: {person_name} ({party_name}) https://whocanivotefor.co.uk/person/{person_id}/{slug}{twitter_str} #GE2017'
    test_status_tmpl = '{constituency_name}! Your MP is: {person_name} ({party_name}){twitter_str} #GE2017'

    winners = {item['post_id']: item['winner_person_id'] for item in feed.entries if item['election_slug'] == ge2017_slug and item['retraction'] != '1'}

    # log in
    tw = twitter.TwitterAPI()

    for item in feed.entries:
        kw = {}
        if item['election_slug'] != ge2017_slug:
            continue
        if item['retraction'] == '1':
            tweeted = db.get(post_id)
            if tweeted:
                tweeted = pickle.loads(tweeted)
                if tweeted['person_id'] == winners.get(post_id):
                    delete_old_tweet(tw, tweeted)
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
                delete_old_tweet(tw, tweeted)

        person = requests.get(api_tmpl.format(person_id)).json()

        thumbnail_url = person.get('thumbnail')
        if thumbnail_url:
            kw['filename'] = thumbnail_url.rsplit('/', 1)[1]
            # fetch the image
            urllib.request.urlretrieve(thumbnail_url, kw['filename'])

        # cc the candidate (if they're on twitter)
        twitter_handle = person['versions'][0]['data'].get('twitter_username')
        if twitter_handle:
            _ = tw.add_to_list(os.getenv('TWITTER_LIST_ID'), twitter_handle)

        # compose the tweet
        constituency_name = abbrev_constituency(item['post_name'])
        party_name = abbrev_party(item['winner_party_name'])
        person_name = item['winner_person_name']
        tb = {
            'twitter_str': ' @{}'.format(twitter_handle) if twitter_handle else '',
            'constituency_name': constituency_name,
            'party_name': party_name,
            'person_name': person_name,
        }

        test_status = test_status_tmpl.format(**tb)
        if len(test_status) > max_tweet_length:
            constituency_name = constituency_name.replace('East ', 'E ').replace(' East', ' E')
            constituency_name = constituency_name.replace('West ', 'W ').replace(' West', ' W')
            constituency_name = constituency_name.replace('North ', 'N ').replace(' North', ' N')
            constituency_name = constituency_name.replace('South ', 'S ').replace(' South', ' S')
            constituency_name = constituency_name.replace('Central ', 'Ctl ').replace(' Central', ' Ctl')
            tb['constituency_name'] = constituency_name

        test_status = test_status_tmpl.format(**tb)
        if len(test_status) > max_tweet_length:
            constituency_name = CONSTITUENCY_LOOKUP.get(constituency_name, constituency_name)
            tb['constituency_name'] = constituency_name

        test_status = test_status_tmpl.format(**tb)
        if len(test_status) > max_tweet_length:
            constituency_name = constituency_name.split(',')[0].split(' & ')[0]
            tb['constituency_name'] = constituency_name

        test_status = test_status_tmpl.format(**tb)
        if len(test_status) > max_tweet_length:
            person_name = PERSON_NAME_LOOKUP.get(person_name, person_name)
            tb['person_name'] = person_name

        tb['person_id'] = person_id
        tb['slug'] = slugify(person_name)
        kw['status'] = status_tmpl.format(**tb)

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
