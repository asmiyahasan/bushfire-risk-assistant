"""Fire-history features for the modelling sample (no weather needed).

Input:  data/historical/processed/ sample_24h, labels_daily, grid_2km, grid_meta.json,
        static_cells, fire_history
Output: data/historical/processed/features_fire.parquet  (one row per sample row, keyed by cell_id + target_date)

Timing rule: every feature uses information up to the END of the day before issue_date
(issue is 6 am on issue_date; target is the next day). Nothing from the issue day or target day leaks in.
Activity = detections matched to a bushfire + unmatched detections outside static cells
(planned burns and static sources excluded, as they can be identified live too).
"""
import json
from collections import deque
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "historical" / "processed"
CELL_KM = 2.0
WINDOWS = (1, 3, 7)            # days of past activity
RADII = {"nbr5": 2, "nbr10": 5}  # half-width in cells: 5x5 (~10 km) and 11x11 (~22 km) squares
MAX_DIST_KM = 100.0


def box_sum(arr: np.ndarray, half: int) -> np.ndarray:
    size = 2 * half + 1
    return ndimage.uniform_filter(arr, size=size, mode="constant") * size * size


def activity_features(sample, r, c, nr, nc, static_cells):
    D0 = sample["feature_day"].min() - pd.Timedelta(days=max(WINDOWS))
    D1 = sample["feature_day"].max()
    n_days = (D1 - D0).days + 1

    lab = pd.read_parquet(PROC / "labels_daily.parquet")
    lab["date"] = pd.to_datetime(lab["local_date"])
    lab = lab[lab["date"].between(D0, D1)].copy()
    unmatched = np.where(lab["cell_id"].isin(static_cells), 0, lab["n_unmatched"])
    lab["active"] = lab["n_bushfire"] + unmatched
    lab = lab[lab["active"] > 0]
    l_day = (lab["date"] - D0).dt.days.to_numpy()
    l_r, l_c = (lab["cell_id"] // nc).to_numpy(), (lab["cell_id"] % nc).to_numpy()
    l_v = lab["active"].to_numpy(np.float32)
    l_ord = np.argsort(l_day, kind="stable")
    l_lo = np.searchsorted(l_day[l_ord], np.arange(n_days))
    l_hi = np.searchsorted(l_day[l_ord], np.arange(n_days), side="right")

    s_day = (sample["feature_day"] - D0).dt.days.to_numpy()
    s_ord = np.argsort(s_day, kind="stable")
    s_lo = np.searchsorted(s_day[s_ord], np.arange(n_days))
    s_hi = np.searchsorted(s_day[s_ord], np.arange(n_days), side="right")

    names = []
    for w in WINDOWS:
        names.append(f"det_cell_{w}d")
        names += [f"det_{k}_{w}d" for k in RADII]
    names.append("dist_fire_km")
    out = np.full((len(sample), len(names)), np.nan, dtype=np.float32)

    history = deque(maxlen=max(WINDOWS))
    for d in range(n_days):
        day = np.zeros((nr, nc), np.float32)
        ia = l_ord[l_lo[d]:l_hi[d]]
        if len(ia):
            np.add.at(day, (l_r[ia], l_c[ia]), l_v[ia])
        history.appendleft(day)

        idx = s_ord[s_lo[d]:s_hi[d]]
        if not len(idx):
            continue
        rr, cc = r[idx], c[idx]
        past = list(history)
        j = 0
        for w in WINDOWS:
            win = np.sum(past[:w], axis=0)
            out[idx, j] = win[rr, cc]; j += 1
            for half in RADII.values():
                out[idx, j] = np.round(box_sum(win, half)[rr, cc]); j += 1
        recent = np.sum(past[:3], axis=0) > 0
        if recent.any():
            dist = ndimage.distance_transform_edt(~recent) * CELL_KM
            out[idx, j] = np.minimum(dist[rr, cc], MAX_DIST_KM)
        else:
            out[idx, j] = MAX_DIST_KM
        if d % 500 == 0:
            print(f"  activity features: day {d:,} of {n_days:,}")
    return pd.DataFrame(out, columns=names, index=sample.index)


def climatology_features(sample, r, c, nr, nc):
    """Average label-B fire cell-days per season, from seasons BEFORE the row's season."""
    lab = pd.read_parquet(PROC / "labels_daily.parquet", columns=["cell_id", "season", "label_b"])
    fire = lab[lab["label_b"] == 1]
    seasons = sorted(set(lab["season"]) | set(sample["season"]))
    grids = {s: np.zeros((nr, nc), np.float32) for s in seasons}
    for s, grp in fire.groupby("season"):
        np.add.at(grids[s], ((grp["cell_id"] // nc).to_numpy(), (grp["cell_id"] % nc).to_numpy()), 1)

    out = pd.DataFrame(index=sample.index, columns=["clim_cell", "clim_nbr10"], dtype=np.float32)
    prior = np.zeros((nr, nc), np.float32)
    for i, s in enumerate(seasons):
        rows = np.flatnonzero(sample["season"].to_numpy() == s)
        if len(rows) and i > 0:
            per_season = prior / i
            nbr = box_sum(per_season, RADII["nbr10"]) / (2 * RADII["nbr10"] + 1) ** 2
            out.iloc[rows, 0] = per_season[r[rows], c[rows]]
            out.iloc[rows, 1] = nbr[r[rows], c[rows]]
        prior += grids[s]
    return out


def years_since_fire(sample, grid):
    """Years since a cell last burned, using fires from EARLIER SEASONS only.

    Perimeters are mapped after a fire ends and show its final extent, so a current-season
    perimeter would reveal where a fire is going to burn. A fire therefore becomes usable
    from 1 July after its season (fire history SEASON = the year the July-June season ends).
    A fire counts for a cell if its perimeter touches any part of the cell.
    """
    fh = gpd.read_parquet(PROC / "fire_history.parquet")
    fh = fh[fh["FIRETYPE"].isin(["Bushfire", "Burn"]) & fh["START_DATE"].notna()]
    print("  intersecting perimeters with grid cells (a few minutes)...")
    hits = gpd.sjoin(grid[["cell_id", "geometry"]],
                     fh[["FIREKEY", "FIRETYPE", "SEASON", "START_DATE", "geometry"]],
                     predicate="intersects")
    fires = hits[["cell_id", "FIREKEY", "FIRETYPE", "SEASON", "START_DATE"]].drop_duplicates(["cell_id", "FIREKEY"])
    fires["available_from"] = pd.to_datetime(fires["SEASON"].astype(str) + "-07-01").astype("datetime64[ns]")
    fires["START_DATE"] = fires["START_DATE"].astype("datetime64[ns]")
    fires["cell_id"] = fires["cell_id"].astype(np.int64)
    print(f"  fire history: {fires['FIREKEY'].nunique():,} fires touch {fires['cell_id'].nunique():,} cells")

    left = pd.DataFrame({"pos": np.arange(len(sample)),
                         "cell_id": sample["cell_id"].astype(np.int64).to_numpy(),
                         "feature_day": sample["feature_day"].astype("datetime64[ns]").to_numpy()}
                        ).sort_values("feature_day")
    out = pd.DataFrame(index=np.arange(len(sample)))
    for name, sel in [("any", fires), ("bushfire", fires[fires["FIRETYPE"] == "Bushfire"])]:
        right = (sel.sort_values("START_DATE")
                    .drop_duplicates(["cell_id", "available_from"], keep="last")  # latest fire per cell per season
                    .sort_values("available_from")[["cell_id", "available_from", "START_DATE", "FIRETYPE"]])
        m = pd.merge_asof(left, right, left_on="feature_day", right_on="available_from",
                          by="cell_id", direction="backward")
        years = ((m["feature_day"] - m["START_DATE"]).dt.days / 365.25).to_numpy(np.float32)
        out.loc[m["pos"].to_numpy(), f"years_since_{name}_fire"] = years
        if name == "any":
            burn = np.where(m["FIRETYPE"].isna(), np.nan, (m["FIRETYPE"] == "Burn").astype(float))
            out.loc[m["pos"].to_numpy(), "last_fire_was_burn"] = burn
    out.index = sample.index
    return out


def main() -> None:
    meta = json.loads((PROC / "grid_meta.json").read_text())
    nr, nc = meta["nrows"], meta["ncols"]
    grid = gpd.read_parquet(PROC / "grid_2km.parquet")
    static_cells = set(pd.read_parquet(PROC / "static_cells.parquet")["cell_id"])

    sample = pd.read_parquet(PROC / "sample_24h.parquet")
    sample["feature_day"] = sample["issue_date"] - pd.Timedelta(days=1)
    r = (sample["cell_id"] // nc).to_numpy()
    c = (sample["cell_id"] % nc).to_numpy()
    print(f"Sample: {len(sample):,} rows")

    print("Activity features...")
    act = activity_features(sample, r, c, nr, nc, static_cells)
    print("Climatology features...")
    clim = climatology_features(sample, r, c, nr, nc)
    print("Years since fire...")
    ysf = years_since_fire(sample, grid)

    td = sample["target_date"]
    doy = td.dt.day_of_year.to_numpy()
    cal = pd.DataFrame({
        "doy_sin": np.sin(2 * np.pi * doy / 365.25), "doy_cos": np.cos(2 * np.pi * doy / 365.25),
        "month": td.dt.month, "dow": td.dt.day_of_week,
    }, index=sample.index)
    loc = sample[["cell_id"]].merge(grid[["cell_id", "row", "col", "lat", "lon"]], on="cell_id", how="left")
    loc.index = sample.index
    loc["static_cell"] = sample["cell_id"].isin(static_cells).astype(int)

    feats = pd.concat([sample[["cell_id", "target_date"]], act, clim, ysf, cal,
                       loc.drop(columns="cell_id")], axis=1)
    out = PROC / "features_fire.parquet"
    feats.to_parquet(out, index=False)
    print(f"\nSaved {feats.shape[1] - 2} features for {len(feats):,} rows -> {out.relative_to(ROOT)}\n")

    lab = sample["label_b"]
    check = ["det_cell_1d", "det_cell_7d", "det_nbr10_7d", "dist_fire_km",
             "clim_cell", "years_since_any_fire", "years_since_bushfire_fire"]
    summary = pd.DataFrame({
        "fire (label B)": feats.loc[lab == 1, check].median(),
        "no fire": feats.loc[lab == 0, check].median(),
    })
    print("Medians, fire vs no-fire rows:")
    print(summary.round(2).to_string())
    print(f"\nFire rows with fire in the same cell the day before: {(feats.loc[lab == 1, 'det_cell_1d'] > 0).mean():.0%}")
    print(f"Fire rows with no fire within 10 km in the last 7 days (new ignitions): "
          f"{(feats.loc[lab == 1, 'det_nbr5_7d'] == 0).mean():.0%}")
    print(f"Missing values per feature:\n{feats.isna().mean().round(3)[feats.isna().mean() > 0].to_string()}")


if __name__ == "__main__":
    main()
