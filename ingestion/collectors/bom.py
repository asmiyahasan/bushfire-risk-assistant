import logging

from . import config
from .http import get_bytes
from .storage import save_raw


def collect_bom_fdr() -> dict:
    """Save BOM's Victorian fire danger rating product (ratings + Fire Behaviour Index)."""
    product_id = config.BOM_FDR_PRODUCT_ID
    url = config.BOM_FTP_TEMPLATE.format(product_id=product_id)
    data = get_bytes(url, label=f"BOM {product_id}")
    if not data.lstrip().startswith(b"<?xml"):
        raise RuntimeError(f"BOM {product_id} is not XML: {data[:120]!r}")
    path = save_raw("bom", product_id, "xml", data)
    logging.info("BOM %s: saved=%s", product_id, path)
    return {"saved": path}
