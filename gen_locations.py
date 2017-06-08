import json
import time

import requests


mappings = requests.get('http://firefly.ukcod.org.uk/~mark/ynr-post-mapping.json').json()
post_id_lookup = {m['old']: m['new'] for m in mappings}

mapit_ids = requests.get('https://mapit.mysociety.org/areas/WMC').json().keys()
locations = {}
for mapit_id in mapit_ids:
    time.sleep(0.5)
    j = requests.get('http://mapit.mysociety.org/area/%s/geometry' % mapit_id).json()
    if 'centre_lat' in j:
        post_id = post_id_lookup[mapit_id]
        locations[post_id] = (j['centre_lat'], j['centre_lon'])

with open('locations.json', 'w') as f:
    json.dump(locations, f)
