import asyncio
import itertools
import subprocess
from datetime import datetime, timedelta
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
import click
import cv2
import imageio
import numpy as np
import requests
from tqdm import tqdm

click.option = partial(click.option, show_default=True)

BASE_URL = 'http://www.sat.dundee.ac.uk/xrit/000.0E/MSG'
BASE_DIR = Path('~/.config/i3/images/').expanduser()
SAVE_DIR = Path('~/Pictures/meteosat/').expanduser()


class Quality(Enum):
    LOW = 'S4'
    MEDIUM = 'S2'
    HIGH = 'S1'


possible_qualities = [q.name.lower() for q in Quality]


class Grid(Enum):
    USE = 'grid'
    DONT_USE = 'no_grid'


def get_save_dir(grid: Grid, quality: Quality) -> Path:
    path = SAVE_DIR / grid.value / quality.value
    path.mkdir(parents=True, exist_ok=True)
    return path


@click.group()
def cli():
    pass


# fix file name when saving for better file browser support???
# gif append
# inner loop grid or outer
# add tqdm to download
# aiohttp
# random sleep to be nice
# optimize gif size
# write day on gif


@cli.command()
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
@click.option(
    '-q',
    '--quality',
    default=Quality.LOW.name.lower(),
    type=click.Choice(possible_qualities),
)
def gif(use_grid: bool, quality: str) -> None:
    grid = Grid.USE if use_grid else Grid.DONT_USE
    quality = Quality[quality.upper()]
    image_directory = get_save_dir(grid, quality)
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
@click.option(
    '-q',
    '--quality',
    default=Quality.LOW.name.lower(),
    type=click.Choice(possible_qualities),
)
@click.option('-ncd', '--n-concurrent-downloads', default=5)
def until(
    until_date: datetime,
    all_grids: bool,
    use_grid: bool,
    quality: str,
    n_concurrent_downloads: int,
) -> None:
    iter_bools = list(Grid) if all_grids else [Grid.USE if use_grid else Grid.DONT_USE]
    quality = Quality[quality.upper()]
    start_date = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    images_to_download = itertools.product(
        iter_datetimes(start_date, until_date), iter_bools
    )
    images_to_download = [
        construct_from_date(current_date, grid, quality)
        for current_date, grid in images_to_download
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
        for url, image_path, date_text in images_to_download:
            print('Trying image: ', image_path.name)
            if image_path.exists():
                # print('Image already exists at: ', image_path_string)
                print('Skipping downloading.')
            else:
                print('Getting image from URL: ', url)
                task = asyncio.ensure_future(
                    bound_fetch(url, image_path, date_text, session, sem)
                )
                tasks.append(task)

        responses = asyncio.gather(*tasks)
        await responses


async def bound_fetch(
    url: str,
    image_path: Path,
    date_text: str,
    session: aiohttp.client.ClientSession,
    semaphore: asyncio.locks.Semaphore,
) -> None:
    async with semaphore:
        error, image = await fetch(url, session)

        if not error:
            save_image(image, str(image_path), date_text)


async def fetch(
    url: str, session: aiohttp.client.ClientSession
) -> Tuple[bool, Optional[bytes]]:
    async with session.get(url) as response:
        if response.status != 200:
            print('Bad response:', url, response.status, response.reason)
            return True, None
        else:
            return False, await response.read()


@cli.command()
@click.option('-mt', '--max-tries', default=20)
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
@click.option(
    '-q',
    '--quality',
    default=Quality.LOW.name.lower(),
    type=click.Choice(possible_qualities),
)
def newest(max_tries: int, use_grid: bool, quality: str) -> None:
    grid = Grid.USE if use_grid else Grid.DONT_USE
    quality = Quality[quality.upper()]
    start_date = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    is_successful = False
    for current_try, current_date in zip(range(max_tries), iter_datetimes(start_date)):
        url, image_path, date_text = construct_from_date(current_date, grid, quality)
        is_successful = download_maybe(url, image_path, date_text)
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


def construct_from_date(
    current_date, grid: Grid, quality: Quality
) -> Tuple[str, Path, str]:
    overview_url = (
        f'{BASE_URL}/{current_date.year}/{current_date.month}/{current_date.day}'
    )
    server_hour_string = get_server_hour_string(current_date.hour)
    server_filename = get_server_filename(
        current_date, server_hour_string, grid, quality
    )
    url = f'{overview_url}/{server_hour_string}/{server_filename}'

    local_hour_string = get_local_hour_string(current_date.hour)
    local_filename = get_local_filename(current_date, local_hour_string, grid, quality)
    image_path = get_save_dir(grid, quality) / local_filename
    image_path.parent.mkdir(parents=True, exist_ok=True)

    date_text = current_date.strftime('%Y-%m-%dT%H%M')

    return url, image_path, date_text


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


def get_server_filename(
    current_date: datetime, hour_string: str, grid: Grid, quality: Quality
) -> str:
    grid_text = ('_' + grid.value) if grid == Grid.USE else ''
    return (
        current_date.strftime('%Y_%-m_%-d')
        + f'_{hour_string}_MSG4_16_{quality.value}{grid_text}.jpeg'
    )


def get_local_filename(
    current_date: datetime, hour_string: str, grid: Grid, quality: Quality
) -> str:
    grid_text = ('_' + grid.value) if grid == Grid.USE else ''
    return (
        current_date.strftime('%Y-%m-%dT%H%M')
        + f'_MSG4_16_{quality.value}{grid_text}.jpeg'
    )


def download_maybe(url: str, image_path: Path, date_text: str) -> bool:
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
            save_image(response.content, image_path_string, date_text)
            is_successful = True
        else:
            print('Bad response: ', response)
            is_successful = False
    return is_successful


def save_image(image: bytes, image_path_string: str, date_text: str) -> None:
    print('Saving image: ', image_path_string)
    img_array = np.asarray(bytearray(image), dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_position = (10, 60)
    font_scale = 0.75
    font_color = (255, 255, 255)
    line_type = 0
    cv2.putText(
        image, date_text, text_position, font, font_scale, font_color, line_type
    )
    cv2.imwrite(image_path_string, image)


def set_background(image_path: Path) -> None:
    print('Calling feh')
    subprocess.run(['feh', '--bg-max', image_path])


if __name__ == '__main__':
    cli()
