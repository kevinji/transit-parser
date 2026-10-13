import re
from datetime import date, datetime

import orjson
import pdfplumber
import polars as pl

from data_files import open_compressed, read_compressed


def decode_power_bi_rows(data: dict) -> list[list]:
    """
    Decode the rows of a Power BI query result. Each row lists only the values that
    differ from the previous row: bit i of `R` marks column i as repeated, bit i of `Ø`
    marks it as null, and string columns hold indexes into the value dictionaries.
    """
    dataset = data["dsr"]["DS"][0]
    value_dicts = dataset.get("ValueDicts", {})
    columns = []
    rows = []
    previous = []
    for row in dataset["PH"][0]["DM0"]:
        columns = row.get("S", columns)
        values = iter(row.get("C", []))
        current = []
        for i, column in enumerate(columns):
            if row.get("R", 0) >> i & 1:
                value = previous[i]
            elif row.get("Ø", 0) >> i & 1:
                value = None
            else:
                value = next(values)
                if "DN" in column:
                    value = value_dicts[column["DN"]][value]
            current.append(value)
        rows.append(current)
        previous = current
    return rows


def parse_sound_transit_monthly_ridership(filename: str) -> pl.DataFrame:
    """
    Get the total and average daily boardings for each month, mode, and schedule type
    from a Sound Transit ridership tracker query. The average for the month the query
    ran in is divided by all of the month's days even though only some have data, so
    only months before it are kept.
    """
    data = orjson.loads(read_compressed(filename))["results"][0]["result"]["data"]
    queried_month = datetime.fromisoformat(data["timestamp"]).date().replace(day=1)
    return (
        pl.DataFrame(
            decode_power_bi_rows(data),
            schema=["month", "mode", "schedule_type", "average_boardings", "boardings"],
            orient="row",
        )
        .with_columns(
            pl.from_epoch(pl.col("month"), time_unit="ms").dt.date(),
            # Some values are returned as strings.
            pl.col("average_boardings", "boardings").cast(pl.String).cast(pl.Float64),
        )
        .filter(pl.col("month") < queried_month)
        .sort("month", "mode", "schedule_type")
    )


def parse_link_light_rail_weekday_ridership(
    monthly_filename: str, reports_filename: str
) -> pl.DataFrame:
    """
    Get the average weekday Link light rail boardings for each month. Sound Transit's
    weekday averages already exclude holidays. Months before the ridership tracker's
    data come from the monthly reports, using the latest report for each month since
    each report revises the prior year's figure.
    """
    tracker = (
        pl.read_csv(monthly_filename, try_parse_dates=True)
        .filter(pl.col("mode") == "Link", pl.col("schedule_type") == "Weekday")
        .select("month", riders=pl.col("average_boardings").round().cast(pl.Int64))
    )
    reports = (
        pl.read_csv(reports_filename, try_parse_dates=True)
        .filter(pl.col("month") < tracker["month"].min())
        .sort("report")
        .group_by("month")
        .agg(pl.col("riders").last())
    )
    return (
        pl.concat([reports, tracker])
        .sort("month")
        .select(
            year=pl.col("month").dt.year(),
            month=pl.col("month").dt.month(),
            riders="riders",
        )
    )


def parse_monthly_report_link_weekday_ridership(
    filename: str, report_month: date
) -> list[dict]:
    """
    Get the average weekday Link boardings for the report's month and the same month a
    year earlier from a Sound Transit monthly ridership report. Reports from 2014 on
    have an average daily boardings table with the prior year first. Earlier reports
    have one row per mode with the current year first, where the weekday averages
    follow the monthly and year-to-date totals.
    """
    with pdfplumber.open(open_compressed(filename)) as pdf:
        text = pdf.pages[0].extract_text(layout=True)
    # Some reports split numbers like "30,509" into "3 0,509".
    text = re.sub(r"(?<![\d,])(\d) (?=\d{1,2},\d{3}\b)", r"\1", text)
    previous_month = report_month.replace(year=report_month.year - 1)

    if "Average Daily Boardings" in text:
        table = text[text.index("Average Daily Boardings") :]
        match = re.search(
            r"^\s*(?:Central )?Link\s+([\d,]+)\s+([\d,]+)", table, re.MULTILINE
        )
        if not match:
            raise ValueError(f"No Link weekday boardings found in {filename}")
        previous, current = match[1], match[2]
    else:
        match = re.search(r"^\s*Central Link light rail\s+(.*%.*)$", text, re.MULTILINE)
        if not match:
            raise ValueError(f"No Link weekday boardings found in {filename}")
        # Monthly total, year-to-date total, then weekday average, skipping the
        # percent changes after each pair.
        numbers = [
            token for token in match[1].split() if re.fullmatch(r"[\d,]+", token)
        ]
        current, previous = numbers[4], numbers[5]

    return [
        {"month": month, "riders": int(riders.replace(",", "")), "report": report_month}
        for month, riders in [(previous_month, previous), (report_month, current)]
    ]
