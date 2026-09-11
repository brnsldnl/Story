"""Okuyucu adapter'ları ve yapılandırmadan okuyucu üreten fabrika."""

from __future__ import annotations

from .base import CardEvent, CardReader, ReaderUnavailable

__all__ = ["CardEvent", "CardReader", "ReaderUnavailable", "build_reader"]


def build_reader(config: dict) -> CardReader:
    """Yapılandırma sözlüğünden uygun okuyucu adapter'ını üretir.

    Donanım seçimi tek bir yapılandırma satırıdır; kod değişmez.
    """
    kind = config.get("type", "mock")

    if kind == "pcsc":
        from .pcsc import PCSCReader

        return PCSCReader(reader_index=config.get("reader_index", 0))

    if kind == "hid":
        from .hid import HIDKeyboardReader

        return HIDKeyboardReader(
            device_path=config.get("device_path"),
            vendor_name=config.get("vendor_name"),
        )

    if kind == "serial":
        from .serial_reader import SerialReader

        return SerialReader(
            port=config["port"],
            baudrate=config.get("baudrate", 9600),
            technology=config.get("technology", "unknown"),
        )

    if kind == "mock":
        from .mock import MockReader

        return MockReader(trigger_file=config.get("trigger_file", "/tmp/pdks_card"))

    raise ValueError(
        f"Bilinmeyen okuyucu tipi: {kind!r}. "
        "Geçerli değerler: pcsc, hid, serial, mock"
    )
