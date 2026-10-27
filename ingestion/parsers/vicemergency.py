import json


def _first_point(geometry: dict | None) -> tuple[float | None, float | None]:
    """Return (lon, lat) of the first Point, whether bare or inside a GeometryCollection."""
    if not geometry:
        return None, None
    if geometry.get("type") == "Point":
        lon, lat = geometry["coordinates"][:2]
        return lon, lat
    for g in geometry.get("geometries", []):
        if g.get("type") == "Point":
            lon, lat = g["coordinates"][:2]
            return lon, lat
    return None, None


def _polygons(geometry: dict | None) -> list[dict]:
    if not geometry:
        return []
    if geometry.get("type") in ("Polygon", "MultiPolygon"):
        return [geometry]
    return [g for g in geometry.get("geometries", []) if g.get("type") in ("Polygon", "MultiPolygon")]


def classify(props: dict) -> str:
    """Classify by VicEmergency's own category fields (never the place name)."""
    cap = props.get("cap") or {}
    c1 = (props.get("category1") or "").lower()
    c2 = (props.get("category2") or "").lower()
    event = (cap.get("event") or "").lower()

    if "planned burn" in (c1, c2) or "planned burn" in event:
        return "planned_burn"
    if c2 in ("bushfire", "grass fire", "scrub fire", "grass and scrub fire") or "bushfire" in event:
        return "bushfire"
    if c1 == "fire" or "fire" in c2 or "fire" in event:
        return "other_fire"
    return "non_fire"


def parse_vicemergency(json_bytes: bytes, snapshot_utc: str, source_file: str = "") -> list[dict]:
    """One row per event in one feed snapshot."""
    payload = json.loads(json_bytes)
    rows = []
    for feature in payload.get("features", []):
        p = feature.get("properties", {})
        cap = p.get("cap") or {}
        lon, lat = _first_point(feature.get("geometry"))
        polys = _polygons(feature.get("geometry"))
        rows.append({
            "snapshot_utc": snapshot_utc,
            "id": p.get("id"),
            "event_id": p.get("eventId"),
            "feed_type": p.get("feedType"),
            "source_org": p.get("sourceOrg"),
            "category1": p.get("category1"),
            "category2": p.get("category2"),
            "cap_event": cap.get("event"),
            "fire_class": classify(p),
            "status": p.get("status"),
            "name": p.get("name"),
            "location": p.get("location"),
            "created": p.get("created"),
            "updated": p.get("updated"),
            "size": p.get("size"),
            "size_fmt": p.get("sizeFmt"),
            "lon": lon,
            "lat": lat,
            "polygon_geojson": json.dumps(polys[0]) if polys else "",
            "source_file": source_file,
        })
    return rows
