import xml.etree.ElementTree as ET


def parse_bom_fdr(xml_bytes: bytes, source_file: str = "") -> list[dict]:
    """Turn one BOM fire danger XML file (e.g. IDV18555) into one row per district per day."""
    root = ET.fromstring(xml_bytes)
    issued_utc = root.findtext("amoc/issue-time-utc")
    issued_local = root.findtext("amoc/issue-time-local")
    product_id = root.findtext("amoc/identifier")

    rows = []
    for area in root.iter("area"):
        if area.get("type") != "fire-district":
            continue
        for period in area.findall("forecast-period"):
            fbi_text = period.findtext("element[@type='fire_behaviour_index']")
            rows.append({
                "product_id": product_id,
                "issued_at_utc": issued_utc,
                "issued_at_local": issued_local,
                "district_code": area.get("aac"),
                "district": area.get("description"),
                "lead_days": int(period.get("index")),
                "forecast_date": period.get("start-time-local", "")[:10],
                "fbi": int(fbi_text) if fbi_text not in (None, "") else None,
                "rating": period.findtext("text[@type='fire_danger']"),
                "source_file": source_file,
            })
    return rows
