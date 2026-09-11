"""KVKK imha işi testleri.

'Sildik' demek yetmez; dosyanın gerçekten gittiğini test etmek gerekir.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"
)

from app.core.db import SessionLocal, engine  # noqa: E402
from app.models import Photo  # noqa: E402
from app.services.photo_storage import PhotoStorage  # noqa: E402
from app.services.retention import purge_expired_photos  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE attendance_events, photos RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def storage(tmp_path):
    return PhotoStorage(str(tmp_path))


def add_photo(db, storage, *, purge_after: datetime) -> tuple[Photo, str]:
    captured = datetime.now(timezone.utc)
    key, digest = storage.save(b"sahte-jpeg-verisi", captured)
    photo = Photo(
        storage_key=key,
        captured_at=captured,
        sha256=digest,
        byte_size=17,
        purge_after=purge_after,
        created_at=captured,
    )
    db.add(photo)
    db.commit()
    return photo, key


def test_suresi_dolan_fotograf_diskten_gercekten_silinir(storage, tmp_path):
    with SessionLocal() as db:
        photo, key = add_photo(
            db, storage, purge_after=datetime.now(timezone.utc) - timedelta(days=1)
        )
        assert (tmp_path / key).exists()

        stats = purge_expired_photos(db, storage)

        assert stats["deleted"] == 1
        # Asıl test: dosya diskte kalmamalı
        assert not (tmp_path / key).exists()
        db.refresh(photo)
        assert photo.deleted_at is not None


def test_suresi_dolmayan_fotograf_korunur(storage, tmp_path):
    with SessionLocal() as db:
        photo, key = add_photo(
            db, storage, purge_after=datetime.now(timezone.utc) + timedelta(days=30)
        )

        stats = purge_expired_photos(db, storage)

        assert stats["deleted"] == 0
        assert (tmp_path / key).exists()
        db.refresh(photo)
        assert photo.deleted_at is None


def test_imha_tekrar_calistirilabilir(storage):
    """İş iki kez çalışırsa ikinci çalıştırma bir şey yapmamalı."""
    with SessionLocal() as db:
        add_photo(db, storage, purge_after=datetime.now(timezone.utc) - timedelta(days=1))

        first = purge_expired_photos(db, storage)
        second = purge_expired_photos(db, storage)

        assert first["deleted"] == 1
        assert second["deleted"] == 0


def test_diskte_olmayan_dosya_isi_durdurmaz(storage, tmp_path):
    """Dosya elle silinmişse iş çuvallamamalı, kaydı yine de kapatmalı."""
    with SessionLocal() as db:
        photo, key = add_photo(
            db, storage, purge_after=datetime.now(timezone.utc) - timedelta(days=1)
        )
        (tmp_path / key).unlink()

        stats = purge_expired_photos(db, storage)

        assert stats["already_missing"] == 1
        db.refresh(photo)
        assert photo.deleted_at is not None
