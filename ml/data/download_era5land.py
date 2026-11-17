"""Download hourly ERA5-Land for Victoria from the Copernicus Climate Data Store.

One request per month, saved to data/historical/weather/era5land_raw/YYYY-MM/.
Resumable: months with a .done marker are skipped.

Usage:
  python ml/data/download_era5land.py --test               # Dec 2019 only, to check setup
  python ml/data/download_era5land.py 2012-06 2026-10      # a range of months
"""
import argparse
import calendar
import shutil
import time
import zipfile
from pathlib import Path

import cdsapi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "historical" / "weather" / "era5land_raw"
AREA = [-33.8, 140.9, -39.2, 150.1]  # north, west, south, east
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
    "volumetric_soil_water_layer_1",
]


def month_range(start: str, end: str):
    y, m = map(int, start.split("-"))
    y_end, m_end = map(int, end.split("-"))
    while (y, m) <= (y_end, m_end):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_month(client: cdsapi.Client, year: int, month: int) -> None:
    folder = OUT / f"{year}-{month:02d}"
    if (folder / ".done").exists():
        print(f"{year}-{month:02d}: already downloaded, skipping")
        return
    folder.mkdir(parents=True, exist_ok=True)
    n_days = calendar.monthrange(year, month)[1]
    request = {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": str(year),
        "month": f"{month:02d}",
        "day": [f"{d:02d}" for d in range(1, n_days + 1)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    print(f"{year}-{month:02d}: requesting (may queue for a while)...")
    tmp = folder / "download.tmp"
    client.retrieve("reanalysis-era5-land", request).download(str(tmp))

    if zipfile.is_zipfile(tmp):  # CDS may zip instant and accumulated variables separately
        with zipfile.ZipFile(tmp) as z:
            for name in z.namelist():
                if name.endswith(".nc"):
                    with z.open(name) as src, open(folder / Path(name).name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        tmp.unlink()
    else:
        tmp.rename(folder / "data.nc")

    (folder / ".done").touch()
    files = sorted(p.name for p in folder.glob("*.nc"))
    size_mb = sum(p.stat().st_size for p in folder.glob("*.nc")) / 1e6
    print(f"{year}-{month:02d}: saved {files} ({size_mb:.0f} MB)")


def fetch_with_retry(client: cdsapi.Client, year: int, month: int, attempts: int = 30) -> None:
    """Retry rejected or failed requests (e.g. Copernicus's queue limit) after a pause."""
    for attempt in range(1, attempts + 1):
        try:
            return fetch_month(client, year, month)
        except Exception as exc:
            text = str(exc)
            last_line = text.strip().splitlines()[-1][:150] if text.strip() else type(exc).__name__
            wait_min = 5 if ("queued" in text or "rejected" in text) else 2
            print(f"{year}-{month:02d}: attempt {attempt} failed ({last_line}); retrying in {wait_min} min")
            time.sleep(wait_min * 60)
    raise RuntimeError(f"{year}-{month:02d}: gave up after {attempts} attempts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start", nargs="?", help="first month, YYYY-MM")
    parser.add_argument("end", nargs="?", help="last month, YYYY-MM")
    parser.add_argument("--test", action="store_true", help="download December 2019 only")
    args = parser.parse_args()

    client = cdsapi.Client()
    if args.test:
        fetch_with_retry(client, 2019, 12)
        return
    if not (args.start and args.end):
        parser.error("give START and END months, or --test")
    for year, month in month_range(args.start, args.end):
        fetch_with_retry(client, year, month)


if __name__ == "__main__":
    main()
