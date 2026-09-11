"""Puantaj motoru testleri.

Bu testler iş kurallarının yazılı halidir. Mevzuat veya şirket politikası
değiştiğinde önce buradaki beklentiler değişmeli, sonra motor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.services.attendance_engine import (
    DayContext,
    DayStatus,
    Punch,
    ShiftRule,
    compute_day,
    night_minutes_in,
    pair_punches,
)

TZ = UTC

GUNDUZ = ShiftRule(
    code="GUNDUZ",
    start_time=time(8, 0),
    end_time=time(18, 0),
    break_minutes=60,
    grace_in_minutes=10,
    min_overtime_minutes=15,
    overtime_requires_approval=True,
)

# 22:00 - 06:00: gün sınırını aşan gece vardiyası
GECE = ShiftRule(
    code="GECE",
    start_time=time(22, 0),
    end_time=time(6, 0),
    crosses_midnight=True,
    break_minutes=60,
    overtime_requires_approval=False,
)


def dt(day: int, hour: int, minute: int = 0, month: int = 3) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


def punches(*items: tuple[datetime, str]) -> list[Punch]:
    return [Punch(at=at, direction=direction) for at, direction in items]


# ---------------------------------------------------------------------
# Temel gün
# ---------------------------------------------------------------------


def test_normal_gun_mola_dusulur():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in"), (dt(2, 18, 0), "out")),
        shift=GUNDUZ,
    )
    result = compute_day(ctx)

    assert result.status == DayStatus.OK
    # Brüt 10 saat, 1 saat mola -> 9 saat
    assert result.worked_minutes == 9 * 60
    assert result.break_minutes == 60
    assert result.late_minutes == 0


def test_tolerans_icindeki_gecikme_gec_kalma_sayilmaz():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 8), "in"), (dt(2, 18, 0), "out")),
        shift=GUNDUZ,  # 10 dakika tolerans
    )
    assert compute_day(ctx).late_minutes == 0


def test_tolerans_disindaki_gecikme_yalnizca_asan_kismi_sayar():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 25), "in"), (dt(2, 18, 0), "out")),
        shift=GUNDUZ,
    )
    # 25 dk geç, 10 dk tolerans -> 15 dk
    assert compute_day(ctx).late_minutes == 15


def test_erken_cikis_hesaplanir():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in"), (dt(2, 17, 30), "out")),
        shift=GUNDUZ,
    )
    assert compute_day(ctx).early_leave_minutes == 30


# ---------------------------------------------------------------------
# GECE VARDİYASI - gün sınırını aşan durum
# ---------------------------------------------------------------------


def test_gece_vardiyasi_ertesi_gune_tasan_cikisi_dogru_hesaplar():
    """1 Mart 22:00 girişi, 2 Mart 06:00 çıkışı -> 1 Mart'ın puantajı."""
    ctx = DayContext(
        work_date=date(2026, 3, 1),
        punches=punches((dt(1, 22, 0), "in"), (dt(2, 6, 0), "out")),
        shift=GECE,
    )
    result = compute_day(ctx)

    assert result.status == DayStatus.OK
    # Brüt 8 saat, 1 saat mola -> 7 saat
    assert result.worked_minutes == 7 * 60
    # Vardiya tam süresinde bitti: erken çıkış YOK.
    # Bu kontrol, bitişin ertesi güne ait olduğunu doğrular.
    assert result.early_leave_minutes == 0
    assert result.late_minutes == 0


def test_gece_vardiyasinda_gec_gelen_dogru_hesaplanir():
    ctx = DayContext(
        work_date=date(2026, 3, 1),
        punches=punches((dt(1, 22, 30), "in"), (dt(2, 6, 0), "out")),
        shift=GECE,
    )
    assert compute_day(ctx).late_minutes == 30


def test_gece_vardiyasinda_erken_cikan_dogru_hesaplanir():
    ctx = DayContext(
        work_date=date(2026, 3, 1),
        punches=punches((dt(1, 22, 0), "in"), (dt(2, 5, 15), "out")),
        shift=GECE,
    )
    assert compute_day(ctx).early_leave_minutes == 45


def test_gece_dakikalari_20_06_araligini_sayar():
    ctx = DayContext(
        work_date=date(2026, 3, 1),
        punches=punches((dt(1, 22, 0), "in"), (dt(2, 6, 0), "out")),
        shift=GECE,
    )
    # 22:00-06:00 tamamen gece dönemi içinde -> 480 dakika
    assert compute_day(ctx).night_minutes == 480


# ---------------------------------------------------------------------
# night_minutes_in birim testleri
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # Tamamen gündüz
        ((2, 9, 0), (2, 17, 0), 0),
        # Tamamen gece (gece yarısını aşan)
        ((1, 22, 0), (2, 6, 0), 480),
        # Kısmen gece: 18:00-22:00 -> yalnız 20:00-22:00 sayılır
        ((2, 18, 0), (2, 22, 0), 120),
        # Sabah kısmı: 05:00-09:00 -> yalnız 05:00-06:00
        ((2, 5, 0), (2, 9, 0), 60),
        # Tam 24 saat -> günde 10 saat gece
        ((1, 0, 0), (2, 0, 0), 600),
        # Sıfır uzunluk
        ((2, 9, 0), (2, 9, 0), 0),
    ],
)
def test_night_minutes_in(start, end, expected):
    assert night_minutes_in(dt(*start), dt(*end)) == expected


