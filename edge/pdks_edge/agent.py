"""Edge agent ana döngüsü.

Akış:
    kart okundu -> fotoğraf çek -> DİSKE YAZ -> göndermeyi dene

Kritik nokta: kayıt diske yazılmadan gönderim denenmez. Böylece ağ kopuksa
veya sunucu kapalıysa hiçbir okuma kaybolmaz.
"""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from .camera import Camera, CameraError, NullCamera
from .config import EdgeConfig
from .queue import OfflineQueue
from .readers import ReaderUnavailable, build_reader
from .uploader import Uploader

log = logging.getLogger(__name__)

AGENT_VERSION = "0.1.0"


class EdgeAgent:
    def __init__(self, config: EdgeConfig) -> None:
        self._config = config
        self._running = False

        self._queue = OfflineQueue(
            db_path=config.queue_db_path, photo_dir=config.photo_spool_dir
        )
        self._reader = build_reader(config.reader)
        self._camera: Camera = (
            Camera(
                device_index=config.camera.device_index,
                width=config.camera.width,
                height=config.camera.height,
                jpeg_quality=config.camera.jpeg_quality,
                keep_open=config.camera.keep_open,
            )
            if config.camera.enabled
            else NullCamera()
        )
        self._uploader = Uploader(
            base_url=config.server.base_url,
            terminal_code=config.terminal_code,
            api_key=config.server.api_key,
            verify=config.server.verify_tls,
        )

        self._last_heartbeat = 0.0
        # Aynı kartın arka arkaya okunmasını filtrelemek için
        self._recent: dict[str, float] = {}

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        log.info("Sinyal alındı (%s), kapanılıyor...", signum)
        self._running = False

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._reader.open()
        except ReaderUnavailable:
            log.exception("Okuyucu açılamadı, agent başlatılamıyor.")
            raise

        self._running = True
        log.info(
            "Edge agent çalışıyor: terminal=%s okuyucu=%s kamera=%s",
            self._config.terminal_code,
            self._reader.name,
            "açık" if self._config.camera.enabled else "kapalı",
        )

        try:
            while self._running:
                self._tick()
        finally:
            self._shutdown()

    def _tick(self) -> None:
        event = self._reader.read(timeout=self._config.read_timeout_seconds)

        if event is not None and not self._is_duplicate(event.uid):
            self._handle_card(event)

        # Kart okunmasa da kuyruğu boşaltmaya çalış: ağ geri gelmiş olabilir.
        try:
            self._uploader.flush(self._queue)
        except Exception:
            log.exception("Kuyruk boşaltılırken beklenmeyen hata")

        self._maybe_heartbeat()

    def _is_duplicate(self, uid: str) -> bool:
        """Aynı kartın kısa süre içinde tekrar okutulmasını eler.

        Kullanıcı kartı okuyucuya iki kez değdirdiğinde giriş hemen ardından
        çıkışa dönüşmemeli. Asıl mükerrer koruma sunucuda da var; buradaki
        filtre gereksiz fotoğraf çekmemizi de engelliyor.
        """
        now = time.monotonic()
        window = self._config.duplicate_window_seconds

        # Eskimiş kayıtları temizle ki sözlük sınırsız büyümesin
        self._recent = {k: v for k, v in self._recent.items() if now - v < window}

        if uid in self._recent:
            log.debug("Mükerrer okuma elendi: %s", uid)
            return True

        self._recent[uid] = now
        return False

    def _handle_card(self, event) -> None:
        photo: bytes | None = None
        if self._config.camera.enabled:
            try:
                photo = self._camera.capture().data
            except CameraError as exc:
                # Kamera arızası okumayı DÜŞÜRMEZ. Puantaj fotoğraftan daha
                # önemlidir; fotoğrafsız kayıt, kayıt olmamasından iyidir.
                log.error("Fotoğraf çekilemedi, okuma fotoğrafsız kaydediliyor: %s", exc)

        self._queue.enqueue(
            card_uid=event.uid,
            read_at=event.read_at,
            technology=event.technology,
            photo=photo,
            raw=event.raw,
        )

    def _maybe_heartbeat(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < self._config.heartbeat_interval_seconds:
            return
        self._last_heartbeat = now
        self._uploader.heartbeat(self._queue.depth(), AGENT_VERSION)

    def _shutdown(self) -> None:
        log.info("Kapanıyor; bekleyen kayıt sayısı: %d", self._queue.depth())
        self._reader.close()
        self._camera.close()
        self._uploader.close()
        self._queue.close()
