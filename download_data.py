import argparse
import base64
import calendar
import io
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import date, timedelta
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
MTA_SUBWAY_HOURLY_START = date(2017, 2, 1)
# Before the hourly datasets, daily entries are estimated from the cumulative entry
# counters that each turnstile reports about every 4 hours. These are the MTA Subway
# Turnstile Usage Data datasets for 2014-2017, which together cover February 2014
# onward. Their monthly weekday averages match the hourly datasets within 0.5%.
MTA_TURNSTILE_DATASETS = ["i55r-43gk", "ug6q-shqc", "ekwu-khcy", "v5y5-mwpb"]
MTA_TURNSTILE_START = date(2014, 2, 1)
MTA_SUBWAY_DIVISIONS = ["IRT", "IND", "BMT"]
# Larger jumps between readings are counter resets or errors rather than entries.
MTA_TURNSTILE_MAX_ENTRIES_PER_READING = 5000

# WMATA's Metrorail ridership dashboards are Tableau views, which can be exported as CSV.
# The yearly dashboard's export only contains the date the data runs through.
WMATA_RIDERSHIP_VIEWS_URL = "https://exttabanalytics.wmata.com/views/RidershipDataPortal-MetroRailRidershipSummary"
WMATA_MONTHLY_ENTRIES_URL = (
    f"{WMATA_RIDERSHIP_VIEWS_URL}/AvgDailyEntriesbyMonth.csv?Service%20Type=Weekday"
)
WMATA_DATA_RANGE_URL = f"{WMATA_RIDERSHIP_VIEWS_URL}/AvgWeekdayEntriesbyYear.csv"

MONTH_NAMES = "|".join(calendar.month_name[1:])

# Sound Transit's ridership tracker is a public Power BI report. Its data can be queried
# through the API that the embedded report uses, which needs the report's key from the
# embed URL on the tracker page.
SOUND_TRANSIT_RIDERSHIP_PAGE_URL = (
    "https://www.soundtransit.org/ride-with-us/system-performance-tracker/ridership"
)
POWER_BI_EMBED_RE = re.compile(r"https://app\.powerbi\.com/view\?r=([A-Za-z0-9_=-]+)")
POWER_BI_API_URL = (
    "https://wabi-west-us-c-primary-api.analysis.windows.net/public/reports"
)
# Before 2019, Link ridership comes from Sound Transit's monthly service performance
# reports, which are listed by the documents API behind the ridership documents page.
SOUND_TRANSIT_DOCUMENTS_URL = (
    "https://www.soundtransit.org/restful/media/by-topic/list.json?topic=549"
)
SOUND_TRANSIT_MONTHLY_REPORT_RE = re.compile(
    rf"({MONTH_NAMES}) (\d{{4}}) ridership (?:report|summary)", re.IGNORECASE
)
SOUND_TRANSIT_MONTHLY_COLUMNS = [
    "MonthRefDate",
    "Mode",
    "ScheduleType",
    "AvgBdgsPerDay",
    "Boardings",
]

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


def download_muni(original_dir: str):
    download_file(
        SFMTA_MUNI_RIDERSHIP_URL,
        os.path.join(original_dir, "sfmta", "ridership.csv"),
    )


def download_ny_open_data(dataset: str, params: dict[str, str], filename: str):
    content = download_with_retries(
        NY_OPEN_DATA_URL.format(dataset=dataset), params={"$limit": "50000", **params}
    )
    with open(filename, "wb") as f:
        f.write(content)


