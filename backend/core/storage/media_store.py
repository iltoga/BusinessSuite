from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from django.core.files.storage import FileSystemStorage, Storage, default_storage


def _normalize_prefix(prefix: str | None) -> str:
    return str(prefix or "").strip().strip("/")


def _iter_storage_files_via_listdir(storage: Storage, prefix: str) -> Iterator[str]:
    normalized_prefix = _normalize_prefix(prefix)
    try:
        directories, files = storage.listdir(normalized_prefix)
    except Exception:
        return

    for file_name in files:
        yield "/".join(part for part in (normalized_prefix, str(file_name).strip("/")) if part)

    for directory_name in directories:
        child_prefix = "/".join(part for part in (normalized_prefix, str(directory_name).strip("/")) if part)
        yield from _iter_storage_files_via_listdir(storage, child_prefix)


class BaseMediaStoreAdapter(ABC):
    def __init__(self, storage: Storage | None = None):
        self.storage = storage or default_storage

    @abstractmethod
    def iter_files(self, prefix: str) -> Iterable[str]:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        self.storage.delete(_normalize_prefix(key))

    def size(self, key: str) -> int | None:
        try:
            return int(self.storage.size(_normalize_prefix(key)))
        except Exception:
            return None


class FileSystemMediaStoreAdapter(BaseMediaStoreAdapter):
    def iter_files(self, prefix: str) -> Iterable[str]:
        return _iter_storage_files_via_listdir(self.storage, prefix)


class ObjectMediaStoreAdapter(BaseMediaStoreAdapter):
    def iter_files(self, prefix: str) -> Iterable[str]:
        normalized_prefix = _normalize_prefix(prefix)
        object_prefix = f"{normalized_prefix}/" if normalized_prefix else ""

        bucket = getattr(self.storage, "bucket", None)
        bucket_objects = getattr(bucket, "objects", None)
        if bucket_objects is not None:
            try:
                for obj in bucket_objects.filter(Prefix=object_prefix):
                    key = _normalize_prefix(getattr(obj, "key", ""))
                    if key and not key.endswith("/"):
                        yield key
                return
            except Exception:
                pass

        yield from _iter_storage_files_via_listdir(self.storage, normalized_prefix)


def get_media_store_adapter(storage: Storage | None = None) -> BaseMediaStoreAdapter:
    concrete_storage = storage or default_storage
    if isinstance(concrete_storage, FileSystemStorage):
        return FileSystemMediaStoreAdapter(concrete_storage)
    return ObjectMediaStoreAdapter(concrete_storage)
