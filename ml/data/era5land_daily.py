"""Convert hourly ERA5-Land months into daily fire weather per ERA5-Land land point.

Days are Melbourne local days. A month is converted only once the previous month has
downloaded too (its last hours belong to this month's first local day).

Input:  data/historical/weather/era5land_raw/YYYY-MM/*.nc
Output: data/historical/weather/era5land_daily/YYYY-MM.parquet   one row per land point per local day
        data/historical/weather/era5land_points.parquet          point_id, lat, lon
        data/historical/processed/cell_to_era5.parquet           nearest land point for each 2 km cell

Usage:
  python ml/data/era5land_daily.py --test     # Dec 2019 only, into era5land_daily_test/, prints a check
  python ml/data/era5land_daily.py            # every downloaded month not yet converted
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
WEATHER = ROOT / "data" / "historical" / "weather"
RAW = WEATHER / "era5land_raw"
PROC = ROOT / "data" / "historical" / "processed"
TZ = "Australia/Melbourne"
VARS = ["t2m", "d2m", "u10", "v10", "tp", "swvl1"]
TAIL_HOURS = 16  # hours taken from the end of the previous month


def load_month(folder: Path) -> xr.Dataset:
    parts = []
    for f in sorted(folder.glob("*.nc")):
        ds = xr.open_dataset(f)
        ds = ds.drop_vars([v for v in ("expver", "number") if v in ds.variables])
        parts.append(ds)
    ds = xr.merge(parts, compat="override")
    if "valid_time" in ds.dims:
        ds = ds.rename({"valid_time": "time"})
    return ds.sortby("time")


def arrays(ds: xr.Dataset):
    return {v: ds[v].values.astype(np.float32) for v in VARS}, pd.DatetimeIndex(ds["time"].values)


def hourly_precip_mm(tp: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
    """ERA5-Land tp accumulates from 00 UTC; the 00 UTC value holds the whole previous UTC day."""
    inc = np.full_like(tp, np.nan)
    inc[1:] = tp[1:] - tp[:-1]
    first_hour = np.asarray(times.hour == 1)
    inc[first_hour] = tp[first_hour]
    return np.clip(inc, 0, None) * 1000.0


def sat_vp(t_c):
    return 6.112 * np.exp(17.62 * t_c / (243.12 + t_c))


def convert_month(month_dir: Path, prev_dir: Path | None) -> pd.DataFrame:
    ds = load_month(month_dir)
    arr, times = arrays(ds)
    if prev_dir is not None:
        parr, ptimes = arrays(load_month(prev_dir).isel(time=slice(-TAIL_HOURS, None)))
        arr = {v: np.concatenate([parr[v], arr[v]]) for v in VARS}
        times = ptimes.append(times)

    t = arr["t2m"] - 273.15
    rh = np.clip(100 * sat_vp(arr["d2m"] - 273.15) / sat_vp(t), 0, 100)
    ws = np.hypot(arr["u10"], arr["v10"]) * 3.6
    precip = hourly_precip_mm(arr["tp"], times)
    ffdi10 = 2 * np.exp(-0.45 + 0.987 * np.log(10) - 0.0345 * rh + 0.0338 * t + 0.0234 * ws)

    local_day = times.tz_localize("UTC").tz_convert(TZ).normalize().tz_localize(None)
    year, month = map(int, month_dir.name.split("-"))
    n_points = arr["t2m"].shape[1] * arr["t2m"].shape[2]
    frames = []
    for day in pd.unique(local_day):
        day = pd.Timestamp(day)
        if (day.year, day.month) != (year, month):
            continue
        idx = np.flatnonzero(local_day == day)
        if len(idx) < 23 or np.isnan(precip[idx]).any(axis=0).all():
            continue  # incomplete local day (previous month missing)
        k = ws[idx].argmax(axis=0)[None]
        u = np.take_along_axis(arr["u10"][idx], k, axis=0)[0]
        v = np.take_along_axis(arr["v10"][idx], k, axis=0)[0]
        stats = {
            "tmax": t[idx].max(axis=0), "tmin": t[idx].min(axis=0),
            "rhmin": rh[idx].min(axis=0),
            "wmax_kmh": ws[idx].max(axis=0),
            "wdir_at_wmax": (np.degrees(np.arctan2(-u, -v)) + 360) % 360,
            "precip_mm": precip[idx].sum(axis=0),
            "swvl1": arr["swvl1"][idx].mean(axis=0),
            "ffdi10_max": ffdi10[idx].max(axis=0),
        }
        df = pd.DataFrame({k2: v2.reshape(-1).astype(np.float32) for k2, v2 in stats.items()})
        df.insert(0, "point_id", np.arange(n_points, dtype=np.int32))
        df.insert(0, "date", day)
        frames.append(df[df["tmax"].notna()])  # land points only
    return pd.concat(frames, ignore_index=True)


def write_points_and_mapping(month_dir: Path) -> None:
    ds = load_month(month_dir)
    lat, lon = ds["latitude"].values, ds["longitude"].values
    glat, glon = np.meshgrid(lat, lon, indexing="ij")
    land = ~np.isnan(ds["t2m"].isel(time=12).values)
    points = pd.DataFrame({"point_id": np.arange(glat.size, dtype=np.int32),
                           "lat": glat.ravel(), "lon": glon.ravel(), "land": land.ravel()})
    points_path = WEATHER / "era5land_points.parquet"
    if points_path.exists():
        old = pd.read_parquet(points_path)
        if not np.allclose(old[["lat", "lon"]].to_numpy(), points[["lat", "lon"]].to_numpy()):
            raise SystemExit("ERA5-Land grid differs from the saved points file")
    points.to_parquet(points_path, index=False)

    grid = pd.read_parquet(PROC / "grid_2km.parquet", columns=["cell_id", "lat", "lon"])
    lp = points[points["land"]]
    scale = np.cos(np.radians(-37.0))
    tree = cKDTree(np.c_[lp["lon"] * scale, lp["lat"]])
    dist, i = tree.query(np.c_[grid["lon"] * scale, grid["lat"]])
    mapping = pd.DataFrame({"cell_id": grid["cell_id"], "point_id": lp["point_id"].to_numpy()[i],
                            "dist_km": (dist * 111.2).astype(np.float32)})
    mapping.to_parquet(PROC / "cell_to_era5.parquet", index=False)
    print(f"Points: {len(points):,} ({int(land.sum()):,} land). "
          f"Cells mapped: {len(mapping):,}; max distance {mapping['dist_km'].max():.1f} km")


def sanity_check(df: pd.DataFrame) -> None:
    points = pd.read_parquet(WEATHER / "era5land_points.parquet")
    places = {"Mallacoota": (149.76, -37.56), "Melbourne": (144.96, -37.81), "Mildura": (142.16, -34.19)}
    lp = points[points["land"]]
    for name, (x, y) in places.items():
        pid = lp.iloc[((lp["lon"] - x) ** 2 + (lp["lat"] - y) ** 2).argmin()]["point_id"]
        s = df[df["point_id"] == pid].set_index("date")
        print(f"\n{name} (point {pid}), last 8 days:")
        print(s[["tmax", "rhmin", "wmax_kmh", "wdir_at_wmax", "precip_mm", "ffdi10_max"]].tail(8).round(1).to_string())
    total = df.groupby("point_id")["precip_mm"].sum()
    print(f"\nMonthly rain across land points (mm): median {total.median():.1f}, "
          f"min {total.min():.1f}, max {total.max():.1f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    done = sorted(p for p in RAW.iterdir() if (p / ".done").exists())
    if not done:
        raise SystemExit("No downloaded months yet")
    write_points_and_mapping(done[0])

    if args.test:
        month = RAW / "2019-12"
        prev = RAW / "2019-11"
        df = convert_month(month, prev if (prev / ".done").exists() else None)
        out_dir = WEATHER / "era5land_daily_test"
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_dir / "2019-12.parquet", index=False)
        print(f"Test: {df['date'].nunique()} local days x {df['point_id'].nunique():,} land points")
        sanity_check(df)
        return

    out_dir = WEATHER / "era5land_daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    names = [p.name for p in done]
    first = min(names)
    converted = 0
    for month in done:
        out = out_dir / f"{month.name}.parquet"
        if out.exists():
            continue
        y, m = map(int, month.name.split("-"))
        prev_name = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
        prev = RAW / prev_name
        if not (prev / ".done").exists() and month.name != first:
            print(f"{month.name}: waiting for {prev_name} to download")
            continue
        df = convert_month(month, prev if (prev / ".done").exists() else None)
        df.to_parquet(out, index=False)
        converted += 1
        print(f"{month.name}: {df['date'].nunique()} days -> {out.relative_to(ROOT)}")
    print(f"Converted {converted} month(s).")


if __name__ == "__main__":
    main()
