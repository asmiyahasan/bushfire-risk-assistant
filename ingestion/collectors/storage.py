import gzip
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from . import config


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def write(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read(self, path: str) -> bytes | None:
        target = self.root / path
        return target.read_bytes() if target.exists() else None


class BlobStorage:
    def __init__(self, connection_string: str, container: str):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(container)
        try:
            self.container.create_container()
        except ResourceExistsError:
            pass

    def write(self, path: str, data: bytes) -> None:
        self.container.upload_blob(path, data, overwrite=True)

    def read(self, path: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.container.download_blob(path).readall()
        except ResourceNotFoundError:
            return None


_store = None


def get_storage():
    global _store
    if _store is None:
        if config.STORAGE_BACKEND == "azure":
            if not config.AZURE_STORAGE_CONNECTION_STRING:
                raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
            _store = BlobStorage(config.AZURE_STORAGE_CONNECTION_STRING, config.BLOB_CONTAINER)
        else:
            _store = LocalStorage(config.LOCAL_DATA_DIR)
    return _store


def save_raw(source: str, name: str, ext: str, data: bytes,
             compress: bool = False, dedupe: bool = True) -> str | None:
    """Save a raw download as source/YYYY/MM/DD/<UTC timestamp>_<name>.<ext>.

    Returns the saved path, or None if identical to the previous download.
    """
    store = get_storage()
    digest = hashlib.sha256(data).hexdigest().encode()
    marker = f"_state/{source}_{name}.sha256"
    if dedupe and store.read(marker) == digest:
        return None

    now = datetime.now(timezone.utc)
    path = f"{source}/{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%SZ}_{name}.{ext}"
    if compress:
        data = gzip.compress(data)
        path += ".gz"
    store.write(path, data)
    store.write(marker, digest)
    return path
