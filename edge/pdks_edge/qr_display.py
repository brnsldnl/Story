"""Terminal ekranında dönen QR kodun üretimi.

Kod tamamen YERELDE üretilir: terminale kurulum sırasında verilen gizli
anahtar ve o anki zaman yeterlidir. İnternet kopsa bile QR ekranda dönmeye
devam eder ve çalışanlar okutabilir; okutmalar mobil tarafta kuyruğa girer.

Sunucu aynı anahtarı kendi ana anahtarından türeterek doğrular, dolayısıyla
terminalin sunucuya hiçbir şey sorması gerekmez.

Bağımlılık: qrcode (BSD) - yalnızca görsel üretimi için, opsiyonel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

log = logging.getLogger(__name__)

DEFAULT_PERIOD_SECONDS = 30
_SIGNATURE_BYTES = 12


def generate_token(
    secret: str, terminal_code: str, now: float | None = None,
    period_seconds: int = DEFAULT_PERIOD_SECONDS,
) -> str:
    """O an geçerli QR içeriğini üretir.

    Sunucudaki app/services/qr_token.py ile AYNI algoritmayı uygular.
    İkisi birbirinden bağımsız çalışır; bu yüzden değişiklik yaparken
    ikisini birlikte değiştirmek gerekir (test: test_qr_uyumluluk.py).
    """
    period = int((now if now is not None else time.time()) // period_seconds)
    message = f"{terminal_code}:{period}".encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest[:_SIGNATURE_BYTES]).decode().rstrip("=")
    return f"{terminal_code}.{period}.{signature}"


def seconds_until_refresh(
    now: float | None = None, period_seconds: int = DEFAULT_PERIOD_SECONDS
) -> float:
    """Ekrandaki kodun yenilenmesine kaç saniye kaldığı."""
    current = now if now is not None else time.time()
    return period_seconds - (current % period_seconds)


def render_png(token: str, path: str, box_size: int = 10) -> None:
    """QR kodu PNG olarak yazar. Kiosk arayüzü bu dosyayı gösterir."""
    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - ortam bağımlı
        raise RuntimeError(
            "qrcode kurulu değil: pip install 'pdks-edge[qr]'"
        ) from exc

    image = qrcode.make(token, box_size=box_size, border=2)
    image.save(path)


def render_ascii(token: str) -> str:
    """QR kodu metin olarak döner - ekransız kurulumda hızlı doğrulama için."""
    try:
        import io

        import qrcode
    except ImportError as exc:  # pragma: no cover - ortam bağımlı
        raise RuntimeError("qrcode kurulu değil.") from exc

    code = qrcode.QRCode(border=1)
    code.add_data(token)
    buffer = io.StringIO()
    code.print_ascii(out=buffer)
    return buffer.getvalue()
