import csv
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MELBOURNE = ZoneInfo("Australia/Melbourne")
VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


def _confidence_level(instrument: str, raw: str) -> str:
    if instrument == "VIIRS":
        return VIIRS_CONFIDENCE.get(raw.strip().lower(), "unknown")
    try:  # MODIS: 0-100, using FIRMS' usual bands
        value = int(raw)
    except ValueError:
        return "unknown"
    if value < 30:
        return "low"
    return "nominal" if value < 80 else "high"


def parse_firms_csv(csv_bytes: bytes, source: str, source_file: str = "") -> list[dict]:
    """Normalise one FIRMS CSV (VIIRS or MODIS) into a common detection schema."""
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    rows = []
    for r in reader:
        hhmm = r["acq_time"].zfill(4)  # "319" -> "0319"
        acq_utc = datetime.strptime(f"{r['acq_date']} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        acq_local = acq_utc.astimezone(MELBOURNE)
        instrument = r["instrument"]
        rows.append({
            "source": source,
            "satellite": r["satellite"],
            "instrument": instrument,
            "lat": float(r["latitude"]),
            "lon": float(r["longitude"]),
            "acq_utc": acq_utc.isoformat(),
            "acq_local": acq_local.isoformat(),
            "local_date": acq_local.date().isoformat(),
            "confidence_raw": r["confidence"],
            "confidence": _confidence_level(instrument, r["confidence"]),
            "brightness": float(r.get("bright_ti4") or r.get("brightness") or "nan"),
            "frp": float(r["frp"]) if r.get("frp") else None,
            "daynight": r.get("daynight"),
            "version": r.get("version"),
            "source_file": source_file,
        })
    return rows
