# -*- coding: utf-8 -*-
import csv
import re
import os
import time
import json
import urllib
import sys

import requests

import twitter


party_lookup = {
    "Traditional Unionist Voice - TUV": "TUV",
    "Democratic Unionist Party - D.U.P.": "DUP",
    "British National Party": "BNP",
    "The Socialist Party of Great Britain": "Socialist Party",
    "Alliance - Alliance Party of Northern Ireland": "Alliance",
    "Pirate Party UK": "Pirate Party",
    "UK Independence Party (UK I P)": "UKIP",
    "Alter Change - Politics. Only Different": "Alter Change",
    "Christian Party \"Proclaiming Christ's Lordship\"": "Christian Party",
    "Scottish National Party (SNP)": "SNP",
    "Lincolnshire Independents Lincolnshire First": "Lincolnshire Independents",
    "Plaid Cymru - The Party of Wales": "Plaid Cymru",
    "An Independence from Europe": "Independence from Europe",
    "People First - Gwerin Gyntaf": "People First",
    "Mebyon Kernow - The Party for Cornwall": "Mebyon Kernow",
    "Communist Party of Britain": "Communist",
    "Speaker seeking re-election": "",
    "Liberty Great Britain": "Liberty GB",
    "UK Independence Party (UKIP)": "UKIP",
    "National Liberal Party - True Liberalism": "National Liberal",
    "Official Monster Raving Loony Party": "Monster Raving Loony",
    "SDLP (Social Democratic & Labour Party)": "SDLP",
    "Trade Unionist and Socialist Coalition": "TUSC",
    "Young People's Party YPP": "Young People's Party",
    "Communist League Election Campaign": "Communist League",
    "The Peace Party - Non-violence, Justice, Environment": "Peace Party",
}

def abbrev_party(party):
    if party in party_lookup:
        return party_lookup[party]
    if party.endswith(" Party"):
        party = party[:-6]
    if party.startswith("The "):
        party = party[4:]
    return party

with open("locations.json") as f:
    locations = json.load(f)

t = twitter.TwitterAPI()

# fetch all URLs tweeted
page = 1
urls = []
while True:
    timeline = t.timeline(page=page)
    if timeline == []:
        break
    urls = urls + [x.entities['urls'][0]['expanded_url'] for x in timeline if len(x.entities['urls']) > 0]
    page += 1

# figure out the CVs we've already tweeted about
tweeted = {int(url.split("/")[-1]): None for url in urls if re.match(r"^https?://cv.democracyclub.org.uk/show_cv/(\d+)$", url)}.keys()

# fetch all CVs collected
j = requests.get("http://cv.democracyclub.org.uk/cvs.json").json()
person_ids = [x["person_id"] for x in reversed(j) if x["has_thumb"]]
cvs = {x["person_id"]: x for x in j}

status_tmpl = u"{name}’{s} CV ({party}, {constituency}) {cv_url}{twitter}"
cv_tmpl = "http://cv.democracyclub.org.uk/show_cv/%d"

candidates = None

if len(sys.args) > 1:
    person_ids = [sys.argv[1]]

for person_id in person_ids:
    if person_id in tweeted:
        continue

    if candidates is None:
        urllib.urlretrieve("https://yournextmp.com/media/candidates.csv", "candidates.csv")
        with open("candidates.csv") as f:
            c = csv.DictReader(f)
            candidates = {int(row["id"]): row for row in c}
    else:
        time.sleep(60)

    image_filename = "%d.jpg" % person_id
    urllib.urlretrieve(cvs[person_id]["thumb"]["url"], image_filename)

    c = candidates[person_id]
    if c["twitter_username"] != "":
        c["twitter_username"] = " /cc @%s" % c["twitter_username"]

    cv_url = cv_tmpl % person_id
    s = "s" if c["name"][-1] != "s" else ""
    status = status_tmpl.format(name=c["name"].decode("utf-8"), party=abbrev_party(c["party"]).decode("utf-8"), constituency=c["constituency"].decode("utf-8"), cv_url=cv_url, s=s, twitter=c["twitter_username"])

    kw = {
        "status": status,
        "filename": image_filename,
    }

    l = locations[c["mapit_id"]] if c["mapit_id"] in locations else None
    if l:
        kw["lat"], kw["long"] = l

    print kw

    #Send a tweet here!
    t.tweet(**kw)

    os.remove(image_filename)
