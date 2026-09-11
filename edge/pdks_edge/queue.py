"""Offline dayanıklı yerel kuyruk (SQLite).

Bu modül sistemin en kritik parçasıdır. Ağ koptuğunda, sunucu yeniden
başlatıldığında veya switch arızalandığında terminal okumaya devam etmeli ve
tek bir kayıt bile kaybolmamalıdır. Kayıp bir okuma, bir çalışanın o günkü
puantajının yanlış hesaplanması demektir.

Tasarım:
  - Okuma ve fotoğraf ÖNCE diske yazılır, SONRA gönderilmeye çalışılır.
  - Her olayın bir client_event_id (UUID) değeri vardır; sunucu bu değerle
    mükerrer kayıtları eler. Bu sayede "gönderdim mi acaba" belirsizliğinde
    tekrar göndermek güvenlidir.
  - Başarısız gönderimler artan bekleme süresiyle yeniden denenir.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_reads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    client_event_id  TEXT    NOT NULL UNIQUE,
    card_uid         TEXT    NOT NULL,
    read_at          TEXT    NOT NULL,
    technology       TEXT    NOT NULL DEFAULT 'unknown',
    photo_path       TEXT,
    raw              TEXT    NOT NULL DEFAULT '{}',
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TEXT    NOT NULL,
    last_error       TEXT,
    created_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_next_attempt
    ON pending_reads(next_attempt_at);
"""

# Yeniden deneme bekleme süreleri (saniye). Son değer tekrar tekrar kullanılır.
_BACKOFF_SCHEDULE = (2, 5, 15, 30, 60, 120, 300)


class PendingRead(NamedTuple):
    id: int
    client_event_id: str
    card_uid: str
    read_at: str
    technology: str
    photo_path: str | None
    raw: dict
    attempts: int


class OfflineQueue:
    def __init__(self, db_path: str, photo_dir: str) -> None:
        self._db_path = Path(db_path)
        self._photo_dir = Path(photo_dir)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._photo_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # WAL: ani elektrik kesintisinde veri bütünlüğü için
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(_SCHEMA)

    def enqueue(
        self,
        card_uid: str,
        read_at: datetime,
        technology: str = "unknown",
        photo: bytes | None = None,
        raw: dict | None = None,
    ) -> str:
        """Okumayı diske yazar ve olay kimliğini döner.

        Fotoğraf varsa önce dosyaya yazılır; kuyruk kaydı yalnızca fotoğraf
        güvenle diskteyse oluşturulur.
        """
        event_id = str(uuid.uuid4())

        photo_path: str | None = None
        if photo is not None:
            path = self._photo_dir / f"{event_id}.jpg"
            path.write_bytes(photo)
            photo_path = str(path)

        now = datetime.now(UTC)
        self._conn.execute(
            """
            INSERT INTO pending_reads (
                client_event_id, card_uid, read_at, technology,
                photo_path, raw, next_attempt_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                card_uid,
                read_at.astimezone(UTC).isoformat(),
                technology,
                photo_path,
                json.dumps(raw or {}),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        log.info("Kuyruğa alındı: uid=%s event=%s", card_uid, event_id)
        return event_id

    def due(self, limit: int = 20) -> Iterator[PendingRead]:
        """Gönderilmeye hazır kayıtları en eskiden başlayarak verir."""
        now = datetime.now(UTC).isoformat()
        rows = self._conn.execute(
            """
            SELECT * FROM pending_reads
            WHERE next_attempt_at <= ?
            ORDER BY read_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()

        for row in rows:
            yield PendingRead(
                id=row["id"],
                client_event_id=row["client_event_id"],
                card_uid=row["card_uid"],
                read_at=row["read_at"],
                technology=row["technology"],
                photo_path=row["photo_path"],
                raw=json.loads(row["raw"]),
                attempts=row["attempts"],
            )

    def mark_sent(self, item: PendingRead) -> None:
        """Başarılı gönderimden sonra kaydı ve fotoğrafını yerelden siler.

        Fotoğraf artık sunucuda; terminalde kopya bırakmak KVKK açısından
        gereksiz bir veri yayılımıdır.
        """
        self._conn.execute("DELETE FROM pending_reads WHERE id = ?", (item.id,))
        if item.photo_path:
            Path(item.photo_path).unlink(missing_ok=True)

    def mark_failed(self, item: PendingRead, error: str) -> None:
        """Gönderim başarısız; artan bekleme süresiyle yeniden planlar."""
        attempts = item.attempts + 1
        delay = _BACKOFF_SCHEDULE[min(attempts - 1, len(_BACKOFF_SCHEDULE) - 1)]
        next_attempt = datetime.now(UTC) + timedelta(seconds=delay)

        self._conn.execute(
            """
            UPDATE pending_reads
            SET attempts = ?, next_attempt_at = ?, last_error = ?
            WHERE id = ?
            """,
            (attempts, next_attempt.isoformat(), error[:500], item.id),
        )
        log.warning(
            "Gönderim başarısız (deneme %d), %d sn sonra tekrar: %s",
            attempts,
            delay,
            error[:200],
        )

    def depth(self) -> int:
        """Bekleyen kayıt sayısı. Panelde terminal sağlığı olarak gösterilir."""
        row = self._conn.execute("SELECT COUNT(*) AS c FROM pending_reads").fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
