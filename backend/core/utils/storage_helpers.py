from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from django.core.files.storage import FileSystemStorage, default_storage

CHUNK_SIZE = 1024 * 1024


def _iter_chunks(file_handle):
    """Yield chunks from django File objects and plain file-like objects."""
    if hasattr(file_handle, "chunks"):
        for chunk in file_handle.chunks():
            if chunk:
                yield chunk
        return

    while True:
        chunk = file_handle.read(CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


def _resolve_storage_and_name(file_reference):
    if file_reference is None:
        raise ValueError("file_reference cannot be None")

    if isinstance(file_reference, str):
        return default_storage, file_reference

    name = getattr(file_reference, "name", None)
    if not name:
        raise ValueError("file_reference does not provide a valid file name")

    storage = getattr(file_reference, "storage", None) or default_storage
    return storage, name


@contextmanager
def get_local_file_path(file_reference) -> Iterator[str]:
    """
    Yield a local filesystem path for any Django-stored file.

    - Local storage: returns native path directly.
    - Remote storage (e.g. S3/R2): downloads to a temp file and cleans it up.
    """
    storage, file_name = _resolve_storage_and_name(file_reference)

    # Local storage backends can provide a native filesystem path directly.
    if isinstance(storage, FileSystemStorage):
        if not os.path.isabs(file_name):
            file_name = storage.path(file_name)
        yield file_name
        return

    temp_path = None
    suffix = Path(file_name).suffix
    temp_file = NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name

    try:
        with temp_file:
            with storage.open(file_name, "rb") as source_file:
                for chunk in _iter_chunks(source_file):
                    temp_file.write(chunk)
        yield temp_path
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
