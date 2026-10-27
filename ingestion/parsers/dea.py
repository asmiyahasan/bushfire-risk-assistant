import json
from datetime import datetime
from zoneinfo import ZoneInfo

from collectors import config

MELBOURNE = ZoneInfo("Australia/Melbourne")
WEST, SOUTH, EAST, NORTH = (float(v) for v in config.VIC_BBOX.split(","))


def _in_vic_box(lon, lat) -> bool:
    return lon is not None and lat is not None and WEST <= lon <= EAST and SOUTH <= lat <= NORTH


def _missing_to_none(value):
    """DEA uses -1 / -999 (or null) for 'no value'."""
    if value is None:
        return None
    try:
        return None if float(value) < 0 else float(value)
    except (TypeError, ValueError):
        return None


def parse_dea(json_bytes: bytes, source_file: str = "") -> list[dict]:
    """Victorian hotspots from one DEA national GeoJSON file."""
    payload = json.loads(json_bytes)
    rows = []
    for feature in payload.get("features", []):
        p = feature.get("properties", {})
        state = (p.get("australian_state") or "").strip()
        lon, lat = p.get("longitude"), p.get("latitude")
        if not (state == "VIC" or (state == "" and _in_vic_box(lon, lat))):
            continue

        dt_utc = datetime.fromisoformat(p["datetime"].replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(MELBOURNE)
        rows.append({
            "id": p.get("id"),
            "satellite": p.get("satellite"),
            "sensor": p.get("sensor"),
            "product": p.get("product"),
            "algorithm": p.get("process_algorithm"),
            "lat": lat,
            "lon": lon,
            "acq_utc": dt_utc.isoformat(),
            "acq_local": dt_local.isoformat(),
            "local_date": dt_local.date().isoformat(),
            "state": state or None,
            "confidence": _missing_to_none(p.get("confidence")),
            "power_mw": _missing_to_none(p.get("power")),
            "temp_kelvin": _missing_to_none(p.get("temp_kelvin")),
            "load_utc": p.get("load_dt"),
            "source_file": source_file,
        })
    return rows
