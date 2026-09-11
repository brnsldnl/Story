"""Edge agent yapılandırması (YAML).

Donanım seçimi tamamen yapılandırmadadır: okuyucu markası değişince kod değil
bu dosya değişir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import (
    default_photo_spool,
    default_qr_png,
    default_queue_db,
)


@dataclass
class CameraConfig:
    enabled: bool = True
    device_index: int = 0
    width: int = 640
    height: int = 480
    # KVKK veri minimizasyonu: kimlik teyidi için 640x480 fazlasıyla yeterli.
    jpeg_quality: int = 75
    keep_open: bool = False


@dataclass
class QRConfig:
    """Terminal ekranında dönen QR kod ayarları."""

    enabled: bool = False
    # Kurulum sırasında sunucudan alınan, terminale özel gizli anahtar.
    # Sunucu bunu kendi ana anahtarından türetir; burada saklanan kopya
    # terminalin çevrimdışı da kod üretebilmesini sağlar.
    secret: str = ""
    period_seconds: int = 30
    # Kiosk arayüzünün göstereceği dosya
    png_path: str = field(default_factory=default_qr_png)


@dataclass
class ServerConfig:
    base_url: str = "https://pdks.local"
    api_key: str = ""
    # Kurum içi sertifika kullanılıyorsa CA dosyasının yolu verilebilir.
    verify_tls: bool | str = True


@dataclass
class EdgeConfig:
    terminal_code: str
    server: ServerConfig = field(default_factory=ServerConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    qr: QRConfig = field(default_factory=QRConfig)
    reader: dict[str, Any] = field(default_factory=lambda: {"type": "mock"})

    queue_db_path: str = field(default_factory=default_queue_db)
    photo_spool_dir: str = field(default_factory=default_photo_spool)

    read_timeout_seconds: float = 1.0
    heartbeat_interval_seconds: float = 60.0
    duplicate_window_seconds: float = 10.0

    @classmethod
    def from_file(cls, path: str | Path) -> EdgeConfig:
        import yaml

        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeConfig:
        if "terminal_code" not in data:
            raise ValueError("Yapılandırmada 'terminal_code' zorunludur.")

        return cls(
            terminal_code=data["terminal_code"],
            server=ServerConfig(**data.get("server", {})),
            camera=CameraConfig(**data.get("camera", {})),
            qr=QRConfig(**data.get("qr", {})),
            reader=data.get("reader", {"type": "mock"}),
            queue_db_path=data.get("queue_db_path") or default_queue_db(),
            photo_spool_dir=data.get("photo_spool_dir") or default_photo_spool(),
            read_timeout_seconds=data.get("read_timeout_seconds", 1.0),
            heartbeat_interval_seconds=data.get(
                "heartbeat_interval_seconds", 60.0
            ),
            duplicate_window_seconds=data.get(
                "duplicate_window_seconds", 10.0
            ),
        )
