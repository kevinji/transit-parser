from datetime import datetime

import orjson
import polars as pl


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
    with open(filename, "rb") as f:
        data = orjson.loads(f.read())["results"][0]["result"]["data"]
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


def parse_link_light_rail_weekday_ridership(filename: str) -> pl.DataFrame:
    """
    Get the average weekday Link light rail boardings for each month. Sound Transit's
    weekday averages already exclude holidays.
    """
    return (
        pl.read_csv(filename, try_parse_dates=True)
        .filter(pl.col("mode") == "Link", pl.col("schedule_type") == "Weekday")
        .select(
            year=pl.col("month").dt.year(),
            month=pl.col("month").dt.month(),
            riders=pl.col("average_boardings").round().cast(pl.Int64),
        )
    )
