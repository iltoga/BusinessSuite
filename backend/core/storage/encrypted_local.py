"""
FILE_ROLE: Implements AES-GCM encrypted local file storage for media blobs.

KEY_COMPONENTS:
- EncryptedLocalStorage: FileSystemStorage subclass that encrypts on write and decrypts on read.
- _resolve_key: Loads and validates the 32-byte encryption key from settings.
- _encrypt_bytes: Encrypts plaintext bytes into the stored payload format.
- _decrypt_bytes: Decrypts payload bytes back into plaintext.
- _save: Encrypts content before delegating to the base storage save.
- open: Returns a decrypted file object for read-only access.

INTERACTIONS:
- Depends on: cryptography AESGCM, django.conf.settings, django.core.files.storage.FileSystemStorage, and media persistence.

AI_GUIDELINES:
- Keep the encryption header and key size contract stable because persisted blobs depend on it.
- Use this adapter only for encrypted local media; do not mix it with unrelated storage behaviors.
"""

from __future__ import annotations

import base64
import os
from io import BytesIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage

_MAGIC = b"RBENC01"
_NONCE_SIZE = 12


class EncryptedLocalStorage(FileSystemStorage):
    """Filesystem storage with AES-GCM encryption-at-rest for media blobs.

    File format: MAGIC(7) + NONCE(12) + CIPHERTEXT+TAG
    """

    def _resolve_key(self) -> bytes:
        raw_value = (getattr(settings, "LOCAL_MEDIA_ENCRYPTION_KEY", "") or "").strip()
        if not raw_value:
            raise ImproperlyConfigured("LOCAL_MEDIA_ENCRYPTION_KEY is required for EncryptedLocalStorage")

        for decoder in (
            lambda v: base64.b64decode(v, validate=True),
            lambda v: bytes.fromhex(v),
        ):
            try:
                decoded = decoder(raw_value)
                if len(decoded) == 32:
                    return decoded
            except Exception:
                continue

        raw_bytes = raw_value.encode("utf-8")
        if len(raw_bytes) == 32:
            return raw_bytes

        raise ImproperlyConfigured("LOCAL_MEDIA_ENCRYPTION_KEY must decode to exactly 32 bytes")

    def _encrypt_bytes(self, plain: bytes) -> bytes:
        key = self._resolve_key()
        nonce = os.urandom(_NONCE_SIZE)
        encrypted = AESGCM(key).encrypt(nonce, plain, None)
        return _MAGIC + nonce + encrypted

    def _decrypt_bytes(self, payload: bytes) -> bytes:
        if not payload.startswith(_MAGIC):
            raise ImproperlyConfigured("Encrypted media payload missing expected encryption header")

        key = self._resolve_key()
        nonce_start = len(_MAGIC)
        nonce_end = nonce_start + _NONCE_SIZE
        nonce = payload[nonce_start:nonce_end]
        ciphertext = payload[nonce_end:]
        return AESGCM(key).decrypt(nonce, ciphertext, None)

    def _save(self, name, content):
        raw = content.read()
        encrypted = self._encrypt_bytes(raw)
        wrapped = ContentFile(encrypted)
        return super()._save(name, wrapped)

    def open(self, name, mode="rb"):
        if any(flag in mode for flag in ("w", "a", "+")):
            return super().open(name, mode)

        encrypted_file = super().open(name, "rb")
        encrypted_data = encrypted_file.read()
        decrypted_data = self._decrypt_bytes(encrypted_data)
        file_obj = File(BytesIO(decrypted_data), name=name)
        return file_obj
