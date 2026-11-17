"""Match Victorian FIRMS detections to DataVic fire history perimeters.

Input:  data/historical/processed/firms_victoria.parquet
        data/historical/fire_history/**/FIRE_HISTORY.shp  (VicGrid, EPSG:7899)
Output: data/historical/processed/fire_history.parquet     (slim perimeters, reused for features)
        data/historical/processed/firms_victoria_matched.parquet
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "historical" / "processed"
FH_PATH = next((ROOT / "data" / "historical" / "fire_history").rglob("FIRE_HISTORY.shp"))

# Days relative to a fire's START_DATE in which a hotspot counts as that fire.
BURN_WINDOW = (-2, 10)
BUSHFIRE_WINDOW = (-2, 90)
BUSHFIRE_EARLY_WINDOW = (-120, -3)  # recorded START_DATE can lag the first detections
KEEP = ["FIREKEY", "FIRETYPE", "SEASON", "START_DATE", "AREA_HA", "TREAT_TYPE", "CAUSE", "FIRE_SVRTY"]


def main() -> None:
    print("Reading fire history (this can take a minute)...")
    fh = gpd.read_file(FH_PATH, columns=KEEP)
    print(f"  {len(fh):,} polygons, {fh['FIREKEY'].nunique():,} distinct fires")
    fh.to_parquet(PROC / "fire_history.parquet")

    df = pd.read_parquet(PROC / "firms_victoria.parquet").reset_index(drop=True)
    pts = gpd.GeoDataFrame(
        {"row": df.index, "local_date": pd.to_datetime(df["local_date"]),
         "season_end": df["season"].str[:4].astype(int) + 1},
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs=4326,
    ).to_crs(fh.crs)

    print("Matching detections to perimeters...")
    
    hits = gpd.sjoin(pts, fh[["FIREKEY", "FIRETYPE", "START_DATE", "SEASON", "geometry"]],
                     predicate="within", how="inner")
    days = (hits["local_date"] - hits["START_DATE"]).dt.days
    is_bush = hits["FIRETYPE"] == "Bushfire"
    burns = hits[(hits["FIRETYPE"] == "Burn") & days.between(*BURN_WINDOW)]
    bush = hits[is_bush & days.between(*BUSHFIRE_WINDOW)]
    bush_early = hits[is_bush & days.between(*BUSHFIRE_EARLY_WINDOW)
                      & (hits["season_end"] == hits["SEASON"])]

    df["fh_planned_burn"] = df.index.isin(burns["row"])
    in_window = df.index.isin(bush["row"])
    early_only = df.index.isin(bush_early["row"]) & ~in_window
    df["fh_bushfire_early"] = early_only & ~df["fh_planned_burn"]
    df["fh_bushfire"] = in_window | df["fh_bushfire_early"]
    keys = pd.concat([bush, bush_early]).groupby("row")["FIREKEY"].first()
    df["fh_firekey"] = keys.reindex(df.index)

    print("Detections matched only through the early window, per season:")
    print(df[df["fh_bushfire_early"]].groupby("season").size().to_string(), "\n")

    df["hist_label"] = np.select(
        [df["type_name"].eq("static_land_source") | df["type_name"].eq("offshore"),
         df["fh_bushfire"],
         df["fh_planned_burn"]],
        ["static", "bushfire", "planned_burn"],
        default="unmatched",
    )

    out_path = PROC / "firms_victoria_matched.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Saved -> {out_path.relative_to(ROOT)}\n")

    print("Labels overall:")
    print(df["hist_label"].value_counts().to_string(), "\n")
    table = df.groupby(["season", "hist_label"]).size().unstack(fill_value=0)
    table["matched_share"] = ((table.get("bushfire", 0) + table.get("planned_burn", 0))
                              / table.sum(axis=1)).map("{:.0%}".format)
    print("Per season:")
    print(table.to_string(), "\n")
    month = pd.to_datetime(df["local_date"]).dt.month
    print("Planned-burn detections by month (expect autumn and spring peaks):")
    print(df[df["hist_label"] == "planned_burn"].groupby(month).size().to_string())


if __name__ == "__main__":
    main()
