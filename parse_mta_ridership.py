import holidays
import polars as pl


def parse_nyc_subway_weekday_ridership(filename: str) -> pl.DataFrame:
    """
    Average the daily subway ridership over weekdays that aren't federal holidays for
    each month, which matches how the MTA reports average weekday ridership.

    The turnstile data is missing a few whole weeks in 2015 and 2016, so months are kept
    as long as at least half of their weekdays have data. The latest month is dropped
    unless the data covers all of it.
    """
    df = pl.read_csv(filename, try_parse_dates=True)
    first_date, last_date = df["date"].min(), df["date"].max()
    years = range(first_date.year, last_date.year + 1)
    federal_holidays = list(holidays.US(years=years))
    is_weekday = (pl.col("date").dt.weekday() <= 5) & ~pl.col("date").is_in(
        federal_holidays
    )

    expected_weekdays = (
        pl.date_range(first_date, last_date, "1d", eager=True)
        .alias("date")
        .to_frame()
        .group_by(month_start=pl.col("date").dt.truncate("1mo"))
        .agg(expected_weekdays=is_weekday.sum())
    )

    return (
        df.group_by(month_start=pl.col("date").dt.truncate("1mo"))
        .agg(
            weekdays=is_weekday.sum(),
            riders=pl.col("riders").filter(is_weekday).mean(),
        )
        .join(expected_weekdays, on="month_start")
        .filter(
            pl.col("month_start").dt.month_end() <= last_date,
            pl.col("weekdays") * 2 >= pl.col("expected_weekdays"),
        )
        .sort("month_start")
        .select(
            year=pl.col("month_start").dt.year(),
            month=pl.col("month_start").dt.month(),
            riders=pl.col("riders").round().cast(pl.Int64),
        )
    )
