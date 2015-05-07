# -*- coding: utf-8 -*-
import csv
import re
import os
import time
import json
import pickle
import urllib
import sys

import feedparser
import requests
import twitter
import redis
from slugify import slugify


# Abbreviated party names, for 140 character convenience
PARTY_LOOKUP = {
    "Labour Party": "#Labour",
    "Labour and Co-operative Party": "#Labour / Co-op",
    "Conservative Party": "#Conservative",
    "Liberal Democrats": "#LibDems",
    "Scottish Green Party": "#Greens",
    "Green Party": "#Greens",
    "UK Independence Party (UK I P)": "#UKIP",
    "UK Independence Party (UKIP)": "#UKIP",
    "Democratic Unionist Party - D.U.P.": "#DUP",
    "Scottish National Party (SNP)": "#SNP",
    "Plaid Cymru - The Party of Wales": "#Plaid15",
    "SDLP (Social Democratic & Labour Party)": "#SDLP",
    "The Respect Party": "#RespectParty",

    "Traditional Unionist Voice - TUV": "TUV",
    "The Eccentric Party of Great Britain": "Eccentric Party",
    "British National Party": "BNP",
    "The Socialist Party of Great Britain": "Socialist Party",
    "Alliance - Alliance Party of Northern Ireland": "Alliance",
    "Pirate Party UK": "Pirate Party",
    "Alter Change - Politics. Only Different": "Alter Change",
    "Christian Party \"Proclaiming Christ's Lordship\"": "Christian",
    "Lincolnshire Independents Lincolnshire First": "Lincolnshire Ind.",
    "An Independence from Europe": "Independence from Europe",
    "People First - Gwerin Gyntaf": "People First",
    "Mebyon Kernow - The Party for Cornwall": "Mebyon Kernow",
    "Communist Party of Britain": "Communist",
    "Speaker seeking re-election": "Speaker",
    "Liberty Great Britain": "Liberty GB",
    "National Liberal Party - True Liberalism": "National Liberal",
    "Official Monster Raving Loony Party": "Raving Loony",
    "Trade Unionist and Socialist Coalition": "TUSC",
    "Young People's Party YPP": "Young People's Party",
    "Communist League Election Campaign": "Communist League",
    "The Peace Party - Non-violence, Justice, Environment": "Peace Party",
    "Left Unity - Trade Unionists and Socialists": "Left Unity / TUSC",
    "Cannabis is Safer than Alcohol": "CISTA",
    "Magna Carta Conservation Party Great Britain": "Magna Carta Conservation",
    "Christian Peoples Alliance": "CPA",
    "Restore the Family For Children's Sake": "Restore the Family",
    "Red Flag - Anti-Corruption": "Red Flag",
    "Al-Zebabist Nation of Ooog": "Ooog",
    "Children of the Atom": "Atom",
    "Bournemouth Independent Alliance": "BIA",
}

CONSTITUENCY_LOOKUP = {
    "Caithness, Sutherland and Easter Ross": "Caithness",
    "Cumbernauld, Kilsyth and Kirkintilloch East": "Cumbernauld",
    "East Kilbride, Strathaven and Lesmahagow": "East Kilbride",
    "Dumfriesshire, Clydesdale and Tweeddale": "Dumfriesshire",
    "Inverness, Nairn, Badenoch and Strathspey": "Inverness",
    "Middlesbrough South and East Cleveland": "Middlesbrough South",
    "Dumfriesshire, Clydesdale and Tweeddale": "Dumfriesshire",
    "Normanton, Pontefract and Castleford": "Normanton",
}

# Abbreviate party names, using lookup and other hacks
def abbrev_party(party):
    if party in PARTY_LOOKUP:
        return PARTY_LOOKUP[party]
    if party.endswith(" Party"):
        party = party[:-6]
    if party.startswith("The "):
        party = party[4:]
    return party

def abbrev_constituency(constituency):
    constituency = CONSTITUENCY_LOOKUP.get(constituency, constituency)
    return constituency.replace(u' and ', u' & ')

# fetch locations (for geopositioning tweets)
with open("locations.json") as f:
    locations = json.load(f)

# print "fetching redis ..."
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
r = redis.from_url(redis_url)

def parse_feed():
    # print "fetching results feed ..."
    feed = feedparser.parse(os.getenv('FEED_URL'))

    api_tmpl = "http://yournextmp.popit.mysociety.org/api/v0.1/persons/{}"
    status_tmpl = u"{constituency}! #YourNextMP is: {person_name} ({party}) https://yournextmp.com/person/{person_id}/{slug}{twitter_str}"

    # log in
    t = twitter.TwitterAPI()

    for item in feed.entries:
        tweeted = r.get(item['post_id'])
        if tweeted:
            tweeted = pickle.loads(tweeted)
            if tweeted['published_at'] >= item['published']:
                # we've already tweeted this
                continue
            else:
                print "delete old tweet: {}".format(tweeted['tweet_id'])
                t.delete(tweeted['tweet_id'])
                if tweeted['twitter_handle']:
                    print "remove old twitter handle: @{}".format(tweeted['twitter_handle'])
                    _ = t.remove_from_list(os.getenv('TWITTER_LIST_ID'), tweeted['twitter_handle'])
        kw = {}
        id_ = item['winner_popit_person_id']
        person = requests.get(api_tmpl.format(id_), verify=False).json()['result']

        if person.get('proxy_image'):
            kw['filename'] = "{}.png".format(id_)
            # fetch the image
            urllib.urlretrieve("{}/200/0".format(person['proxy_image']), kw['filename'])

        # cc the candidate (if they're on twitter)
        twitter_handle = person['versions'][0]['data'].get('twitter_username')
        twitter_str = " @{}".format(twitter_handle) if twitter_handle else ""
        if twitter_handle:
            _ = t.add_to_list(os.getenv('TWITTER_LIST_ID'), twitter_handle)

        # compose the tweet
        constituency = abbrev_constituency(person['standing_in']['2015']['name'])
        party = abbrev_party(person['party_memberships']['2015']['name'])
        kw['status'] = status_tmpl.format(constituency=constituency, person_name=person['name'], party=party, person_id=id_, twitter_str=twitter_str, slug=slugify(person['name']))

        # add a location if we have one
        post_id = person['standing_in']['2015']['post_id']
        l = locations[post_id] if post_id in locations else None
        if l:
            kw['lat'], kw['long'] = l

        # Send a tweet here!
        print "Tweeting:", kw
        tweet = t.tweet(**kw)

        # Save the tweet to redis
        r.set(item['post_id'], pickle.dumps({
            "published_at": item['published'],
            "tweet_id": tweet.id,
            "twitter_handle": twitter_handle,
        }))

        if kw.get('filename'):
            # Delete the downloaded image
            os.remove(kw['filename'])

        time.sleep(1)

while True:
    print "Working ..."
    parse_feed()
    print "Sleeping ..."
    time.sleep(60)
