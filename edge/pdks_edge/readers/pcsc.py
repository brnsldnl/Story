"""PC/SC uyumlu NFC okuyucu adapter'ı (önerilen yol).

PC/SC, akıllı kart okuyucuları için üreticiden bağımsız bir standarttır.
ACR122U gibi yaygın okuyucular bu standardı konuşur; Linux'ta pcscd + CCID
sürücüsüyle çalışır, kapalı kaynak bir SDK gerekmez.

Bu adapter kartın UID'sini okur. Kriptografik kart doğrulaması (DESFire
authenticate) yapmaz - o, SAM modülü ve üreticiye özel anahtar yönetimi
gerektirir. Kart kopyalamaya karşı savunmamız fotoğraf kaydıdır: kopya kartla
giren kişinin yüzü kayda girer.

Bağımlılık: pyscard (LGPL)
"""

from __future__ import annotations

import logging

from .base import CardEvent, CardReader, ReaderUnavailable

log = logging.getLogger(__name__)

# APDU: kartın UID'sini iste (PC/SC pseudo-APDU, ACR122U ve muadilleri)
GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]


class PCSCReader(CardReader):
    name = "pcsc"

    def __init__(self, reader_index: int = 0) -> None:
        self._reader_index = reader_index
        self._reader = None
        self._last_uid: str | None = None

    def open(self) -> None:
        try:
            from smartcard.System import readers  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - ortam bağımlı
            raise ReaderUnavailable(
                "pyscard kurulu değil. 'pip install pyscard' ve sistemde "
                "pcscd + libccid gerekir."
            ) from exc

        available = readers()
        if not available:
            raise ReaderUnavailable(
                "PC/SC okuyucu bulunamadı. pcscd servisi çalışıyor mu, "
                "okuyucu takılı mı kontrol edin."
            )
        if self._reader_index >= len(available):
            raise ReaderUnavailable(
                f"Okuyucu #{self._reader_index} yok; {len(available)} okuyucu bulundu."
            )

        self._reader = available[self._reader_index]
        log.info("PC/SC okuyucu açıldı: %s", self._reader)

    def read(self, timeout: float) -> CardEvent | None:
        from smartcard.CardRequest import CardRequest  # type: ignore[import-untyped]
        from smartcard.CardType import AnyCardType  # type: ignore[import-untyped]
        from smartcard.Exceptions import (  # type: ignore[import-untyped]
            CardRequestTimeoutException,
            NoCardException,
        )

        if self._reader is None:
            raise ReaderUnavailable("open() çağrılmadan read() kullanılamaz.")

        try:
            request = CardRequest(
                readers=[self._reader], cardType=AnyCardType(), timeout=timeout
            )
            service = request.waitforcard()
            service.connection.connect()
            try:
                response, sw1, sw2 = service.connection.transmit(GET_UID_APDU)
            finally:
                service.connection.disconnect()
        except CardRequestTimeoutException:
            # Timeout normaldir: kimse kart okutmadı.
            self._last_uid = None
            return None
        except NoCardException:
            self._last_uid = None
            return None

        if (sw1, sw2) != (0x90, 0x00):
            log.warning("Kart UID okunamadı, SW=%02X%02X", sw1, sw2)
            return None

        uid = "".join(f"{byte:02X}" for byte in response)
        if not uid:
            return None

        # Kart okuyucunun üstünde bırakıldığında sürekli olay üretmesini
        # engelle. Asıl mükerrer koruma sunucuda, ama burada da filtreleyerek
        # gereksiz fotoğraf çekmiyoruz (KVKK: veri minimizasyonu).
        if uid == self._last_uid:
            return None
        self._last_uid = uid

        return CardEvent.now(uid, technology="mifare", reader=self.name)

    def close(self) -> None:
        self._reader = None
        self._last_uid = None
