import polars as pl


def parse_muni_metro_weekday_ridership(filename: str) -> pl.DataFrame:
    """
    Get the average weekday Muni Metro boardings for each month. Muni Metro was
    suspended and replaced by buses from April to November 2020, so it has no rows for
    those months; they are filled in as zero.
    """
    weekdays = (
        pl.read_csv(filename)
        .filter(pl.col("Service Day of the Week") == "WEEKDAY")
        .select(
            date=pl.col("Month").str.to_date("%B %Y"),
            mode=pl.col("Transportation Mode"),
            riders=pl.col("Average Daily Boardings")
            .str.replace_all(",", "")
            .cast(pl.Int64),
        )
    )
    muni_metro = weekdays.filter(pl.col("mode") == "Muni Metro").select(
        "date", "riders"
    )

    return (
        weekdays.select("date")
        .unique()
        .join(muni_metro, on="date", how="left")
        .with_columns(pl.col("riders").fill_null(0))
        .sort("date")
        .select(
            year=pl.col("date").dt.year(),
            month=pl.col("date").dt.month(),
            riders="riders",
        )
    )
