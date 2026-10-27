import logging

from . import config
from .http import get_bytes
from .storage import save_raw


def collect_dea() -> dict:
    """Save DEA's 72-hour national hotspots GeoJSON.

    The file can be large in peak season, so it is checked lightly
    rather than parsed, to stay within the function's memory.
    """
    data = get_bytes(config.DEA_RECENT_URL, label="DEA Hotspots", timeout=180)
    head = data[:2000].lstrip()
    if not head.startswith(b"{") or b'"features"' not in data[:200000]:
        raise RuntimeError(f"DEA response is not GeoJSON: {data[:120]!r}")
    path = save_raw("dea", "recent-hotspots", "json", data, compress=True)
    logging.info("DEA: %.1f MB downloaded, saved=%s", len(data) / 1e6, path)
    return {"mb": round(len(data) / 1e6, 2), "saved": path}
