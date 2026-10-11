import argparse
import calendar
import os
import re
import shutil
import tempfile
import zipfile
from urllib.parse import unquote, urljoin, urlparse

import polars as pl
import requests
from tqdm import tqdm

SFMTA_MUNI_RIDERSHIP_URL = (
    "https://transtat.sfmta.com/t/public/views/Goal2Dashboards/RidershipTable.csv"
)

BART_RIDERSHIP_PAGE_URL = "https://www.bart.gov/about/reports/ridership"

# The MTA website blocks scripted downloads, so subway ridership comes from the MTA's
# datasets on the NY Open Data portal instead. The daily systemwide dataset matches the
# MTA's published average weekday ridership within 0.5%, but only starts in March 2020;
# earlier days are summed from the hourly station-level datasets.
NY_OPEN_DATA_URL = "https://data.ny.gov/resource/{dataset}.json"
MTA_DAILY_RIDERSHIP_DATASET = "sayj-mze2"
MTA_DAILY_RIDERSHIP_START = "2020-03-01"
# MTA Subway Hourly Ridership for 2017-2019 and 2020-2024
MTA_SUBWAY_HOURLY_DATASETS = ["t69i-h2me", "wujg-7c2s"]

MONTH_NAMES = "|".join(calendar.month_name[1:])
# Monthly files are named like `Ridership_202601.xlsx`, `Ridership_202401 1.xlsx`,
# `Ridership_April2010.xlsx`, `Ridership_April 2008.xls`, or
# `January 2001 Entry_Exit Matrices.xls`
BART_NUMERIC_MONTH_RE = re.compile(
    r"^Ridership_(\d{4})(\d{2})(?: \d+)?\.(xlsx?)$", re.IGNORECASE
)
BART_NAMED_MONTH_RE = re.compile(
    rf"({MONTH_NAMES})\s*(\d{{4}})(?!\d).*\.(xlsx?)$", re.IGNORECASE
)
# Yearly archives of monthly files, e.g. `ridership_2024.zip` or
# `ridership_OD_2025.zip`
BART_YEARLY_ZIP_RE = re.compile(r"ridership_(?:OD_)?(\d{4})\.zip$", re.IGNORECASE)


def download_file(url: str, filename: str):
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))

    with (
        open(filename, "wb") as f,
        tqdm(
            desc=os.path.basename(filename),
            total=total_size,
            unit="iB",
            unit_scale=True,
        ) as pbar,
    ):
        for chunk in response.iter_content(chunk_size=8192):
            size = f.write(chunk)
            pbar.update(size)


def url_basename(url: str) -> str:
    return unquote(os.path.basename(urlparse(url).path))


def bart_ridership_filename(name: str) -> str | None:
    """
    Normalize a BART monthly ridership file name (e.g. `Ridership_April2010.xlsx`)
    to `ridership-YYYYMM.<ext>`, or return `None` if it isn't one.
    """
    if match := BART_NUMERIC_MONTH_RE.search(name):
        year, month, ext = int(match[1]), int(match[2]), match[3]
    elif match := BART_NAMED_MONTH_RE.search(name):
        month = list(calendar.month_name).index(match[1].capitalize())
        year, ext = int(match[2]), match[3]
    else:
        return None
    return f"ridership-{year}{month:02d}.{ext.lower()}"


def find_bart_ridership_urls() -> tuple[list[str], list[str]]:
    """
    Scrape the BART ridership page for monthly files and yearly .zip archives.
    """
    response = requests.get(BART_RIDERSHIP_PAGE_URL)
    response.raise_for_status()

    monthly_urls = []
    yearly_zip_urls = []
    for href in re.findall(r'href="([^"]+)"', response.text):
        url = urljoin(BART_RIDERSHIP_PAGE_URL, href)
        basename = url_basename(url)
        if bart_ridership_filename(basename):
            monthly_urls.append(url)
        elif BART_YEARLY_ZIP_RE.search(basename):
            yearly_zip_urls.append(url)
    return monthly_urls, yearly_zip_urls


def download_bart_yearly_zip(url: str, bart_dir: str):
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_filename = os.path.join(tmp_dir, os.path.basename(url))
        download_file(url, zip_filename)

        with zipfile.ZipFile(zip_filename) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                filename = bart_ridership_filename(os.path.basename(info.filename))
                if not filename:
                    raise ValueError(f"Unrecognized file {info.filename!r} in {url}")
                with (
                    zf.open(info) as src,
                    open(os.path.join(bart_dir, filename), "wb") as dst,
                ):
                    shutil.copyfileobj(src, dst)


def original_data_dir() -> str:
    data_repo = os.environ["DATA_REPO"]
    return os.path.join(data_repo, "original")


def download_muni(original_dir: str):
    download_file(
        SFMTA_MUNI_RIDERSHIP_URL,
        os.path.join(original_dir, "sfmta", "ridership.csv"),
    )


def query_ny_open_data(dataset: str, params: dict[str, str]) -> list[dict]:
    response = requests.get(
        NY_OPEN_DATA_URL.format(dataset=dataset),
        params={"$limit": "50000", **params},
        timeout=600,
    )
    response.raise_for_status()
    return response.json()


def download_nyc_subway(original_dir: str):
    rows = []
    for dataset in MTA_SUBWAY_HOURLY_DATASETS:
        rows += query_ny_open_data(
            dataset,
            {
                "$select": "date_trunc_ymd(transit_timestamp) AS date, "
                "sum(ridership) AS riders",
                "$where": "transit_mode = 'subway' AND "
                f"transit_timestamp < '{MTA_DAILY_RIDERSHIP_START}'",
                "$group": "date",
            },
        )
    rows += query_ny_open_data(
        MTA_DAILY_RIDERSHIP_DATASET,
        {
            "$select": "date, count AS riders",
            "$where": f"mode = 'Subway' AND date >= '{MTA_DAILY_RIDERSHIP_START}'",
        },
    )

    df = (
        pl.DataFrame(rows)
        .select(
            date=pl.col("date").str.to_datetime().dt.date(),
            riders=pl.col("riders").cast(pl.Float64).round().cast(pl.Int64),
        )
        .sort("date")
    )
    assert df["date"].is_unique().all()

    mta_dir = os.path.join(original_dir, "mta")
    os.makedirs(mta_dir, exist_ok=True)
    df.write_csv(os.path.join(mta_dir, "subway-daily-ridership.csv"))


def download_bart(original_dir: str):
    bart_dir = os.path.join(original_dir, "bart")
    monthly_urls, yearly_zip_urls = find_bart_ridership_urls()
    for url in yearly_zip_urls:
        download_bart_yearly_zip(url, bart_dir)
    for url in monthly_urls:
        filename = bart_ridership_filename(url_basename(url))
        assert filename
        download_file(url, os.path.join(bart_dir, filename))


def main():
    parser = argparse.ArgumentParser(description="Download transit ridership data")
    parser.add_argument("mode", choices=["bart", "muni", "nyc-subway"])
    args = parser.parse_args()

    original_dir = original_data_dir()
    match args.mode:
        case "bart":
            download_bart(original_dir)
        case "muni":
            download_muni(original_dir)
        case "nyc-subway":
            download_nyc_subway(original_dir)


if __name__ == "__main__":
    main()
