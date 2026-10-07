"""Stockage des photos de preuve.

Aujourd'hui : un dossier local servi sous /uploads.
Demain : une classe S3Storage avec la même méthode `save`, sans toucher aux routes.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def save(self, data: bytes, content_type: str) -> str:
        ext = ALLOWED_TYPES[content_type]
        now = datetime.now(timezone.utc)
        relative = Path(f"{now:%Y}/{now:%m}/{uuid.uuid4().hex}{ext}")
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/uploads/{relative.as_posix()}"


storage = LocalStorage(settings.upload_dir)


class PrivateStorage:
    """Fichiers personnels (tickets de caisse) : hors du dossier servi par l'API."""

    def __init__(self, root: str):
        self.root = Path(root)

    def save(self, data: bytes, content_type: str) -> str:
        ext = ALLOWED_TYPES[content_type]
        now = datetime.now(timezone.utc)
        relative = Path(f"{now:%Y}/{now:%m}/{uuid.uuid4().hex}{ext}")
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return relative.as_posix()


private_storage = PrivateStorage(settings.receipts_dir)
