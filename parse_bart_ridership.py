import os

import polars as pl


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
        filename,
        sheet_name="Total Trips",
        read_options={
            "header_row": 3,
        },
    )


def original_data_dir() -> str:
    data_repo = os.environ["DATA_REPO"]
    return os.path.join(data_repo, "original")


def main():
    original_dir = original_data_dir()
    bart_ridership_oct_df = parse_bart_ridership(
        os.path.join(original_dir, "bart", "2024-11-29-ridership-202410.xlsx"),
    )
    print(bart_ridership_oct_df)


if __name__ == "__main__":
    main()
