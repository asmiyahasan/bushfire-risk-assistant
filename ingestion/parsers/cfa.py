import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime

NOT_TFB = "is not currently a day of total fire ban"
IS_TFB = "is a day of total fire ban"


def _clean(text: str) -> str:
    """Turn the HTML in an RSS description into plain lower-case-friendly text."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_cfa_district(xml_bytes: bytes, district_slug: str, source_file: str = "") -> list[dict]:
    """One row per forecast day: Total Fire Ban status and rating for one fire district."""
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    published = channel.findtext("{http://purl.org/dc/elements/1.1/}date")

    rows = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        try:
            day = datetime.strptime(title, "%A, %d %B %Y").date()
        except ValueError:
            continue  # skips the "Fire restrictions by municipality" item

        text = _clean(item.findtext("description"))
        lower = text.lower()
        if NOT_TFB in lower:
            tfb = "no"
        elif IS_TFB in lower:
            tfb = "yes"
        else:
            tfb = "unknown"

        issued = re.search(r"forecast issued at:\s*(.+?(?:AM|PM))", text)
        rating = re.search(r":\s*(NO RATING|MODERATE|HIGH|EXTREME|CATASTROPHIC)\b", text, re.I)

        rows.append({
            "district_slug": district_slug,
            "published_utc": published,
            "forecast_date": day.isoformat(),
            "total_fire_ban": tfb,
            "rating": rating.group(1).title() if rating else None,
            "bom_issue_local": (
                datetime.strptime(issued.group(1), "%A, %d %B %Y %I:%M %p").isoformat()
                if issued else None
            ),
            "tfb_sentence": text.split(".")[0] + "." if tfb == "unknown" else "",
            "source_file": source_file,
        })
    return rows
