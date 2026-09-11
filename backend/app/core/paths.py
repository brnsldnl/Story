"""Platform bağımsız varsayılan dizinler.

Proje hem Linux sunucuda (üretim) hem Windows'ta (geliştirme) çalışır.
Sabit "/var/lib/..." yolları Windows'ta anlamsızdır, bu yüzden varsayılanlar
çalışılan işletim sistemine göre belirlenir.

Yapılandırmada açık bir yol verilirse her zaman o kullanılır; buradaki
değerler yalnızca varsayılandır.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir(app_name: str = "PDKS") -> Path:
    """Uygulama verisinin varsayılan kök dizini."""
    if sys.platform == "win32":
        # C:\ProgramData\PDKS
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    return Path("/var/lib") / app_name.lower()


def default_photo_dir() -> str:
    return str(default_data_dir() / "photos")
