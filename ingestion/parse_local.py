import csv
import gzip
import sys
from collections import Counter
from pathlib import Path

from collectors import config
from parsers.bom import parse_bom_fdr
from parsers.cfa import parse_cfa_district
from parsers.vicemergency import parse_vicemergency

DATA = Path(config.LOCAL_DATA_DIR)
OUT = DATA / "parsed"


def write_csv(rows: list[dict], name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / name
    if not rows:
        print(f"{name}: no rows")
        return
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}: {len(rows)} rows -> {out_path}")


def parse_bom() -> None:
    rows, seen = [], set()
    for path in sorted((DATA / "bom").rglob("*.xml")):
        for row in parse_bom_fdr(path.read_bytes(), source_file=str(path.relative_to(DATA))):
            key = (row["issued_at_utc"], row["district_code"], row["lead_days"])
            if key not in seen:
                seen.add(key)
                rows.append(row)
    write_csv(rows, "bom_fire_danger.csv")


def parse_cfa() -> None:
    rows, seen = [], set()
    for path in sorted((DATA / "cfa").rglob("*.xml")):
        slug = path.stem.split("_", 1)[1]  # "20261027T014702Z_central" -> "central"
        for row in parse_cfa_district(path.read_bytes(), slug, source_file=str(path.relative_to(DATA))):
            key = (row["district_slug"], row["published_utc"], row["forecast_date"])
            if key not in seen:
                seen.add(key)
                rows.append(row)
    write_csv(rows, "cfa_fire_bans.csv")
    unknown = [r for r in rows if r["total_fire_ban"] == "unknown"]
    if unknown:
        print(f"WARNING: {len(unknown)} rows with unrecognised Total Fire Ban wording, e.g.: "
              f"{unknown[0]['tfb_sentence']}")

def parse_vicemergency_all() -> None:
    rows, seen = [], set()
    for path in sorted((DATA / "vicemergency").rglob("*.json.gz")):
        stamp = path.name.split("_", 1)[0]  # "20261027T014656Z"
        snapshot_utc = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
        data = gzip.decompress(path.read_bytes())
        for row in parse_vicemergency(data, snapshot_utc, source_file=str(path.relative_to(DATA))):
            key = (row["id"], row["updated"])  # keep each new version of an event once
            if key not in seen:
                seen.add(key)
                rows.append(row)
    write_csv(rows, "vicemergency_events.csv")

    print("\nCategories seen (feed_type, category1, category2, cap_event) -> fire_class:")
    counts = Counter((r["feed_type"], r["category1"], r["category2"], r["cap_event"], r["fire_class"]) for r in rows)
    for (ft, c1, c2, ev, fc), n in counts.most_common():
        print(f"  {n:3d}  {ft} | {c1} | {c2} | {ev}  ->  {fc}")

PARSERS = {"bom": parse_bom, "cfa": parse_cfa, "vicemergency": parse_vicemergency_all}

if __name__ == "__main__":
    for name in sys.argv[1:] or list(PARSERS):
        PARSERS[name]()
