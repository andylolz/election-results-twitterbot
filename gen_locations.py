import time
import requests


mapit_ids = requests.get("http://mapit.mysociety.org/areas/WMC").json().keys()
locations = {}
for mapit_id in mapit_ids:
    time.sleep(0.5)
    j = requests.get("http://mapit.mysociety.org/area/%s/geometry" % mapit_id).json()
    if "centre_lat" in j:
        locations[mapit_id] = (j["centre_lat"], j["centre_lon"])

with open("locations.json", "w") as f:
    json.dump(locations, f)
