"""Edge agent yapılandırması (YAML).

Donanım seçimi tamamen yapılandırmadadır: okuyucu markası değişince kod değil
bu dosya değişir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    reader: dict[str, Any] = field(default_factory=lambda: {"type": "mock"})

    queue_db_path: str = "/var/lib/pdks-edge/queue.db"
    photo_spool_dir: str = "/var/lib/pdks-edge/photos"

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
            reader=data.get("reader", {"type": "mock"}),
            queue_db_path=data.get("queue_db_path", cls.queue_db_path),
            photo_spool_dir=data.get("photo_spool_dir", cls.photo_spool_dir),
            read_timeout_seconds=data.get("read_timeout_seconds", cls.read_timeout_seconds),
            heartbeat_interval_seconds=data.get(
                "heartbeat_interval_seconds", cls.heartbeat_interval_seconds
            ),
            duplicate_window_seconds=data.get(
                "duplicate_window_seconds", cls.duplicate_window_seconds
            ),
        )
