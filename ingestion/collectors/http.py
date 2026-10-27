import time
import urllib.request

import requests

from . import config

RETRY_STATUS = {429, 500, 502, 503, 504}


def _redact(text: str) -> str:
    if config.FIRMS_MAP_KEY:
        text = text.replace(config.FIRMS_MAP_KEY, "***")
    return text


def get_bytes(url: str, label: str, timeout: int = 60, retries: int = 3) -> bytes:
    """Fetch a URL (HTTP or FTP) with retries. `label` names it in errors."""
    last_error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            if url.startswith("ftp://"):
                with urllib.request.urlopen(url, timeout=timeout) as resp:
                    return resp.read()
            resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            last_error = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUS:
                break
        except Exception as exc:  # network errors, timeouts
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(5 * attempt)
    raise RuntimeError(_redact(f"Fetch failed for {label} after {retries} attempts: {last_error}"))
