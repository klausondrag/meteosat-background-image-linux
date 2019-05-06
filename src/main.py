import subprocess
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import click
import requests
from bs4 import BeautifulSoup

click.option = partial(click.option, show_default=True)

BASE_URL = 'http://www.sat.dundee.ac.uk/xrit/000.0E/MSG'
BASE_DIR = Path('~/.config/i3/images/').expanduser()


@click.command()
@click.option('-mt', '--max-tries', default=2)
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
def main(max_tries: int, use_grid: bool):
    grid_text = '_grid' if use_grid else ''
    current_date = datetime.now()
    current_try = 1
    has_successful_request = False
    while current_try <= max_tries and not has_successful_request:
        overview_url = (
            f'{BASE_URL}/{current_date.year}/{current_date.month}/{current_date.day}/'
        )
        print('Getting overview from URL: ', overview_url)
        overview_response = requests.get(overview_url)
        has_successful_request = overview_response.ok
        if not overview_response.ok:
            print('Bad response: ', overview_response)
            current_try += 1
            current_date -= timedelta(days=1)
            continue

        soup = BeautifulSoup(overview_response.text, 'html.parser')
        last_upload_hour = soup('tr')[-2]
        last_upload_hour = last_upload_hour('a')[0].text
        # remove trailing slash
        last_upload_hour = last_upload_hour[:-1]

        # http://www.sat.dundee.ac.uk/xrit/000.0E/MSG/2019/5/5/2200/2019_5_5_2200_MSG4_16_S1_grid.jpeg
        file_name = (
            f'{current_date.year}_{current_date.month}_{current_date.day}_{last_upload_hour}'
            + f'_MSG4_16_S1{grid_text}.jpeg'
        )
        # no slash between overview_url and last_upload_hour because it's already in overview_url
        image_url = f'{overview_url}{last_upload_hour}/{file_name}'

        print('Getting image from URL: ', image_url)
        image_response = requests.get(image_url)
        has_successful_request = image_response.ok
        if not image_response.ok:
            print('Bad response: ', image_response)
            current_try += 1
            current_date -= timedelta(days=1)
            continue

    if not has_successful_request:
        print('No image has been successfully downloaded.')
        exit(1)

    current_image_path = str(BASE_DIR / 'current.jpeg')
    print('Saving image to: ', current_image_path)
    with open(current_image_path, 'wb') as f:
        f.write(image_response.content)

    current_text_path = str(BASE_DIR / 'current.txt')
    print(f'Writing newest filename {file_name} into {current_text_path }')
    with open(current_text_path, 'w') as f:
        f.write(file_name)

    subprocess.run(['feh', '--bg-max', current_image_path])


if __name__ == '__main__':
    main()
