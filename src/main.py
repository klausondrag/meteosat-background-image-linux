from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

MAX_RETRIES = 3
USE_GRID = True
BASE_URL = 'http://www.sat.dundee.ac.uk/xrit/000.0E/MSG'
grid_text = '_grid' if USE_GRID else ''

current_date = datetime.now()
current_try = 1
has_successful_request = False
while current_try <= MAX_RETRIES and not has_successful_request:
    overview_url = (
        f'{BASE_URL}/{current_date.year}/{current_date.month}/{current_date.day}/'
    )
    r = requests.get(overview_url)
    current_try += 1
    has_successful_request = r.ok
    if not r.ok:
        current_date -= timedelta(days=1)

if not has_successful_request:
    exit(1)

soup = BeautifulSoup(r.text)
last_upload_hour = soup('tr')[-2]
last_upload_hour = last_upload_hour('a')[0].text
# remove trailing slash
last_upload_hour = last_upload_hour[:-1]

# http://www.sat.dundee.ac.uk/xrit/000.0E/MSG/2019/5/5/2200/2019_5_5_2200_MSG4_16_S4_grid.jpeg
file_name = (
    f'{current_date.year}_{current_date.month}_{current_date.day}_{last_upload_hour}'
    + f'_MSG4_16_S4{grid_text}.jpeg'
)
# no slash between overview_url and last_upload_hour because it's already in overview_url
image_url = f'{overview_url}{last_upload_hour}/{file_name}'

r = requests.get(image_url)
r.raise_for_status()

with open('current.jpeg', 'wb') as f:
    f.write(r.content)
with open(file_name, 'wb') as f:
    f.write(r.content)
