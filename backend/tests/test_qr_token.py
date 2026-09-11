"""Dönen QR kod testleri.

Bu testler QR kanalının güvenlik iddiasını doğrular: kodun fotoğrafını çekmek
işe yaramamalı, başka terminalin kodu kabul edilmemeli, imza kurcalanamamalı.
"""

from __future__ import annotations

import pytest

from app.services.qr_token import (
    DEFAULT_PERIOD_SECONDS,
    QRTokenError,
    derive_terminal_secret,
    generate_token,
    verify_token,
)

MASTER = "test-ana-anahtar"
TERMINAL = "MERKEZ-GIRIS-1"
SECRET = derive_terminal_secret(MASTER, TERMINAL)

T0 = 1_800_000_000.0  # sabit referans zaman


def resolver(code: str) -> str | None:
    """Yalnızca bilinen terminaller için anahtar döner."""
    known = {
        TERMINAL: SECRET,
        "DEPO-KAPI": derive_terminal_secret(MASTER, "DEPO-KAPI"),
    }
    return known.get(code)


def test_uretilen_kod_dogrulanir():
    token = generate_token(SECRET, TERMINAL, now=T0)
    result = verify_token(token, resolver, now=T0)

    assert result.terminal_code == TERMINAL


def test_kod_zamanla_degisir():
    """QR ekranda sabit kalmamalı; aksi halde fotoğrafı yeterdi."""
    first = generate_token(SECRET, TERMINAL, now=T0)
    later = generate_token(SECRET, TERMINAL, now=T0 + DEFAULT_PERIOD_SECONDS * 3)

    assert first != later


def test_ayni_dilim_icinde_kod_sabittir():
    """Aynı anda birden fazla kişi aynı kodu okutabilmeli."""
    a = generate_token(SECRET, TERMINAL, now=T0)
    b = generate_token(SECRET, TERMINAL, now=T0 + 5)

    assert a == b


def test_fotografi_cekilen_kod_kisa_surede_gecersiz_olur():
    """QR kanalının temel güvenlik iddiası budur."""
    token = generate_token(SECRET, TERMINAL, now=T0)

    # Birkaç dakika sonra okutmaya çalışmak
    with pytest.raises(QRTokenError, match="süresi dolmuş"):
        verify_token(token, resolver, now=T0 + 300)


def test_tolerans_penceresi_icinde_kod_kabul_edilir():
    """Kullanıcının kodu görüp telefonu kaldırması zaman alır."""
    token = generate_token(SECRET, TERMINAL, now=T0)

    # Bir dilim sonra hâlâ geçerli
    result = verify_token(token, resolver, now=T0 + DEFAULT_PERIOD_SECONDS)
    assert result.terminal_code == TERMINAL


def test_iki_dilim_sonra_kod_reddedilir():
    token = generate_token(SECRET, TERMINAL, now=T0)

    with pytest.raises(QRTokenError):
        verify_token(token, resolver, now=T0 + DEFAULT_PERIOD_SECONDS * 3)


def test_baska_terminalin_anahtariyla_uretilen_kod_reddedilir():
    """Bir terminalin kodu başka kapıda geçerli olmamalı."""
    other_secret = derive_terminal_secret(MASTER, "DEPO-KAPI")
    # DEPO-KAPI anahtarıyla imzalanmış ama MERKEZ-GIRIS-1 adına kod
    forged = generate_token(other_secret, TERMINAL, now=T0)

    with pytest.raises(QRTokenError, match="imzası"):
        verify_token(forged, resolver, now=T0)


def test_imzasi_kurcalanmis_kod_reddedilir():
    token = generate_token(SECRET, TERMINAL, now=T0)
    terminal_code, period, signature = token.split(".")
    tampered = f"{terminal_code}.{period}.{'A' * len(signature)}"

    with pytest.raises(QRTokenError, match="imzası"):
        verify_token(tampered, resolver, now=T0)


def test_zaman_dilimi_ileri_alinmis_kod_reddedilir():
    """Saldırgan dilimi ileri alıp kodu uzun süre geçerli kılamamalı."""
    token = generate_token(SECRET, TERMINAL, now=T0)
    terminal_code, period, signature = token.split(".")
    forged = f"{terminal_code}.{int(period) + 100}.{signature}"

    with pytest.raises(QRTokenError):
        verify_token(forged, resolver, now=T0)


def test_bilinmeyen_terminal_reddedilir():
    secret = derive_terminal_secret(MASTER, "OLMAYAN-KAPI")
    token = generate_token(secret, "OLMAYAN-KAPI", now=T0)

    with pytest.raises(QRTokenError, match="bilinmeyen"):
        verify_token(token, resolver, now=T0)


@pytest.mark.parametrize(
    "bozuk", ["", "abc", "a.b", "a.b.c.d", "MERKEZ.abc.imza"]
)
def test_bozuk_bicimli_kodlar_reddedilir(bozuk):
    with pytest.raises(QRTokenError):
        verify_token(bozuk, resolver, now=T0)


def test_terminal_anahtarlari_birbirinden_farklidir():
    """Bir terminalin anahtarı sızsa diğerleri etkilenmemeli."""
    a = derive_terminal_secret(MASTER, "KAPI-A")
    b = derive_terminal_secret(MASTER, "KAPI-B")

    assert a != b


def test_ayni_terminal_icin_anahtar_tekrar_uretilebilir():
    """Anahtar veritabanında saklanmaz, her seferinde türetilir."""
    assert derive_terminal_secret(MASTER, TERMINAL) == derive_terminal_secret(
        MASTER, TERMINAL
    )
