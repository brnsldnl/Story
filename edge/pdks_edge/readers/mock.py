"""Donanımsız geliştirme ve test için sahte okuyucu.

Ekip donanım gelmeden önce tüm akışı uçtan uca çalıştırabilsin diye vardır.
Kart numaralarını bir dosyadan okur: dosyaya bir UID yazmak, o kartın
okutulmasıyla aynı etkiyi yapar.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .base import CardEvent, CardReader

log = logging.getLogger(__name__)


class MockReader(CardReader):
    name = "mock"

    def __init__(self, trigger_file: str = "/tmp/pdks_card", uids: list[str] | None = None):
        self._trigger = Path(trigger_file)
        self._uids = uids or []
        self._index = 0

    def open(self) -> None:
        log.info(
            "Sahte okuyucu açıldı. Kart okutmak için: echo ABC123 > %s", self._trigger
        )

    def read(self, timeout: float) -> CardEvent | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._trigger.exists():
                uid = self._trigger.read_text().strip()
                self._trigger.unlink(missing_ok=True)
                if uid:
                    return CardEvent.now(uid, technology="mock", reader=self.name)
            time.sleep(0.1)
        return None

    def close(self) -> None:
        self._trigger.unlink(missing_ok=True)
