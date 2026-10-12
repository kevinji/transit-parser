import argparse
import glob
import os
import re
from datetime import date

import orjson
import polars as pl

from parse_bart_ridership import parse_bart_weekday_ridership
from parse_mta_ridership import (
    combine_nyc_subway_daily_ridership,
    parse_nyc_subway_weekday_ridership,
)
from parse_muni_ridership import parse_muni_metro_weekday_ridership
from parse_sound_transit_ridership import (
    parse_link_light_rail_weekday_ridership,
    parse_monthly_report_link_weekday_ridership,
    parse_sound_transit_monthly_ridership,
)
from parse_wmata_ridership import parse_dc_metro_weekday_ridership

BART_RIDERSHIP_FILE_RE = re.compile(r"ridership-(\d{4})(\d{2})\.xlsx?")
SOUND_TRANSIT_REPORT_FILE_RE = re.compile(r"ridership-(\d{4})(\d{2})\.pdf")


def write_json(rows: list[dict], filename: str):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as f:
        f.write(
            orjson.dumps(rows, option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE)
        )


def generate_bart(original_dir: str, generated_dir: str):
    bart_dir = os.path.join(original_dir, "bart")
    rows = []
    for name in sorted(os.listdir(bart_dir)):
        match = BART_RIDERSHIP_FILE_RE.fullmatch(name)
        if not match:
            continue
        riders = parse_bart_weekday_ridership(os.path.join(bart_dir, name))
        rows.append(
            {"year": int(match[1]), "month": int(match[2]), "riders": round(riders)}
        )
    write_json(rows, os.path.join(generated_dir, "bart", "weekday-ridership.json"))


def generate_dc_metro(original_dir: str, generated_dir: str):
    wmata_dir = os.path.join(original_dir, "wmata")
    df = parse_dc_metro_weekday_ridership(
        os.path.join(wmata_dir, "rail-weekday-entries-by-month.csv"),
        os.path.join(wmata_dir, "data-range.csv"),
    )
    write_json(
        df.to_dicts(), os.path.join(generated_dir, "wmata", "weekday-ridership.json")
    )


def generate_link_light_rail(original_dir: str, processed_dir: str, generated_dir: str):
    original_sound_transit_dir = os.path.join(original_dir, "sound-transit")
    processed_sound_transit_dir = os.path.join(processed_dir, "sound-transit")
    os.makedirs(processed_sound_transit_dir, exist_ok=True)

    monthly_filename = os.path.join(
        processed_sound_transit_dir, "monthly-ridership.csv"
    )
    parse_sound_transit_monthly_ridership(
        os.path.join(original_sound_transit_dir, "monthly-ridership.json")
    ).write_csv(monthly_filename)

    reports_dir = os.path.join(
        original_sound_transit_dir, "service-performance-reports"
    )
    report_rows = []
    for name in sorted(os.listdir(reports_dir)):
        match = SOUND_TRANSIT_REPORT_FILE_RE.fullmatch(name)
        if not match:
            continue
        report_rows += parse_monthly_report_link_weekday_ridership(
            os.path.join(reports_dir, name), date(int(match[1]), int(match[2]), 1)
        )
    reports_filename = os.path.join(
        processed_sound_transit_dir, "service-performance-reports-link-weekday.csv"
    )
    pl.DataFrame(report_rows).write_csv(reports_filename)

    df = parse_link_light_rail_weekday_ridership(monthly_filename, reports_filename)
    write_json(
        df.to_dicts(),
        os.path.join(generated_dir, "sound-transit", "weekday-ridership.json"),
    )


def generate_muni(original_dir: str, generated_dir: str):
    df = parse_muni_metro_weekday_ridership(
        os.path.join(original_dir, "sfmta", "ridership.csv")
    )
    write_json(
        df.to_dicts(), os.path.join(generated_dir, "sfmta", "weekday-ridership.json")
    )


def generate_nyc_subway(original_dir: str, processed_dir: str, generated_dir: str):
    daily_filename = os.path.join(processed_dir, "mta", "subway-daily-ridership.csv")
    combine_nyc_subway_daily_ridership(
        os.path.join(processed_dir, "mta", "subway-turnstile-daily-entries.csv"),
        sorted(glob.glob(os.path.join(original_dir, "mta", "*.json"))),
    ).write_csv(daily_filename)

    df = parse_nyc_subway_weekday_ridership(daily_filename)
    write_json(
        df.to_dicts(), os.path.join(generated_dir, "mta", "weekday-ridership.json")
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate chart data from ridership files"
    )
    parser.add_argument(
        "mode", choices=["bart", "dc-metro", "link-light-rail", "muni", "nyc-subway"]
    )
    args = parser.parse_args()

    data_repo = os.environ["DATA_REPO"]
    original_dir = os.path.join(data_repo, "original")
    processed_dir = os.path.join(data_repo, "processed")
    generated_dir = os.path.join(data_repo, "generated")
    match args.mode:
        case "bart":
            generate_bart(original_dir, generated_dir)
        case "dc-metro":
            generate_dc_metro(original_dir, generated_dir)
        case "link-light-rail":
            generate_link_light_rail(original_dir, processed_dir, generated_dir)
        case "muni":
            generate_muni(original_dir, generated_dir)
        case "nyc-subway":
            generate_nyc_subway(original_dir, processed_dir, generated_dir)


if __name__ == "__main__":
    main()
