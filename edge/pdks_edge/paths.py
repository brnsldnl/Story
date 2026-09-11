"""Platform bağımsız varsayılan dizinler (terminal agent).

Terminal genellikle Linux'ta (Raspberry Pi / mini PC) çalışır ama
geliştirme Windows'ta yapılabilir; varsayılanlar ikisinde de anlamlı olmalı.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "PDKS-Edge"


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    return Path("/var/lib/pdks-edge")


def default_queue_db() -> str:
    return str(default_data_dir() / "queue.db")


def default_photo_spool() -> str:
    return str(default_data_dir() / "photos")


def default_qr_png() -> str:
    """QR görselinin yazılacağı yol.

    Linux'ta /run geçici dosya sistemidir (yeniden başlatmada temizlenir);
    Windows'ta karşılığı yoktur, geçici dizin kullanılır.
    """
    if sys.platform == "win32":
        return str(Path(tempfile.gettempdir()) / "pdks-qr.png")
    return "/run/pdks-edge/qr.png"


def default_mock_trigger() -> str:
    """Sahte okuyucunun izlediği tetik dosyası."""
    return str(Path(tempfile.gettempdir()) / "pdks_card")
