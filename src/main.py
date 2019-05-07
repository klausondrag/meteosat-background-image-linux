import asyncio
import itertools
import subprocess
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
import click
import imageio
import requests
from tqdm import tqdm

click.option = partial(click.option, show_default=True)

BASE_URL = 'http://www.sat.dundee.ac.uk/xrit/000.0E/MSG'
BASE_DIR = Path('~/.config/i3/images/').expanduser()
SAVE_DIR = Path('~/Pictures/meteosat/').expanduser()
GRID_SAVE_DIR = SAVE_DIR / 'grid'
NO_GRID_SAVE_DIR = SAVE_DIR / 'no_grid'
USE_GRID_TO_DIR = {True: GRID_SAVE_DIR, False: NO_GRID_SAVE_DIR}


@click.group()
def cli():
    pass



@cli.command()
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=False)
def gif(use_grid: bool) -> None:
    image_directory = USE_GRID_TO_DIR[use_grid]
    file_path = SAVE_DIR / f'{image_directory.name}.gif'
    with imageio.get_writer(file_path, mode='I', loop=False) as writer:
        for filename in tqdm(
            sorted(image_directory.glob('*.jpeg'), key=filename_to_int)
        ):
            image = imageio.imread(filename)
            writer.append_data(image)


def filename_to_int(filename: Path, max_hour_length: int = 4) -> int:
    filename = filename.name
    # 01:00 not 13:00
    # 2019_5_5_100_MSG4_16_S1.jpeg

    filename = filename[: find_nth_char(filename)]
    # 2019_5_5_100

    # add left of hour otherwise 01:00 and 10:00 become the same
    hour_start_index = filename.rindex('_') + 1
    zeros_to_add = max_hour_length - (len(filename) - hour_start_index)
    filename = (
        filename[:hour_start_index] + '0' * zeros_to_add + filename[hour_start_index:]
    )
    # 2019_5_5_0100

    filename = filename.replace('_', '')
    filename = int(filename)
    # 2019550100

    return filename


def find_nth_char(s: str, nth_char: int = 4, char: str = '_') -> int:
    counter = 0
    for index, c in enumerate(s):
        if c == char:
            counter += 1
        if counter >= nth_char:
            return index

    return -1


@cli.command()
@click.argument('until-date', type=click.DateTime(formats=['%Y-%m-%d', '%Y-%m-%dT%H']))
@click.option('-ag/-nag', '--all-grids/--not-all-grids', default=True)
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
@click.option('-ncd', '--n-concurrent-downloads', default=5)
def until(
    until_date: datetime, all_grids: bool, use_grid: bool, n_concurrent_downloads: int
) -> None:
    iter_bools = [True, False] if all_grids else [use_grid]
    start_date = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    images_to_download = itertools.product(
        iter_datetimes(start_date, until_date), iter_bools
    )
    images_to_download = [
        construct_from_date(current_date, use_grid=ug)
        for current_date, ug in images_to_download
    ]

    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(run(images_to_download, n_concurrent_downloads))
    loop.run_until_complete(future)


async def run(images_to_download, n_concurrent_downloads):
    tasks = []
    # create instance of Semaphore
    sem = asyncio.Semaphore(n_concurrent_downloads)

    # Create client session that will ensure we dont open new connection
    # per each request.
    async with aiohttp.ClientSession() as session:
        for url, image_path in images_to_download:
            print('Trying image: ', image_path.name)
            if image_path.exists():
                # print('Image already exists at: ', image_path_string)
                print('Skipping downloading.')
            else:
                print('Getting image from URL: ', url)
                task = asyncio.ensure_future(bound_fetch(url, image_path, session, sem))
                tasks.append(task)

        responses = asyncio.gather(*tasks)
        await responses


async def bound_fetch(url, image_path, session, sem):
    async with sem:
        error, image = await fetch(url, session)

        if not error:
            print('Saving image:', image_path.name)
            with open(str(image_path), 'wb') as f:
                f.write(image)


async def fetch(url, session):
    async with session.get(url) as response:
        if response.status != 200:
            print('Bad response:', url, response.status, response.reason)
            return True, None
        else:
            return False, await response.read()


@cli.command()
@click.option('-mt', '--max-tries', default=20)
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
def newest(max_tries: int, use_grid: bool) -> None:
    start_date = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    is_successful = False
    for current_try, current_date in zip(range(max_tries), iter_datetimes(start_date)):
        url, image_path = construct_from_date(current_date, use_grid)
        is_successful = download_maybe(url, image_path)
        if is_successful:
            break
        else:
            continue

    if not is_successful:
        print('No image has been successfully downloaded.')
        exit(1)

    set_background(image_path)


def iter_datetimes(start_date: datetime, until_date: Optional[datetime] = None):
    current_date = start_date
    while until_date is None or current_date >= until_date:
        yield current_date
        current_date -= timedelta(hours=1)


def construct_from_date(current_date, use_grid: bool) -> Tuple[str, Path]:
    grid_text = '_grid' if use_grid else ''

    overview_url = (
        f'{BASE_URL}/{current_date.year}/{current_date.month}/{current_date.day}'
    )
    server_hour_string = get_server_hour_string(current_date.hour)
    server_filename = get_filename(current_date, server_hour_string, grid_text)
    url = f'{overview_url}/{server_hour_string}/{server_filename}'

    local_hour_string = get_local_hour_string(current_date.hour)
    local_filename = get_filename(current_date, local_hour_string, grid_text)
    image_path = SAVE_DIR / USE_GRID_TO_DIR[use_grid] / local_filename
    image_path.parent.mkdir(parents=True, exist_ok=True)

    return url, image_path


def get_server_hour_string(hour: int) -> str:
    if hour == 0:
        return '0'
    else:
        return f'{hour}00'


def get_local_hour_string(hour: int) -> str:
    if hour == 0:
        return '0'
    elif 1 < hour <= 9:
        return f'0{hour}00'
    else:
        return f'{hour}00'


def get_filename(current_date: datetime, hour_string: str, grid_text) -> str:
    return (
        f'{current_date.year}_{current_date.month}_{current_date.day}_{hour_string}'
        + f'_MSG4_16_S1{grid_text}.jpeg'
    )


def download_maybe(url: str, image_path: Path) -> bool:
    print('Trying image: ', image_path.name)
    image_path_string = str(image_path)
    if image_path.exists():
        # print('Image already exists at: ', image_path_string)
        print('Skipping downloading.')
        is_successful = True
    else:
        print('Getting image from URL: ', url)
        response = requests.get(url)
        if response.ok:
            print('Saving image: ', image_path_string)
            with open(image_path_string, 'wb') as f:
                f.write(response.content)
            is_successful = True
        else:
            print('Bad response: ', response)
            is_successful = False
    return is_successful


def set_background(image_path: Path) -> None:
    print('Calling feh')
    subprocess.run(['feh', '--bg-max', image_path])


if __name__ == '__main__':
    cli()
