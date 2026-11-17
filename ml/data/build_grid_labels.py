"""Build the 2 km Victorian grid and daily fire labels per cell.

Input:  data/historical/processed/vic_boundary.geojson
        data/historical/processed/firms_victoria_matched.parquet
Output: data/historical/processed/grid_2km.parquet      (cell polygons, VicGrid EPSG:7899)
        data/historical/processed/grid_meta.json        (origin and size, to place live data)
        data/historical/processed/labels_daily.parquet  (one row per cell-day with activity)

Labels: 1 = fire, -1 = ignore (not used in training). Absent cell-days = 0 (no fire).
  label_a (strict):   fire = mapped bushfire detection
  label_b (seasonal): fire = mapped bushfire, or unmatched detection in Nov-Feb
  Planned burns, static sources, other unmatched and low-confidence detections -> ignore.
"""
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "historical" / "processed"
CELL_M = 2000
CRS = 7899  # VicGrid GDA2020, metres
LAST_SEASON_WITH_FIRE_HISTORY = "2024-25"
SUMMER_MONTHS = {11, 12, 1, 2}


def build_grid() -> tuple[gpd.GeoDataFrame, dict]:
    vic = gpd.read_file(PROC / "vic_boundary.geojson").to_crs(CRS)
    vic = vic.geometry.union_all() if hasattr(vic.geometry, "union_all") else vic.geometry.unary_union
    minx, miny, maxx, maxy = vic.bounds
    x0, y0 = math.floor(minx / CELL_M) * CELL_M, math.floor(miny / CELL_M) * CELL_M
    ncols, nrows = math.ceil((maxx - x0) / CELL_M), math.ceil((maxy - y0) / CELL_M)

    cols, rows = (a.ravel() for a in np.meshgrid(np.arange(ncols), np.arange(nrows)))
    boxes = shapely.box(x0 + cols * CELL_M, y0 + rows * CELL_M,
                        x0 + (cols + 1) * CELL_M, y0 + (rows + 1) * CELL_M)
    shapely.prepare(vic)
    keep = shapely.intersects(vic, boxes)

    grid = gpd.GeoDataFrame(
        {"cell_id": rows[keep] * ncols + cols[keep], "row": rows[keep], "col": cols[keep]},
        geometry=boxes[keep], crs=CRS,
    )
    centres = grid.geometry.centroid.to_crs(4326)
    grid["lon"], grid["lat"] = centres.x.round(5), centres.y.round(5)
    meta = {"crs": f"EPSG:{CRS}", "cell_m": CELL_M, "x0": x0, "y0": y0, "ncols": ncols, "nrows": nrows}
    return grid, meta


def assign_cells(lon: pd.Series, lat: pd.Series, meta: dict) -> np.ndarray:
    pts = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=4326).to_crs(CRS)
    col = np.floor((pts.x.to_numpy() - meta["x0"]) / meta["cell_m"]).astype(int)
    row = np.floor((pts.y.to_numpy() - meta["y0"]) / meta["cell_m"]).astype(int)
    return row * meta["ncols"] + col


def main() -> None:
    grid, meta = build_grid()
    grid.to_parquet(PROC / "grid_2km.parquet")
    (PROC / "grid_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Grid: {len(grid):,} cells of {CELL_M // 1000} km  ({meta['ncols']} x {meta['nrows']} bounding grid)")

    df = pd.read_parquet(PROC / "firms_victoria_matched.parquet")
    df["cell_id"] = assign_cells(df["longitude"], df["latitude"], meta)
    df = df[df["cell_id"].isin(grid["cell_id"])].copy()

    static_days = df[df["type_name"].eq("static_land_source")].groupby("cell_id")["local_date"].nunique()
    static_cells = sorted(static_days[static_days >= 3].index)
    pd.DataFrame({"cell_id": static_cells}).to_parquet(PROC / "static_cells.parquet", index=False)
    in_static = df["cell_id"].isin(static_cells)
    print(f"Static cells (industrial heat on 3+ days): {len(static_cells)}")

    month = pd.to_datetime(df["local_date"]).dt.month
    low = df["confidence_level"].eq("low")
    label = df["hist_label"]
    df["pos_a"] = label.eq("bushfire") & ~low
    df["pos_b"] = df["pos_a"] | (label.eq("unmatched") & month.isin(SUMMER_MONTHS) & ~low & ~in_static)
    for name in ["bushfire", "unmatched", "planned_burn", "static"]:
        df[f"n_{name}"] = label.eq(name).astype(int)

    labels = df.groupby(["cell_id", "local_date", "season"], as_index=False).agg(
        n_detections=("hist_label", "size"),
        n_bushfire=("n_bushfire", "sum"),
        n_unmatched=("n_unmatched", "sum"),
        n_planned_burn=("n_planned_burn", "sum"),
        n_static=("n_static", "sum"),
        pos_a=("pos_a", "max"),
        pos_b=("pos_b", "max"),
    )
    labels["label_a"] = np.where(labels["pos_a"], 1, -1).astype(float)
    labels.loc[labels["season"] > LAST_SEASON_WITH_FIRE_HISTORY, "label_a"] = np.nan
    labels["label_b"] = np.where(labels["pos_b"], 1, -1)
    labels = labels.drop(columns=["pos_a", "pos_b"])
    labels.to_parquet(PROC / "labels_daily.parquet", index=False)
    print(f"Labels: {len(labels):,} cell-days with activity -> labels_daily.parquet\n")

    cell_days = len(grid) * 365
    summary = labels.groupby("season").agg(
        fire_a=("label_a", lambda s: int((s == 1).sum())),
        fire_b=("label_b", lambda s: int((s == 1).sum())),
        ignore_b=("label_b", lambda s: int((s == -1).sum())),
    )
    summary["fire_b_per_10k_cell_days"] = (summary["fire_b"] / cell_days * 1e4).round(1)
    print("Fire cell-days per season (label A strict, label B seasonal):")
    print(summary.to_string())


if __name__ == "__main__":
    main()
