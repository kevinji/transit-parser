import polars as pl


def parse_muni_weekday_ridership(filename: str) -> pl.DataFrame:
    """
    Sum the average weekday boardings across all Muni transportation modes for each
    month. The set of modes changes over time (e.g. cable cars are folded into
    "Other" from April 2020), but each month's modes cover the whole system.
    """
    return (
        pl.read_csv(filename)
        .filter(pl.col("Service Day of the Week") == "WEEKDAY")
        .select(
            date=pl.col("Month").str.to_date("%B %Y"),
            riders=pl.col("Average Daily Boardings")
            .str.replace_all(",", "")
            .cast(pl.Int64),
        )
        .group_by("date")
        .agg(pl.col("riders").sum())
        .sort("date")
        .select(
            year=pl.col("date").dt.year(),
            month=pl.col("date").dt.month(),
            riders="riders",
        )
    )
