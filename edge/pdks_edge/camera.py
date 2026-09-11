"""Kart okuma anında fotoğraf çekimi.

Kamera bilinçli olarak okuyucudan AYRI tutulmuştur. Erişim kontrol
terminallerinin dahili kameraları üreticiye özel SDK'ların arkasındadır ve
genellikle yüz tanımaya bağlıdır - yüz şablonu KVKK m.6 anlamında özel
nitelikli kişisel veridir ve açık rıza gerektirir.

Standart bir UVC web kamerasını kendimiz kontrol ederek hem tam açık kaynak
kalıyoruz hem de yalnızca "fotoğraf" işliyoruz: biyometrik şablon üretmiyoruz.

Bağımlılık: opencv-python (Apache 2.0)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    width: int
    height: int
    content_type: str = "image/jpeg"


class CameraError(RuntimeError):
    """Kamera açılamadı veya kare alınamadı."""


class Camera:
    """Tek kare yakalayan basit kamera sarmalayıcısı.

    Kamerayı sürekli açık tutmak yerine her çekimde açıp kapatma seçeneği
    vardır (`keep_open=False`). Kiosk makinesi günde birkaç yüz kare çekeceği
    için bu maliyet önemsizdir ve kamerayı boşta açık bırakmamak hem KVKK
    açısından daha savunulabilir hem de USB kilitlenmelerine karşı dayanıklıdır.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int = 640,
        height: int = 480,
        jpeg_quality: int = 75,
        warmup_frames: int = 5,
        keep_open: bool = False,
    ) -> None:
        self._device_index = device_index
        self._width = width
        self._height = height
        self._jpeg_quality = jpeg_quality
        self._warmup_frames = warmup_frames
        self._keep_open = keep_open
        self._capture = None

    def _open_capture(self):
        import cv2  # type: ignore[import-untyped]

        capture = cv2.VideoCapture(self._device_index)
        if not capture.isOpened():
            raise CameraError(
                f"Kamera #{self._device_index} açılamadı. Cihaz bağlı mı, "
                "kullanıcı 'video' grubunda mı?"
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        return capture

    def capture(self) -> Snapshot:
        """Tek kare yakalar ve JPEG olarak döner."""
        import cv2  # type: ignore[import-untyped]

        capture = self._capture
        opened_here = False
        if capture is None:
            capture = self._open_capture()
            opened_here = True
            if self._keep_open:
                self._capture = capture
                opened_here = False

        try:
            # Web kameralarının ilk kareleri karanlık/bulanık gelir; pozlama
            # oturana kadar birkaç kare atıyoruz.
            frame = None
            for _ in range(max(1, self._warmup_frames)):
                ok, candidate = capture.read()
                if ok:
                    frame = candidate

            if frame is None:
                raise CameraError("Kameradan kare alınamadı.")

            ok, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality]
            )
            if not ok:
                raise CameraError("Kare JPEG olarak kodlanamadı.")

            height, width = frame.shape[:2]
            return Snapshot(data=buffer.tobytes(), width=width, height=height)
        finally:
            if opened_here:
                capture.release()

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class NullCamera(Camera):
    """Kamerasız terminaller için (örn. yalnızca çıkış turnikesi)."""

    def __init__(self) -> None:
        super().__init__()

    def capture(self) -> Snapshot:
        raise CameraError("Bu terminalde kamera devre dışı.")
