"""Build a clean Victorian FIRMS fire history (2000-present) from the archive downloads.

Input:  data/historical/firms/**/fire_archive_*.csv and fire_nrt_*.csv
Output: data/historical/processed/firms_vic.parquet
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "historical" / "firms"
OUT = ROOT / "data" / "historical" / "processed"

WEST, SOUTH, EAST, NORTH = 140.9, -39.2, 150.0, -33.9  # Victoria bounding box
TYPE_NAMES = {0: "vegetation_fire", 1: "volcano", 2: "static_land_source", 3: "offshore"}


def load_all() -> pd.DataFrame:
    frames = []
    for path in sorted(RAW.rglob("fire_*.csv")):
        df = pd.read_csv(path, dtype={"acq_time": str, "confidence": str, "version": str})
        df["file_kind"] = "archive" if "archive" in path.name else "nrt"
        df["source_file"] = str(path.relative_to(ROOT))
        frames.append(df)
        print(f"loaded {len(df):>9,} rows  {path.name}")
    return pd.concat(frames, ignore_index=True)


def confidence_level(raw: pd.Series) -> pd.Series:
    """VIIRS uses l/n/h; MODIS uses 0-100 (low <30, nominal 30-79, high 80+)."""
    s = raw.astype(str).str.strip().str.lower()
    from_letters = s.map({"l": "low", "n": "nominal", "h": "high"})
    numbers = pd.to_numeric(s, errors="coerce")
    from_numbers = pd.cut(numbers, bins=[0, 30, 80, 101], right=False,
                          labels=["low", "nominal", "high"]).astype(object)
    return from_letters.fillna(from_numbers).fillna("unknown")


def fire_season(local_dates: pd.Series) -> pd.Series:
    """Australian fire seasons run July-June: 2019-12-31 -> '2019-20'."""
    d = pd.to_datetime(local_dates)
    start = d.dt.year.where(d.dt.month >= 7, d.dt.year - 1)
    return start.astype(str) + "-" + ((start + 1) % 100).astype(str).str.zfill(2)


def main() -> None:
    df = load_all()
    df = df[df["longitude"].between(WEST, EAST) & df["latitude"].between(SOUTH, NORTH)].copy()

    df["sensor"] = df["instrument"].replace({"SNPP": "VIIRS"})
    hhmm = df["acq_time"].str.zfill(4)
    df["acq_utc"] = pd.to_datetime(df["acq_date"] + " " + hhmm, format="%Y-%m-%d %H%M", utc=True)
    df["acq_local"] = df["acq_utc"].dt.tz_convert("Australia/Melbourne")
    df["local_date"] = df["acq_local"].dt.date
    df["season"] = fire_season(df["local_date"])
    df["confidence_level"] = confidence_level(df["confidence"])
    df["type_name"] = df["type"].map(TYPE_NAMES)  # empty for nrt rows

    # Where archive and nrt overlap, keep the cleaner archive row ("archive" sorts first).
    df = (df.sort_values("file_kind")
            .drop_duplicates(["satellite", "latitude", "longitude", "acq_utc"], keep="first")
            .sort_values("acq_utc"))

    cols = ["sensor", "satellite", "latitude", "longitude", "acq_utc", "acq_local", "local_date",
            "season", "confidence", "confidence_level", "brightness", "frp", "daynight",
            "type", "type_name", "version", "file_kind", "source_file"]
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "firms_vic.parquet"
    df[cols].to_parquet(out_path, index=False)

    print(f"\nSaved {len(df):,} Victorian detections -> {out_path.relative_to(ROOT)}")
    print(f"Date range: {df['local_date'].min()} to {df['local_date'].max()}\n")
    print("By sensor and file:\n", df.groupby(["sensor", "file_kind"]).size().to_string(), "\n")
    print("By type (archive only):\n", df["type_name"].value_counts(dropna=False).to_string(), "\n")
    print("Vegetation-fire detections per season:")
    veg = df[(df["type_name"] == "vegetation_fire") | df["type_name"].isna()]
    print(veg.groupby(["season", "sensor"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
