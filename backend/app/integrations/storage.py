"""File storage abstraction (local disk today; S3/GCS can implement the same interface)."""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed

_SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9/_\-.]{0,200}$")
ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/svg+xml": "svg"}


class StorageProvider(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> str:
        """Persist bytes and return the public URL."""

    @abstractmethod
    def open(self, key: str) -> tuple[bytes, str]: ...

    @staticmethod
    def new_key(prefix: str, content_type: str) -> str:
        ext = ALLOWED_IMAGE_TYPES.get(content_type)
        if not ext:
            raise ValidationFailed("Unsupported file type", code="UNSUPPORTED_MEDIA_TYPE")
        return f"{prefix}/{uuid.uuid4().hex}.{ext}"


class LocalStorageProvider(StorageProvider):
    _TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "svg": "image/svg+xml"}

    def __init__(self, root: str, url_prefix: str) -> None:
        self.root = Path(root).resolve()
        self.url_prefix = url_prefix.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key) or ".." in key:
            raise NotFoundError("File not found", code="FILE_NOT_FOUND")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise NotFoundError("File not found", code="FILE_NOT_FOUND")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{self.url_prefix}/{key}"

    def open(self, key: str) -> tuple[bytes, str]:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError("File not found", code="FILE_NOT_FOUND")
        return path.read_bytes(), self._TYPES.get(path.suffix.lstrip("."), "application/octet-stream")


@lru_cache
def get_storage() -> StorageProvider:
    s = get_settings()
    return LocalStorageProvider(s.media_root, s.media_url_prefix)
