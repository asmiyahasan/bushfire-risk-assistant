import json
import logging

from . import config
from .http import get_bytes
from .storage import save_raw


def collect_vicemergency() -> dict:
    """Snapshot the full VicEmergency feed. Events vanish when they end, so keep every version."""
    data = get_bytes(config.VICEMERGENCY_URL, label="VicEmergency feed")
    payload = json.loads(data)
    features = payload.get("features")
    if features is None:
        raise RuntimeError("VicEmergency feed has no 'features' key")
    path = save_raw("vicemergency", "events", "json", data, compress=True)
    logging.info("VicEmergency: %d events, saved=%s", len(features), path)
    return {"events": len(features), "saved": path}
