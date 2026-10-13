import re

import fastexcel
import polars as pl

from data_files import read_compressed

STATION_CODE_RE = re.compile(r"^[A-Z0-9]{2}$")
WEEKDAY_SHEET_RE = re.compile(r"weekday|wkdy", re.IGNORECASE)


def parse_station_code(code: str) -> str:
    """
    BART two-letter station codes, parsed from
    https://www.bart.gov/sites/default/files/docs/station-names.xls
    """
    match code:
        case "RM":
            return "Richmond"
        case "EN":
            return "El Cerrito Del Norte"
        case "EP":
            return "El Cerrito Plaza"
        case "NB":
            return "North Berkeley"
        case "BK":
            return "Berkeley"
        case "AS":
            return "Ashby"
        case "MA":
            return "MacArthur"
        case "19":
            return "19th Street Oakland"
        case "12":
            return "12th Street / Oakland City Center"
        case "LM":
            return "Lake Merritt"
        case "FV":
            return "Fruitvale"
        case "CL":
            return "Coliseum"
        case "SL":
            return "San Leandro"
        case "BF":
            return "Bayfair"
        case "HY":
            return "Hayward"
        case "SH":
            return "South Hayward"
        case "UC":
            return "Union City"
        case "FM":
            return "Fremont"
        case "CN":
            return "Concord"
        case "PH":
            return "Pleasant Hill"
        case "WC":
            return "Walnut Creek"
        case "LF":
            return "Lafayette"
        case "OR":
            return "Orinda"
        case "RR":
            return "Rockridge"
        case "OW":
            return "West Oakland"
        case "EM":
            return "Embarcadero"
        case "MT":
            return "Montgomery Street"
        case "PL":
            return "Powell Street"
        case "CC":
            return "Civic Center"
        case "16":
            return "16th Street Mission"
        case "24":
            return "24th Street Mission"
        case "GP":
            return "Glen Park"
        case "BP":
            return "Balboa Park"
        case "DC":
            return "Daly City"
        case "CM":
            return "Colma"
        case "CV":
            return "Castro Valley"
        case "ED":
            return "Dublin / Pleasanton"
        case "NC":
            return "North Concord"
        case "WP":
            return "Pittsburg / Bay Point"
        case "SS":
            return "South San Francisco"
        case "SB":
            return "San Bruno"
        case "SO":
            return "San Francisco International Airport"
        case "MB":
            return "Millbrae"
        case "WD":
            return "West Dublin / Pleasanton"
        case "OA":
            return "Oakland International Airport"
        case "WS":
            return "Warm Springs"
        case "AN":
            return "Antioch"
        case "PC":
            return "Pittsburg Center"
        case "ML":
            return "Milpitas"
        case "BE":
            return "Berryessa / North San José"
        case _:
            raise AssertionError(f"Unknown station code: {code}")


def parse_bart_ridership(filename: str) -> pl.DataFrame:
    return pl.read_excel(
        read_compressed(filename),
        sheet_name="Total Trips",
        read_options={
            "header_row": 3,
        },
    )


def is_station_code(cell: str | None) -> bool:
    return cell is not None and bool(STATION_CODE_RE.match(cell.removesuffix(".0")))


def parse_bart_weekday_ridership(filename: str) -> float:
    """
    Sum the average weekday origin-destination matrix in a BART monthly ridership
    file. The sheet layout has changed over the years, so this finds the header row
    of entry station codes and sums the cells whose row and column are both station
    codes, which skips any entry/exit total rows and columns.
    """
    reader = fastexcel.read_excel(read_compressed(filename))
    sheet_name = next(
        name for name in reader.sheet_names if WEEKDAY_SHEET_RE.search(name)
    )
    rows = (
        reader.load_sheet(sheet_name, header_row=None, dtypes="string")
        .to_polars()
        .rows()
    )

    header_index = max(
        range(min(10, len(rows))),
        key=lambda i: sum(is_station_code(cell) for cell in rows[i]),
    )
    station_columns = [
        j for j, cell in enumerate(rows[header_index]) if is_station_code(cell)
    ]

    total = 0.0
    for row in rows[header_index + 1 :]:
        if is_station_code(row[0]):
            total += sum(float(row[j]) for j in station_columns if row[j] is not None)
    return total
