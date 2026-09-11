"""KVKK imha işi.

Saklama süresi dolan fotoğrafları GERÇEKTEN siler. Veritabanında bayrak
çevirmek imha değildir; dosyanın diskten kalkması gerekir.

Puantaj kayıtları bu işin kapsamı dışındadır: onların saklama süresi yasal
zorunluluklara tabidir ve fotoğraftan çok daha uzundur. Fotoğraf silinse bile
giriş/çıkış kaydı yerinde kalır - bu kasıtlıdır.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Photo
from .photo_storage import PhotoStorage

log = logging.getLogger(__name__)


def purge_expired_photos(
    db: Session, storage: PhotoStorage, batch_size: int = 500
) -> dict[str, int]:
    """Saklama süresi dolmuş fotoğrafları siler.

    Dosya önce diskten silinir, sonra kayıt işaretlenir. Sıra önemlidir: ters
    sırada bir hata olursa veritabanı 'silindi' der ama dosya diskte kalır ve
    kimse fark etmez.
    """
    now = datetime.now(UTC)
    stats = {"deleted": 0, "already_missing": 0, "failed": 0}

    expired = db.execute(
        select(Photo)
        .where(Photo.purge_after <= now, Photo.deleted_at.is_(None))
        .limit(batch_size)
    ).scalars().all()

    for photo in expired:
        try:
            removed = storage.delete(photo.storage_key)
        except OSError:
            log.exception("Fotoğraf silinemedi: %s", photo.storage_key)
            stats["failed"] += 1
            continue

        photo.deleted_at = now
        stats["deleted" if removed else "already_missing"] += 1

    db.commit()

    if stats["deleted"] or stats["failed"]:
        log.info("KVKK imha işi tamamlandı: %s", stats)

    return stats