# ---------------------------------------------------------------------
# Eksik okutma senaryoları
# ---------------------------------------------------------------------


def test_cikis_okutmayi_unutan_isaretlenir():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in")),
        shift=GUNDUZ,
    )
    result = compute_day(ctx)

    assert result.status == DayStatus.MISSING_OUT
    # Tahmin yürütmüyoruz: çıkış bilinmiyorsa süre yazmayız.
    assert result.worked_minutes == 0
    assert result.warnings


def test_girissiz_cikis_isaretlenir():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 18, 0), "out")),
        shift=GUNDUZ,
    )
    assert compute_day(ctx).status == DayStatus.MISSING_IN


def test_hic_okutma_yoksa_devamsiz():
    ctx = DayContext(work_date=date(2026, 3, 2), punches=[], shift=GUNDUZ)
    assert compute_day(ctx).status == DayStatus.ABSENT


def test_izinli_gun_devamsiz_sayilmaz():
    ctx = DayContext(
        work_date=date(2026, 3, 2), punches=[], shift=GUNDUZ, is_on_leave=True
    )
    assert compute_day(ctx).status == DayStatus.LEAVE


def test_resmi_tatil_devamsiz_sayilmaz():
    ctx = DayContext(
        work_date=date(2026, 4, 23), punches=[], shift=GUNDUZ, is_holiday=True
    )
    assert compute_day(ctx).status == DayStatus.HOLIDAY


# ---------------------------------------------------------------------
# Mesai ve onay
# ---------------------------------------------------------------------


def test_onaysiz_mesai_ucretlendirilmez_ama_raporlanir():
    """Amir onayı olmadan kapıda kalan süre maliyete dönüşmemeli."""
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in"), (dt(2, 20, 0), "out")),
        shift=GUNDUZ,
        approved_overtime_minutes=None,
    )
    result = compute_day(ctx)

    assert result.normal_minutes == 9 * 60
    assert result.overtime_minutes == 0
    assert result.unapproved_overtime_minutes == 2 * 60


def test_onayli_mesai_onaylanan_kadar_yazilir():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in"), (dt(2, 20, 0), "out")),
        shift=GUNDUZ,
        approved_overtime_minutes=60,
    )
    result = compute_day(ctx)

    # 2 saat fazla kaldı ama 1 saat onaylandı
    assert result.overtime_minutes == 60
    assert result.unapproved_overtime_minutes == 60


def test_esik_altindaki_fazla_kalma_mesai_sayilmaz():
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches((dt(2, 8, 0), "in"), (dt(2, 18, 8), "out")),
        shift=GUNDUZ,  # min_overtime_minutes = 15
        approved_overtime_minutes=60,
    )
    assert compute_day(ctx).overtime_minutes == 0


def test_resmi_tatilde_calisma_ayri_kolona_yazilir():
    ctx = DayContext(
        work_date=date(2026, 4, 23),
        punches=punches((dt(23, 8, 0, month=4), "in"), (dt(23, 18, 0, month=4), "out")),
        shift=GUNDUZ,
        is_holiday=True,
        approved_overtime_minutes=0,
    )
    result = compute_day(ctx)

    # Tatil çalışması farklı katsayıyla ücretlendirilir; ayrı izlenmeli.
    assert result.holiday_minutes == 9 * 60
    assert result.weekend_minutes == 0


# ---------------------------------------------------------------------
# Hareket eşleme
# ---------------------------------------------------------------------


def test_mola_icin_cikip_giren_sure_dusulur():
    """Kartla mola: çiftler arasındaki boşluk çalışma sayılmaz."""
    kartli_mola = ShiftRule(
        code="KARTLI",
        start_time=time(8, 0),
        end_time=time(18, 0),
        break_mode="card",
        overtime_requires_approval=False,
    )
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=punches(
            (dt(2, 8, 0), "in"),
            (dt(2, 12, 0), "out"),
            (dt(2, 13, 0), "in"),
            (dt(2, 18, 0), "out"),
        ),
        shift=kartli_mola,
    )
    result = compute_day(ctx)

    assert result.worked_minutes == 9 * 60  # 4 + 5 saat
    assert result.break_minutes == 60


def test_pair_punches_sirasiz_gelen_hareketleri_sıralar():
    items = punches((dt(2, 18, 0), "out"), (dt(2, 8, 0), "in"))
    pairs, warnings = pair_punches(items)

    assert len(pairs) == 1
    assert pairs[0][0].at == dt(2, 8, 0)
    assert not warnings


def test_pair_punches_arka_arkaya_iki_giris_uyarir():
    items = punches((dt(2, 8, 0), "in"), (dt(2, 9, 0), "in"), (dt(2, 18, 0), "out"))
    pairs, warnings = pair_punches(items)

    assert len(pairs) == 1
    assert warnings


def test_duzeltmeli_gun_isaretlenir():
    """Manuel düzeltme yapılan günler panelde ayırt edilebilmeli."""
    ctx = DayContext(
        work_date=date(2026, 3, 2),
        punches=[
            Punch(at=dt(2, 8, 0), direction="in", source="card"),
            Punch(at=dt(2, 18, 0), direction="out", source="adjustment"),
        ],
        shift=GUNDUZ,
    )
    assert compute_day(ctx).has_adjustment is True
