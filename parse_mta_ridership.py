import holidays
import polars as pl


def parse_nyc_subway_weekday_ridership(filename: str) -> pl.DataFrame:
    """
    Average the daily subway ridership over weekdays that aren't federal holidays for
    each month, which matches how the MTA reports average weekday ridership. Months
    missing any days are dropped.
    """
    df = pl.read_csv(filename, try_parse_dates=True)
    years = range(df["date"].min().year, df["date"].max().year + 1)
    federal_holidays = list(holidays.US(years=years))

    return (
        df.with_columns(month_start=pl.col("date").dt.truncate("1mo"))
        .group_by("month_start")
        .agg(
            days=pl.len(),
            riders=pl.col("riders")
            .filter(
                (pl.col("date").dt.weekday() <= 5)
                & ~pl.col("date").is_in(federal_holidays)
            )
            .mean(),
        )
        .filter(pl.col("days") == pl.col("month_start").dt.month_end().dt.day())
        .sort("month_start")
        .select(
            year=pl.col("month_start").dt.year(),
            month=pl.col("month_start").dt.month(),
            riders=pl.col("riders").round().cast(pl.Int64),
        )
    )
