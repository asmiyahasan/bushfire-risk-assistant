import logging

from . import config
from .http import get_bytes
from .storage import save_raw

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def collect_firms(day_range: int = 2) -> dict:
    """Download the last `day_range` days of detections over Victoria for each satellite."""
    if not config.FIRMS_MAP_KEY:
        raise RuntimeError("FIRMS_MAP_KEY is not set")

    summary = {}
    for source in config.FIRMS_SOURCES:
        url = f"{BASE_URL}/{config.FIRMS_MAP_KEY}/{source}/{config.VIC_BBOX}/{day_range}"
        data = get_bytes(url, label=f"FIRMS {source}")
        text = data.decode("utf-8", errors="replace")
        # A valid response is a CSV whose header starts with "latitude".
        if not text.startswith("latitude"):
            raise RuntimeError(f"FIRMS {source} returned unexpected content: {text[:200]!r}")
        detections = max(len(text.strip().splitlines()) - 1, 0)  # header only = no fires, normal
        path = save_raw("firms", source, "csv", data)
        summary[source] = {"detections": detections, "saved": path}
        logging.info("FIRMS %s: %d detections, saved=%s", source, detections, path)
    return summary
