"""Dönen (rotating) QR kod üretimi ve doğrulaması.

NEDEN SABİT QR OLMAZ
    Kapıya asılan sabit bir QR kod hiçbir şey doğrulamaz: bir kez fotoğrafını
    çeken kişi evinden okutur. Konum doğrulaması eklense bile GPS taklidi
    (mock location) mobil cihazlarda kolaydır. Sabit QR + GPS kombinasyonu
    sanıldığı kadar güçlü değildir.

ÇÖZÜM
    QR kod terminal ekranında gösterilir ve birkaç saniyede bir DEĞİŞİR.
    İçeriği, terminale özel bir gizli anahtarla imzalanmış zaman dilimidir.
    Bir fotoğraf kısa sürede geçersiz olur; okutma yapabilmek için kişinin
    o anda ekranın karşısında olması gerekir.

    Böylece savunma sırası şudur:
      1. Dönen QR   -> fiziksel varlığı kanıtlar (asıl güvence)
      2. Konum      -> destekleyici kanıt
      3. Cihaz bağı -> hesap ele geçirilse bile okutmayı engeller

ANAHTAR YÖNETİMİ
    Terminal gizli anahtarı veritabanında SAKLANMAZ; sunucudaki ana
    anahtardan türetilir. Böylece veritabanı sızsa bile QR üretilemez.
    Anahtar kurulum sırasında terminale bir kez verilir; terminal sonrasında
    kodu çevrimdışıyken de üretebilir - internet kopsa bile QR ekranda
    dönmeye devam eder.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

# QR kodun kaç saniyede bir değiştiği
DEFAULT_PERIOD_SECONDS = 30

# Kabul edilen geçmiş dilim sayısı. Kullanıcının kodu görüp telefonu
# kaldırıp okutması zaman alır; ayrıca cihaz saatleri birkaç saniye
# kayabilir. 1 dilim tolerans bu ikisini karşılar.
DEFAULT_TOLERANCE_PERIODS = 1

_SIGNATURE_BYTES = 12


class QRTokenError(ValueError):
    """QR kod geçersiz, süresi dolmuş veya imzası tutmuyor."""


@dataclass(frozen=True)
class VerifiedToken:
    terminal_code: str
    issued_period: int
    age_seconds: int


def derive_terminal_secret(master_secret: str, terminal_code: str) -> str:
    """Terminale özel QR anahtarını ana anahtardan türetir.

    Veritabanında anahtar tutulmaz; gerektiğinde yeniden hesaplanır.
    """
    digest = hmac.new(
        master_secret.encode(), f"qr:{terminal_code}".encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _sign(secret: str, terminal_code: str, period: int) -> str:
    message = f"{terminal_code}:{period}".encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:_SIGNATURE_BYTES]).decode().rstrip("=")


def current_period(
    now: float | None = None, period_seconds: int = DEFAULT_PERIOD_SECONDS
) -> int:
    return int((now if now is not None else time.time()) // period_seconds)


def generate_token(
    secret: str,
    terminal_code: str,
    now: float | None = None,
    period_seconds: int = DEFAULT_PERIOD_SECONDS,
) -> str:
    """Terminalin ekranda göstereceği QR içeriğini üretir.

    Terminal bu fonksiyonu kendi başına, çevrimdışıyken de çalıştırabilir.
    """
    period = current_period(now, period_seconds)
    signature = _sign(secret, terminal_code, period)
    return f"{terminal_code}.{period}.{signature}"


def verify_token(
    token: str,
    secret_resolver,
    now: float | None = None,
    period_seconds: int = DEFAULT_PERIOD_SECONDS,
    tolerance_periods: int = DEFAULT_TOLERANCE_PERIODS,
) -> VerifiedToken:
    """QR kodu doğrular ve hangi terminale ait olduğunu döner.

    secret_resolver: terminal kodunu alıp o terminalin gizli anahtarını
    dönen çağrılabilir. Bilinmeyen terminal için None dönmelidir.

    Geçersizse QRTokenError fırlatır.
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise QRTokenError("QR kod biçimi geçersiz.")

    terminal_code, period_text, signature = parts

    try:
        period = int(period_text)
    except ValueError as exc:
        raise QRTokenError("QR kod zaman dilimi okunamadı.") from exc

    secret = secret_resolver(terminal_code)
    if secret is None:
        raise QRTokenError("QR kod bilinmeyen bir terminale ait.")

    expected = _sign(secret, terminal_code, period)
    if not hmac.compare_digest(expected, signature):
        raise QRTokenError("QR kod imzası doğrulanamadı.")

    now_period = current_period(now, period_seconds)

    # Gelecekten gelen kod: cihaz saati ileri veya kod üretilmeye çalışılmış.
    # Küçük bir ileri sapmaya izin veriyoruz, fazlasına değil.
    if period > now_period + tolerance_periods:
        raise QRTokenError("QR kod geçerlilik penceresinin dışında.")

    if period < now_period - tolerance_periods:
        raise QRTokenError("QR kodun süresi dolmuş, ekrandaki güncel kodu okutun.")

    age = int((now if now is not None else time.time()) - period * period_seconds)
    return VerifiedToken(
        terminal_code=terminal_code, issued_period=period, age_seconds=max(0, age)
    )
