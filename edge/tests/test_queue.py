"""Offline kuyruk testleri.

Kuyruk, sistemin veri kaybetmeme garantisidir; bu yüzden en çok test edilen
parça odur.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pdks_edge.queue import OfflineQueue


@pytest.fixture()
def queue(tmp_path):
    q = OfflineQueue(
        db_path=str(tmp_path / "queue.db"), photo_dir=str(tmp_path / "photos")
    )
    yield q
    q.close()


def test_enqueue_persists_read_and_photo(queue, tmp_path):
    event_id = queue.enqueue(
        card_uid="04A2B3C4",
        read_at=datetime(2026, 3, 2, 6, 42, tzinfo=UTC),
        technology="mifare",
        photo=b"\xff\xd8fake-jpeg",
    )

    items = list(queue.due())
    assert len(items) == 1
    item = items[0]
    assert item.client_event_id == event_id
    assert item.card_uid == "04A2B3C4"
    assert item.photo_path is not None

    # Fotoğraf gönderimden ÖNCE diske yazılmış olmalı
    photo_files = list((tmp_path / "photos").iterdir())
    assert len(photo_files) == 1
    assert photo_files[0].read_bytes() == b"\xff\xd8fake-jpeg"


def test_photo_is_optional(queue):
    queue.enqueue(card_uid="DEADBEEF", read_at=datetime.now(UTC))
    item = next(iter(queue.due()))
    assert item.photo_path is None


def test_mark_sent_removes_record_and_local_photo(queue, tmp_path):
    queue.enqueue(
        card_uid="04A2B3C4", read_at=datetime.now(UTC), photo=b"jpeg-bytes"
    )
    item = next(iter(queue.due()))
    photo_path = tmp_path / "photos" / f"{item.client_event_id}.jpg"
    assert photo_path.exists()

    queue.mark_sent(item)

    assert queue.depth() == 0
    # Terminalde kopya kalmamalı (KVKK: gereksiz veri yayılımı)
    assert not photo_path.exists()


def test_failed_send_is_retried_with_backoff(queue):
    queue.enqueue(card_uid="04A2B3C4", read_at=datetime.now(UTC))
    item = next(iter(queue.due()))

    queue.mark_failed(item, "bağlantı reddedildi")

    # Kayıt kaybolmadı, sadece ertelendi
    assert queue.depth() == 1
    assert list(queue.due()) == []


def test_queue_survives_restart(tmp_path):
    """Elektrik kesintisi simülasyonu: kuyruk kapanıp yeniden açılır."""
    db = str(tmp_path / "queue.db")
    photos = str(tmp_path / "photos")

    first = OfflineQueue(db_path=db, photo_dir=photos)
    first.enqueue(card_uid="04A2B3C4", read_at=datetime.now(UTC), photo=b"x")
    first.close()

    second = OfflineQueue(db_path=db, photo_dir=photos)
    try:
        assert second.depth() == 1
        assert next(iter(second.due())).card_uid == "04A2B3C4"
    finally:
        second.close()


def test_reads_are_drained_oldest_first(queue):
    """Gönderim sırası korunmalı: giriş/çıkış sırası puantajı belirler."""
    queue.enqueue("AAA", datetime(2026, 3, 2, 8, 0, tzinfo=UTC))
    queue.enqueue("BBB", datetime(2026, 3, 2, 7, 0, tzinfo=UTC))
    queue.enqueue("CCC", datetime(2026, 3, 2, 9, 0, tzinfo=UTC))

    uids = [item.card_uid for item in queue.due()]
    assert uids == ["BBB", "AAA", "CCC"]


def test_event_ids_are_unique(queue):
    """Mükerrer kayıt korumasının dayandığı garanti."""
    ids = {
        queue.enqueue(f"CARD{i}", datetime.now(UTC)) for i in range(50)
    }
    assert len(ids) == 50
