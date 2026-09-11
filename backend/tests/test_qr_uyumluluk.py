"""Terminal ile sunucunun QR algoritmalarının aynı olduğunu doğrular.

edge/pdks_edge/qr_display.py ve backend/app/services/qr_token.py aynı
algoritmayı BAĞIMSIZ olarak uygular. Bu kasıtlıdır: terminal agent'ı
backend paketine bağımlı olmamalı, ayrı kurulabilmelidir.

Bedeli, ikisinin zamanla birbirinden sapma riskidir. Bu test o riski
kapatır: biri değişip diğeri değişmezse burada kırılır.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.services.qr_token import derive_terminal_secret, verify_token
from app.services.qr_token import generate_token as sunucu_uret

EDGE_MODULE = (
    Path(__file__).resolve().parents[2] / "edge" / "pdks_edge" / "qr_display.py"
)


def _load_edge_module():
    spec = importlib.util.spec_from_file_location("pdks_edge_qr", EDGE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def edge():
    if not EDGE_MODULE.exists():
        pytest.skip(f"Edge modülü bulunamadı: {EDGE_MODULE}")
    return _load_edge_module()


TERMINAL = "MERKEZ-GIRIS-1"
SECRET = derive_terminal_secret("ana-anahtar-en-az-otuziki-bayt-olmali", TERMINAL)
T0 = 1_800_000_000.0


def test_terminal_ve_sunucu_ayni_kodu_uretir(edge):
    terminalden = edge.generate_token(SECRET, TERMINAL, now=T0)
    sunucudan = sunucu_uret(SECRET, TERMINAL, now=T0)

    assert terminalden == sunucudan


@pytest.mark.parametrize("offset", [0, 31, 60, 3600, 86_400])
def test_farkli_zamanlarda_da_uyumlu(edge, offset):
    assert edge.generate_token(SECRET, TERMINAL, now=T0 + offset) == sunucu_uret(
        SECRET, TERMINAL, now=T0 + offset
    )


def test_terminalin_urettigi_kodu_sunucu_dogrular(edge):
    """Asıl senaryo: terminal üretir, sunucu doğrular."""
    token = edge.generate_token(SECRET, TERMINAL, now=T0)

    result = verify_token(token, lambda code: SECRET if code == TERMINAL else None, now=T0)

    assert result.terminal_code == TERMINAL


def test_periyot_sabitleri_ayni(edge):
    from app.services import qr_token

    assert edge.DEFAULT_PERIOD_SECONDS == qr_token.DEFAULT_PERIOD_SECONDS


def test_yenilenmeye_kalan_sure_dogru(edge):
    # Dilim başlangıcından 10 saniye sonra, 30 saniyelik periyotta
    assert edge.seconds_until_refresh(now=T0 + 10) == pytest.approx(20)
