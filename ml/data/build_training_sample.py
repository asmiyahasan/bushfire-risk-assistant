"""Build the modelling sample: every fire cell-day plus a random sample of no-fire cell-days.

Input:  data/historical/processed/grid_2km.parquet, labels_daily.parquet
Output: data/historical/processed/sample_24h.parquet

One row = one grid cell on one target day (the day predicted, 24 h after a 6 am issue the day before).
Positives:  every cell-day with label_b == 1 (label_a may be 1, -1 = ignore, or blank).
Negatives:  a random NEG_RATE share of cell-days with no detections at all, weight = 1 / NEG_RATE.
Ignore-only cell-days (planned burns, autumn burn-offs, static sources) are left out.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "historical" / "processed"
START, END = pd.Timestamp("2012-07-01"), pd.Timestamp("2026-06-30")  # seasons 2012-13 to 2025-26
LAST_SEASON_WITH_FIRE_HISTORY = "2024-25"
NEG_RATE = 0.005
SEED = 42


def season_of(dates: pd.Series) -> pd.Series:
    start = dates.dt.year.where(dates.dt.month >= 7, dates.dt.year - 1)
    return start.astype(str) + "-" + ((start + 1) % 100).astype(str).str.zfill(2)


def main() -> None:
    cells = pd.read_parquet(PROC / "grid_2km.parquet", columns=["cell_id"])["cell_id"].to_numpy()
    labels = pd.read_parquet(PROC / "labels_daily.parquet")
    labels["target_date"] = pd.to_datetime(labels["local_date"])
    labels = labels[labels["target_date"].between(START, END)]

    n_days = (END - START).days + 1
    day_index = lambda d: (d - START).dt.days.to_numpy()
    key = lambda cell, day: cell.astype(np.int64) * 10_000 + day

    # Positives: every label-B fire cell-day (label A rides along).
    pos = labels.loc[labels["label_b"] == 1, ["cell_id", "target_date", "label_a", "label_b"]].copy()
    pos["weight"] = 1.0

    # Negatives: random cell-days with no detection of any kind.
    rng = np.random.default_rng(SEED)
    n_draw = int(len(cells) * n_days * NEG_RATE * 1.02)
    neg = pd.DataFrame({"cell_id": rng.choice(cells, n_draw),
                        "day": rng.integers(0, n_days, n_draw)}).drop_duplicates()
    active = key(labels["cell_id"].to_numpy(), day_index(labels["target_date"]))
    neg = neg[~np.isin(key(neg["cell_id"].to_numpy(), neg["day"].to_numpy()), active)]
    neg["target_date"] = START + pd.to_timedelta(neg["day"], unit="D")
    neg = neg.drop(columns="day").assign(label_a=0.0, label_b=0, weight=1 / NEG_RATE)

    sample = pd.concat([pos, neg], ignore_index=True)
    sample["season"] = season_of(sample["target_date"])
    sample.loc[sample["season"] > LAST_SEASON_WITH_FIRE_HISTORY, "label_a"] = np.nan
    sample["issue_date"] = sample["target_date"] - pd.Timedelta(days=1)
    sample = sample.sort_values(["target_date", "cell_id"]).reset_index(drop=True)
    sample = sample[["cell_id", "issue_date", "target_date", "season", "label_a", "label_b", "weight"]]

    out = PROC / "sample_24h.parquet"
    sample.to_parquet(out, index=False)
    print(f"Saved {len(sample):,} rows -> {out.relative_to(ROOT)}")
    print(f"Grid cells: {len(cells):,} | days: {n_days:,} | negative rate: {NEG_RATE:.1%}\n")

    summary = sample.groupby("season").agg(
        fire_b=("label_b", lambda s: int((s == 1).sum())),
        fire_a=("label_a", lambda s: int((s == 1).sum())),
        ignore_a=("label_a", lambda s: int((s == -1).sum())),
        no_fire=("label_b", lambda s: int((s == 0).sum())),
    )
    summary["fire_share_b"] = (summary["fire_b"] / (summary["fire_b"] + summary["no_fire"])).map("{:.2%}".format)
    print(summary.to_string())


if __name__ == "__main__":
    main()
