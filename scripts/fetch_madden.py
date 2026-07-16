"""Download the Madden NFL 26 player ratings dataset from Kaggle.

EA doesn't publish a bulk ratings export, and scraping the in-game ratings
site directly wasn't necessary: this Kaggle mirror already has full
per-attribute breakdowns (speed, awareness, throw power, route running,
block shedding, etc.), not just an overall rating, for ~2k rostered players
as of Week 15 of the 2025 season roster updates.

Source: https://www.kaggle.com/datasets/flynn28/madden-26-week-15-player-ratings
"""

import os

DATASET = "flynn28/madden-26-week-15-player-ratings"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(DATASET, path=RAW_DIR, unzip=True)

    for f in os.listdir(RAW_DIR):
        if f.endswith(".csv"):
            print("downloaded:", os.path.join(RAW_DIR, f))


if __name__ == "__main__":
    main()
