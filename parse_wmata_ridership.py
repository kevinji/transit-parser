import re
from datetime import date

import polars as pl

DATA_THROUGH_RE = re.compile(r"Showing Data Through (\d{1,2})/(\d{1,2})/(\d{4})")


def parse_data_through(filename: str) -> date:
    with open(filename, encoding="utf-8-sig") as f:
        match = DATA_THROUGH_RE.search(f.read())
    if not match:
        raise ValueError(f"No data range found in {filename}")
    return date(int(match[3]), int(match[1]), int(match[2]))


def parse_dc_metro_weekday_ridership(
    entries_filename: str, data_range_filename: str
) -> pl.DataFrame:
    """
    Sum the average weekday tapped and non-tapped entries for each month. Non-tapped
    entries (faregate entries without a fare tap) are only recorded from 2023. WMATA's
    weekday service type already excludes holidays. The latest month is dropped if the
    data doesn't cover the whole month.
    """
    data_through = parse_data_through(data_range_filename)
    return (
        pl.read_csv(entries_filename)
        .select(
            month_start=pl.concat_str(
                pl.col("Year of Date").cast(pl.String),
                pl.col("Month of Date"),
                separator=" ",
            ).str.to_date("%Y %B"),
            riders=pl.col("Measure Values").str.replace_all(",", "").cast(pl.Float64),
        )
        .group_by("month_start")
        .agg(pl.col("riders").sum())
        .filter(pl.col("month_start").dt.month_end() <= data_through)
        .sort("month_start")
        .select(
            year=pl.col("month_start").dt.year(),
            month=pl.col("month_start").dt.month(),
            riders=pl.col("riders").round().cast(pl.Int64),
        )
    )
