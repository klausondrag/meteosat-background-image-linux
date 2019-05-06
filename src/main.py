import asyncio
import subprocess
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

import click
import requests

click.option = partial(click.option, show_default=True)

BASE_URL = 'http://www.sat.dundee.ac.uk/xrit/000.0E/MSG'
BASE_DIR = Path('~/.config/i3/images/').expanduser()
SAVE_DIR = Path('~/Pictures/meteosat/').expanduser()


@click.group()
def cli():
    pass


@cli.command()
@click.argument('until-date', type=click.DateTime(formats=['%Y-%m-%d', '%Y-%m-%dT%H']))
@click.option('-ag/-nag', '--all-grids/--not-all-grids', default=True)
@click.option('-ug/-nug', '--use-grid/--no-use-grid', default=True)
def until(until_date: datetime, all_grids: bool, use_grid: bool) -> None:
    iter_bools = [True, False] if all_grids else [use_grid]
    start_date = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    for current_date in iter_datetimes(start_date):
        if current_date < until_date:
            break
        for ug in iter_bools:
            url, image_path = construct_from_date(current_date, use_grid=ug)
            download_maybe(url, image_path)


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


def iter_datetimes(date: datetime):
    while True:
        yield date
        date -= timedelta(hours=1)


def get_hour_string(hour: int) -> str:
    if hour == 0:
        return '0'
    else:
        return f'{hour}00'


def construct_from_date(current_date, use_grid: bool) -> Tuple[str, Path]:
    grid_text = '_grid' if use_grid else ''
    hour_string = get_hour_string(current_date.hour)
    overview_url = (
        f'{BASE_URL}/{current_date.year}/{current_date.month}/{current_date.day}'
    )
    filename = (
        f'{current_date.year}_{current_date.month}_{current_date.day}_{hour_string}'
        + f'_MSG4_16_S1{grid_text}.jpeg'
    )
    url = f'{overview_url}/{hour_string}/{filename}'
    grid_dir = 'grid' if use_grid else 'no_grid'
    image_path = SAVE_DIR / grid_dir / filename
    image_path.parent.mkdir(parents=True, exist_ok=True)
    return url, image_path


def download_maybe(url: str, image_path: Path) -> bool:
    print('Trying image: ', image_path.name)
    image_path_string = str(image_path)
    if image_path.exists():
        print('Image already exists at: ', image_path_string)
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


async def download_maybe_async(
    url: str, image_path: Path, semaphores: Optional[asyncio.Semaphore] = None
) -> bool:
    print('Trying image: ', image_path.name)
    image_path_string = str(image_path)
    if image_path.exists():
        # print('Image already exists at: ', image_path_string)
        print('Skipping downloading.')
        is_successful = True
    else:
        print('Getting image from URL: ', url)
        async with semaphores:
            await asyncio.sleep(1)
            return True
    return is_successful


def set_background(image_path: Path) -> None:
    print('Calling feh')
    subprocess.run(['feh', '--bg-max', image_path])


if __name__ == '__main__':
    cli()