def download_with_retries(url: str, params: dict[str, str], attempts: int = 5) -> bytes:
    """
    Download a response body, retrying on errors. NY Open Data sometimes times out
    partway through a large response, which `requests`' own retries don't cover.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=300)
            response.raise_for_status()
            return response.content
        except requests.RequestException:
            if attempt == attempts:
                raise
            time.sleep(10 * attempt)
    raise AssertionError("unreachable")


def turnstile_daily_entries(start: date, end: date) -> pl.DataFrame:
    """
    Estimate daily subway entries from start to end (exclusive) by summing the
    increases in each turnstile's cumulative entry counter. Readings from the day
    before start are included so that the first increase on start can be computed.
    """
    divisions = ", ".join(f"'{division}'" for division in MTA_SUBWAY_DIVISIONS)
    readings = []
    for dataset in MTA_TURNSTILE_DATASETS:
        csv = download_with_retries(
            NY_OPEN_DATA_URL.format(dataset=dataset).removesuffix(".json") + ".csv",
            params={
                "$select": "c_a, unit, scp, date, time, entries",
                "$where": f"division IN ({divisions}) AND "
                f"date >= '{start - timedelta(days=1)}' AND date < '{end}'",
                "$limit": "10000000",
            },
        )
        readings.append(pl.read_csv(io.BytesIO(csv), infer_schema=False))

    return (
        pl.concat(readings)
        .select(
            turnstile=pl.concat_str("c_a", "unit", "scp", separator="/"),
            timestamp=(
                pl.col("date").str.slice(0, 10) + " " + pl.col("time")
            ).str.to_datetime("%Y-%m-%d %H:%M:%S"),
            entries=pl.col("entries").cast(pl.Int64),
        )
        .unique(["turnstile", "timestamp"])
        .sort("turnstile", "timestamp")
        # Some counters count down, so use the size of each change.
        .with_columns(increase=pl.col("entries").diff().over("turnstile").abs())
        .filter(pl.col("increase") <= MTA_TURNSTILE_MAX_ENTRIES_PER_READING)
        .group_by(date=pl.col("timestamp").dt.date())
        .agg(riders=pl.col("increase").sum())
        .filter(pl.col("date") >= start)
    )


def download_nyc_subway(original_dir: str, processed_dir: str):
    mta_dir = os.path.join(original_dir, "mta")
    os.makedirs(mta_dir, exist_ok=True)
    for dataset in MTA_SUBWAY_HOURLY_DATASETS:
        download_ny_open_data(
            dataset,
            {
                "$select": "date_trunc_ymd(transit_timestamp) AS date, "
                "sum(ridership) AS riders",
                "$where": "transit_mode = 'subway' AND "
                f"transit_timestamp >= '{MTA_SUBWAY_HOURLY_START}' AND "
                f"transit_timestamp < '{MTA_DAILY_RIDERSHIP_START}'",
                "$group": "date",
                "$order": "date",
            },
            os.path.join(mta_dir, f"subway-hourly-ridership-by-day-{dataset}.json"),
        )
    download_ny_open_data(
        MTA_DAILY_RIDERSHIP_DATASET,
        {
            "$select": "date, count AS riders",
            "$where": f"mode = 'Subway' AND date >= '{MTA_DAILY_RIDERSHIP_START}'",
            "$order": "date",
        },
        os.path.join(mta_dir, "subway-daily-ridership.json"),
    )

    # The raw turnstile readings are too large to keep, so only the daily estimates
    # computed from them are saved.
    turnstile_days = []
    month_start = MTA_TURNSTILE_START
    with tqdm(desc="turnstile months", unit="month") as pbar:
        while month_start < MTA_SUBWAY_HOURLY_START:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            turnstile_days.append(turnstile_daily_entries(month_start, next_month))
            month_start = next_month
            pbar.update()

    processed_mta_dir = os.path.join(processed_dir, "mta")
    os.makedirs(processed_mta_dir, exist_ok=True)
    pl.concat(turnstile_days).sort("date").write_csv(
        os.path.join(processed_mta_dir, "subway-turnstile-daily-entries.csv")
    )


def download_dc_metro(original_dir: str):
    wmata_dir = os.path.join(original_dir, "wmata")
    os.makedirs(wmata_dir, exist_ok=True)
    download_file(
        WMATA_MONTHLY_ENTRIES_URL,
        os.path.join(wmata_dir, "rail-weekday-entries-by-month.csv"),
    )
    download_file(WMATA_DATA_RANGE_URL, os.path.join(wmata_dir, "data-range.csv"))


def sound_transit_power_bi_key() -> str:
    response = requests.get(SOUND_TRANSIT_RIDERSHIP_PAGE_URL)
    response.raise_for_status()
    match = POWER_BI_EMBED_RE.search(response.text)
    if not match:
        raise ValueError("No Power BI report found on the Sound Transit ridership page")
    return json.loads(base64.b64decode(match[1]))["k"]


def download_sound_transit_monthly_reports(sound_transit_dir: str):
    reports_dir = os.path.join(sound_transit_dir, "service-performance-reports")
    os.makedirs(reports_dir, exist_ok=True)
    page = 0
    while True:
        response = requests.get(SOUND_TRANSIT_DOCUMENTS_URL, params={"page": page})
        response.raise_for_status()
        documents = response.json()["content"]
        if not documents:
            break
        for document in documents:
            match = SOUND_TRANSIT_MONTHLY_REPORT_RE.fullmatch(document["title"].strip())
            if not match:
                continue
            month = list(calendar.month_name).index(match[1].capitalize())
            download_file(
                urljoin(SOUND_TRANSIT_DOCUMENTS_URL, document["file_url"]),
                os.path.join(reports_dir, f"ridership-{match[2]}{month:02d}.pdf"),
            )
        page += 1


def download_link_light_rail(original_dir: str):
    sound_transit_dir = os.path.join(original_dir, "sound-transit")
    download_sound_transit_monthly_reports(sound_transit_dir)

    key = sound_transit_power_bi_key()
    headers = {"X-PowerBI-ResourceKey": key}
    response = requests.get(
        f"{POWER_BI_API_URL}/{key}/modelsAndExploration",
        params={"preferReadOnlySession": "true"},
        headers=headers,
    )
    response.raise_for_status()
    model_id = response.json()["models"][0]["id"]

    # Monthly boardings and average daily boardings for each mode and schedule type
    source = {"SourceRef": {"Source": "m"}}
    select = [
        {"Column": {"Expression": source, "Property": "MonthRefDate"}},
        {"Column": {"Expression": source, "Property": "Mode"}},
        {"Column": {"Expression": source, "Property": "ScheduleType"}},
        *(
            {
                "Aggregation": {
                    "Expression": {"Column": {"Expression": source, "Property": p}},
                    "Function": 0,
                }
            }
            for p in ["AvgBdgsPerDay", "Boardings"]
        ),
    ]
    for column, name in zip(select, SOUND_TRANSIT_MONTHLY_COLUMNS, strict=True):
        column["Name"] = name
    query = {
        "Version": 2,
        "From": [{"Name": "m", "Entity": "MonthlyMetrics", "Type": 0}],
        "Select": select,
    }
    command = {
        "Query": query,
        "Binding": {
            "Primary": {"Groupings": [{"Projections": list(range(len(select)))}]},
            "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 30000}}},
            "Version": 1,
        },
    }
    response = requests.post(
        f"{POWER_BI_API_URL}/querydata",
        params={"synchronous": "true"},
        headers=headers,
        json={
            "version": "1.0.0",
            "queries": [
                {"Query": {"Commands": [{"SemanticQueryDataShapeCommand": command}]}}
            ],
            "modelId": model_id,
        },
    )
    response.raise_for_status()
    result = response.json()["results"][0]["result"]
    if "error" in result:
        raise ValueError(f"Power BI query failed: {result['error']}")

    with open(os.path.join(sound_transit_dir, "monthly-ridership.json"), "wb") as f:
        f.write(response.content)


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
    parser.add_argument(
        "mode", choices=["bart", "dc-metro", "link-light-rail", "muni", "nyc-subway"]
    )
    args = parser.parse_args()

    data_repo = os.environ["DATA_REPO"]
    original_dir = os.path.join(data_repo, "original")
    processed_dir = os.path.join(data_repo, "processed")
    match args.mode:
        case "bart":
            download_bart(original_dir)
        case "dc-metro":
            download_dc_metro(original_dir)
        case "link-light-rail":
            download_link_light_rail(original_dir)
        case "muni":
            download_muni(original_dir)
        case "nyc-subway":
            download_nyc_subway(original_dir, processed_dir)


if __name__ == "__main__":
    main()
