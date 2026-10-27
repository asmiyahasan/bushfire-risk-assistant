import logging

from . import config
from .http import get_bytes
from .storage import save_raw


def collect_cfa() -> dict:
    """Save each fire district's RSS feed. One bad district doesn't stop the others."""
    summary, failures = {}, []
    for district in config.CFA_DISTRICTS:
        url = config.CFA_RSS_TEMPLATE.format(district=district)
        try:
            data = get_bytes(url, label=f"CFA {district}")
            if b"<rss" not in data[:1000]:
                raise RuntimeError(f"not an RSS document: {data[:120]!r}")
            summary[district] = save_raw("cfa", district, "xml", data)
        except Exception as exc:
            failures.append(f"{district}: {exc}")
    logging.info("CFA: saved=%s", summary)
    if failures:
        raise RuntimeError("CFA failures: " + "; ".join(failures))
    return summary
