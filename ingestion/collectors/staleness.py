import logging
from datetime import datetime, timedelta, timezone

from . import config

# Hours without a new raw file before a source counts as stale.
MAX_AGE_HOURS = {"vicemergency": 1, "dea": 7, "cfa": 7, "firms": 15, "bom": 18}


def check_staleness() -> dict:
    """Fail if any source has gone too long without saving a new file."""
    from azure.storage.blob import BlobServiceClient

    container = BlobServiceClient.from_connection_string(
        config.AZURE_STORAGE_CONNECTION_STRING
    ).get_container_client(config.BLOB_CONTAINER)

    now = datetime.now(timezone.utc)
    ages, stale = {}, []
    for source, limit in MAX_AGE_HOURS.items():
        latest = None
        for day in (now, now - timedelta(days=1)):  # files are filed by UTC day
            for blob in container.list_blobs(name_starts_with=f"{source}/{day:%Y/%m/%d}/"):
                if latest is None or blob.last_modified > latest:
                    latest = blob.last_modified
        age = None if latest is None else round((now - latest).total_seconds() / 3600, 1)
        ages[source] = age
        if age is None or age > limit:
            stale.append(f"{source}: last file {age if age is not None else '>24'} h ago (limit {limit} h)")

    logging.info("Hours since last file: %s", ages)
    if stale:
        raise RuntimeError("Stale data sources: " + "; ".join(stale))
    return ages
