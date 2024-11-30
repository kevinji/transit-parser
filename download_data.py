import os
from datetime import datetime

import requests
from tqdm import tqdm

SFMTA_MUNI_RIDERSHIP_URL = (
    "https://transtat.sfmta.com/t/public/views/Goal2Dashboards/RidershipTable.csv"
)

# TODO: Support .zip files for previous years:
# https://www.bart.gov/about/reports/ridership
BART_RIDERSHIP_URL_BY_2024_MONTH = {
    1: "https://www.bart.gov/sites/default/files/2024-03/Ridership_202401%201.xlsx",
    2: "https://www.bart.gov/sites/default/files/2024-03/Ridership_202402.xlsx",
    3: "https://www.bart.gov/sites/default/files/2024-04/Ridership_202403.xlsx",
    4: "https://www.bart.gov/sites/default/files/2024-05/Ridership_202404.xlsx",
    5: "https://www.bart.gov/sites/default/files/2024-06/Ridership_202405.xlsx",
    6: "https://www.bart.gov/sites/default/files/2024-07/Ridership_202406.xlsx",
    7: "https://www.bart.gov/sites/default/files/2024-08/Ridership_202407.xlsx",
    8: "https://www.bart.gov/sites/default/files/2024-09/Ridership_202408.xlsx",
    9: "https://www.bart.gov/sites/default/files/2024-11/Ridership_202409.xlsx",
    10: "https://www.bart.gov/sites/default/files/2024-11/Ridership_202410.xlsx",
}


def download_file(url: str, filename: str):
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))

    with (
        open(filename, "wb") as f,
        tqdm(
            desc=os.path.basename(filename),
            total=total_size,
            unit="iB",
            unit_scale=True,
        ) as pbar,
    ):
        for chunk in response.iter_content(chunk_size=8192):
            size = f.write(chunk)
            pbar.update(size)


def original_data_dir() -> str:
    data_repo = os.environ["DATA_REPO"]
    return os.path.join(data_repo, "original")


def main():
    original_dir = original_data_dir()
    today = datetime.today().strftime("%Y-%m-%d")

    download_file(
        SFMTA_MUNI_RIDERSHIP_URL,
        os.path.join(original_dir, "sfmta", f"{today}-ridership.csv"),
    )
    for month, bart_ridership_url in BART_RIDERSHIP_URL_BY_2024_MONTH.items():
        download_file(
            bart_ridership_url,
            os.path.join(
                original_dir, "bart", f"{today}-ridership-2024{month:02d}.xlsx"
            ),
        )


if __name__ == "__main__":
    main()
