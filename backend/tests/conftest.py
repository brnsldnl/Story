"""Ortak test yapılandırması.

Testler platform bağımsız olmalı: sabit "/tmp" yolları Windows'ta
çalışmaz. Fotoğraf deposu her oturum için geçici bir dizine kurulur ve
sonunda temizlenir.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Ayarlar ilk import anında okunduğu için ortam değişkenleri uygulama
# modülleri yüklenmeden önce ayarlanmalıdır.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"
)
os.environ.setdefault(
    "PHOTO_STORAGE_PATH", str(Path(tempfile.gettempdir()) / "pdks-test-photos")
)
os.environ.setdefault(
    "JWT_SECRET", "test-ortami-icin-jwt-anahtari-en-az-otuziki-bayt"
)
os.environ.setdefault(
    "QR_MASTER_SECRET", "test-ortami-icin-qr-ana-anahtari-en-az-otuziki-bayt"
)
