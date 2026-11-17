"""Keep only FIRMS detections inside Victoria's official boundary (ABS ASGS 2021).

Input:  data/historical/processed/firms_vic.parquet  (bounding-box filtered)
        data/historical/boundaries/STE_2021_AUST_SHP_GDA2020.zip
Output: data/historical/processed/firms_victoria.parquet
        data/historical/processed/vic_boundary.geojson  (reused later for the grid and labels)
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_ZIP = ROOT / "data" / "historical" / "boundaries" / "STE_2021_AUST_SHP_GDA2020.zip"
PROC = ROOT / "data" / "historical" / "processed"


def load_victoria():
    states = gpd.read_file(f"zip://{BOUNDARY_ZIP}")
    if "STE_NAME21" not in states.columns:
        raise SystemExit(f"Expected column STE_NAME21, found: {list(states.columns)}")
    vic = states[states["STE_NAME21"] == "Victoria"][["STE_NAME21", "geometry"]]
    if vic.empty:
        raise SystemExit(f"No 'Victoria' row. Names found: {states['STE_NAME21'].tolist()}")
    vic = vic.to_crs(4326)  # GDA2020 -> WGS84, to match FIRMS coordinates
    vic.to_file(PROC / "vic_boundary.geojson", driver="GeoJSON")
    return vic.geometry.union_all() if hasattr(vic.geometry, "union_all") else vic.geometry.unary_union


def main() -> None:
    df = pd.read_parquet(PROC / "firms_vic.parquet")
    vic = load_victoria()
    shapely.prepare(vic)  # speeds up the point-in-polygon test
    inside = shapely.contains_xy(vic, df["longitude"].to_numpy(), df["latitude"].to_numpy())

    out = df[inside]
    out_path = PROC / "firms_victoria.parquet"
    out.to_parquet(out_path, index=False)
    print(f"Inside Victoria: {inside.sum():,} of {len(df):,} detections ({inside.mean():.0%})")
    print(f"Saved -> {out_path.relative_to(ROOT)}\n")

    veg = lambda d: d[(d["type_name"] == "vegetation_fire") | d["type_name"].isna()]
    compare = pd.DataFrame({
        "box": veg(df).groupby("season").size(),
        "victoria": veg(out).groupby("season").size(),
    }).fillna(0).astype(int)
    compare["share_in_vic"] = (compare["victoria"] / compare["box"]).map("{:.0%}".format)
    print("Vegetation-fire detections per season (MODIS + VIIRS):")
    print(compare.to_string())


if __name__ == "__main__":
    main()
