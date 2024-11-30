import os
from datetime import datetime

import requests
from tqdm import tqdm

SFMTA_MUNI_RIDERSHIP_URL = (
    "https://transtat.sfmta.com/t/public/views/Goal2Dashboards/RidershipTable.csv"
)


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


if __name__ == "__main__":
    main()
