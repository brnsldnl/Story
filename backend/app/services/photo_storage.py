"""Fotoğraf deposu.

Fotoğraflar veritabanına BLOB olarak konmaz: yedek boyutu kontrolden çıkar ve
KVKK imha süreci (gerçekten silme) zorlaşır. Dosya sisteminde tutulur,
veritabanında yalnızca referans ve saklama süresi bulunur.

Arayüz soyutlanmıştır; ileride S3 uyumlu bir depoya (MinIO vb.) geçmek
istenirse yalnızca bu sınıfın yeni bir uygulaması yazılır.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class PhotoStorage:
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        return self._root / key

    def save(self, data: bytes, captured_at: datetime) -> tuple[str, str]:
        """Fotoğrafı kaydeder; (storage_key, sha256) döner.

        Tarihe göre klasörlenir: hem dizin başına dosya sayısı makul kalır
        hem de KVKK imha işi bir günün tamamını tek seferde temizleyebilir.
        """
        digest = hashlib.sha256(data).hexdigest()
        folder = captured_at.strftime("%Y/%m/%d")
        key = f"{folder}/{digest[:16]}.jpg"

        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

        return key, digest

    def read(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def delete(self, key: str) -> bool:
        """Dosyayı gerçekten siler. KVKK imhası flag atmakla olmaz."""
        path = self._path_for(key)
        if not path.exists():
            return False
        path.unlink()

        # Boşalan tarih klasörlerini temizle
        for parent in (path.parent, path.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break
        return True
