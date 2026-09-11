"""USB HID "keyboard wedge" okuyucu adapter'ı.

Bu okuyucular kendilerini USB klavye olarak tanıtır ve kart okunduğunda UID'yi
tuş tuş "yazar". Sürücü, SDK, lisans gerektirmezler - en ucuz ve en hızlı
başlangıç yolu budur.

Okuyucuyu evdev üzerinden ÖZEL OLARAK yakalarız (EVIOCGRAB). Aksi halde kart
numarası sistemde açık olan pencereye de yazılır; kiosk makinesinde bu hem
kirlilik hem güvenlik sorunudur.

Bağımlılık: evdev (BSD)
"""

from __future__ import annotations

import logging

from .base import CardEvent, CardReader, ReaderUnavailable

log = logging.getLogger(__name__)

# evdev tuş kodundan karaktere: kart okuyucular yalnızca rakam/harf üretir
_KEYMAP = {
    **{f"KEY_{d}": str(d) for d in range(10)},
    **{f"KEY_{c}": c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
}


class HIDKeyboardReader(CardReader):
    name = "hid"

    def __init__(self, device_path: str | None = None, vendor_name: str | None = None):
        """
        device_path : /dev/input/eventX - en güvenilir yol, udev kuralıyla sabitleyin
        vendor_name : cihaz adında aranacak metin (device_path verilmediyse)
        """
        if not device_path and not vendor_name:
            raise ValueError("device_path veya vendor_name verilmelidir.")
        self._device_path = device_path
        self._vendor_name = vendor_name
        self._device = None
        self._buffer: list[str] = []

    def open(self) -> None:
        try:
            import evdev  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - ortam bağımlı
            raise ReaderUnavailable("evdev kurulu değil: pip install evdev") from exc

        path = self._device_path
        if path is None:
            matches = [
                dev
                for dev in (evdev.InputDevice(p) for p in evdev.list_devices())
                if self._vendor_name and self._vendor_name.lower() in dev.name.lower()
            ]
            if not matches:
                raise ReaderUnavailable(
                    f"'{self._vendor_name}' adını taşıyan HID cihazı bulunamadı."
                )
            self._device = matches[0]
        else:
            try:
                self._device = evdev.InputDevice(path)
            except (OSError, PermissionError) as exc:
                raise ReaderUnavailable(
                    f"{path} açılamadı: {exc}. Kullanıcı 'input' grubunda mı?"
                ) from exc

        # Tuş vuruşlarını yalnız bize yönlendir
        try:
            self._device.grab()
        except OSError as exc:
            log.warning("Cihaz özel olarak yakalanamadı (grab): %s", exc)

        log.info("HID okuyucu açıldı: %s", self._device.name)

    def read(self, timeout: float) -> CardEvent | None:
        import select

        import evdev  # type: ignore[import-untyped]

        if self._device is None:
            raise ReaderUnavailable("open() çağrılmadan read() kullanılamaz.")

        ready, _, _ = select.select([self._device.fd], [], [], timeout)
        if not ready:
            return None

        for event in self._device.read():
            if event.type != evdev.ecodes.EV_KEY:
                continue
            key_event = evdev.categorize(event)
            if key_event.keystate != key_event.key_down:
                continue

            keycode = key_event.keycode
            if isinstance(keycode, list):
                keycode = keycode[0]

            if keycode == "KEY_ENTER":
                uid = "".join(self._buffer)
                self._buffer.clear()
                if uid:
                    return CardEvent.now(uid, technology="unknown", reader=self.name)
            elif keycode in _KEYMAP:
                self._buffer.append(_KEYMAP[keycode])
                # Bozuk okuma sonsuza kadar birikmesin
                if len(self._buffer) > 64:
                    self._buffer.clear()

        return None

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.ungrab()
            except OSError:
                pass
            self._device.close()
            self._device = None
        self._buffer.clear()
