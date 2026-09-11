"""Seri port (UART / USB-CDC / RS232) okuyucu adapter'ı.

Duvara monte okuyucuların çoğu kart numarasını seri port üzerinden satır satır
gönderir. Protokol basittir; bu yüzden bu adapter da basittir.

Bağımlılık: pyserial (BSD)
"""

from __future__ import annotations

import logging
import re

from .base import CardEvent, CardReader, ReaderUnavailable

log = logging.getLogger(__name__)

# Satırdaki gürültüyü atıp kart numarasını ayıkla
_UID_PATTERN = re.compile(r"([0-9A-Fa-f]{6,32})")


class SerialReader(CardReader):
    name = "serial"

    def __init__(self, port: str, baudrate: int = 9600, technology: str = "unknown"):
        self._port = port
        self._baudrate = baudrate
        self._technology = technology
        self._serial = None

    def open(self) -> None:
        try:
            import serial  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - ortam bağımlı
            raise ReaderUnavailable("pyserial kurulu değil: pip install pyserial") from exc

        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=0.5)
        except Exception as exc:  # serial.SerialException ve alt tipleri
            raise ReaderUnavailable(f"{self._port} açılamadı: {exc}") from exc

        log.info("Seri okuyucu açıldı: %s @ %d", self._port, self._baudrate)

    def read(self, timeout: float) -> CardEvent | None:
        if self._serial is None:
            raise ReaderUnavailable("open() çağrılmadan read() kullanılamaz.")

        self._serial.timeout = timeout
        try:
            line = self._serial.readline().decode("ascii", errors="ignore").strip()
        # pyserial sürücüye göre farklı istisnalar fırlatır; tek bir bozuk
        # okuma agent'ı düşürmemeli.
        except Exception as exc:  # noqa: BLE001
            log.warning("Seri port okuma hatası: %s", exc)
            return None

        if not line:
            return None

        match = _UID_PATTERN.search(line)
        if not match:
            log.debug("Kart numarası ayıklanamayan satır: %r", line)
            return None

        return CardEvent.now(
            match.group(1), technology=self._technology, reader=self.name, line=line
        )

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
