"""Kart okuyucu soyutlaması.

Donanım seçimi bu arayüzün arkasında kalır. Bir okuyucu tedarik edilemez
olduğunda ya da başka bir lokasyonda farklı marka kullanıldığında yalnızca
yeni bir adapter yazılır; uygulamanın geri kalanı değişmez.

Bu soyutlama bilinçli olarak dar tutulmuştur: bir okuyucudan tek ihtiyacımız
"bir kart okundu ve UID'si şu" bilgisidir. Üreticiye özel kapı açma, parmak
izi, yüz tanıma gibi yetenekler kasıtlı olarak kapsam dışıdır.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Self


@dataclass(frozen=True)
class CardEvent:
    """Okuyucudan gelen tek bir kart okuma olayı."""

    uid: str
    read_at: datetime
    technology: str = "unknown"
    raw: dict = field(default_factory=dict)

    @staticmethod
    def now(uid: str, technology: str = "unknown", **raw: object) -> CardEvent:
        return CardEvent(
            uid=uid.upper(),
            read_at=datetime.now(UTC),
            technology=technology,
            raw=dict(raw),
        )


class CardReader(abc.ABC):
    """Tüm okuyucu adapter'larının uyduğu arayüz."""

    name: str = "base"

    @abc.abstractmethod
    def open(self) -> None:
        """Donanıma bağlan. Bağlanamazsa ReaderUnavailable fırlatır."""

    @abc.abstractmethod
    def read(self, timeout: float) -> CardEvent | None:
        """Bir kart okumasını bekler.

        timeout süresi içinde okuma olmazsa None döner. Bu bir hata değildir;
        ana döngü bu sayede nefes alır ve kapanma sinyallerini işleyebilir.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Donanım kaynaklarını bırak."""

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class ReaderUnavailable(RuntimeError):
    """Okuyucu donanımına ulaşılamıyor (takılı değil, izin yok, meşgul)."""
