"""Coğrafi çit testleri."""

from __future__ import annotations

import pytest

from app.services.geofence import (
    GeofenceStatus,
    check_geofence,
    haversine_distance_m,
)

# Referans nokta: İstanbul, Levent civarı
CENTER_LAT, CENTER_LON = 41.0821, 29.0100


def test_haversine_bilinen_mesafeyi_dogru_hesaplar():
    """1 derece enlem yaklaşık 111 km'dir."""
    distance = haversine_distance_m(41.0, 29.0, 42.0, 29.0)
    assert 110_000 < distance < 112_000


def test_ayni_nokta_sifir_mesafe():
    assert haversine_distance_m(41.0, 29.0, 41.0, 29.0) == pytest.approx(0, abs=0.1)


def test_cit_icindeki_konum_kabul_edilir():
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=CENTER_LAT + 0.0005,  # ~55 m
        reported_lon=CENTER_LON,
        accuracy_m=10,
    )
    assert result.status == GeofenceStatus.INSIDE
    assert result.distance_m is not None and result.distance_m < 150


def test_cit_disindaki_konum_isaretlenir():
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=CENTER_LAT + 0.05,  # ~5.5 km
        reported_lon=CENTER_LON,
        accuracy_m=10,
    )
    assert result.status == GeofenceStatus.OUTSIDE
    assert result.distance_m > 5000
    assert result.should_reject is True


def test_cit_tanimlanmamissa_kontrol_yapilmaz():
    result = check_geofence(
        center_lat=None,
        center_lon=None,
        radius_m=None,
        reported_lat=CENTER_LAT,
        reported_lon=CENTER_LON,
    )
    assert result.status == GeofenceStatus.NOT_REQUIRED


def test_konum_bildirilmemisse_bilinmiyor():
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=None,
        reported_lon=None,
    )
    assert result.status == GeofenceStatus.UNKNOWN


def test_dusuk_dogruluklu_konumla_karar_verilmez():
    """500 m hatalı konumla çit kontrolü yapmak anlamsızdır."""
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=CENTER_LAT + 0.05,
        reported_lon=CENTER_LON,
        accuracy_m=800,
    )
    assert result.status == GeofenceStatus.UNKNOWN
    assert "doğruluğu" in result.reason


def test_hata_payi_calisanin_lehine_sayilir():
    """Sınırda duran biri hatalı şekilde dışarıda gösterilmemeli.

    Çalışan çitin 200 m dışında görünüyor ama cihaz 100 m hata payı
    bildiriyor; sınır 150 m. Hata payı düşülünce içeride sayılır.
    """
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=CENTER_LAT + 0.0018,  # ~200 m
        reported_lon=CENTER_LON,
        accuracy_m=100,
    )
    assert result.status == GeofenceStatus.INSIDE


def test_hata_payi_sinirsiz_tolerans_saglamaz():
    """Hata payı mazeretiyle şehrin öbür ucundan okutulamamalı."""
    result = check_geofence(
        center_lat=CENTER_LAT,
        center_lon=CENTER_LON,
        radius_m=150,
        reported_lat=CENTER_LAT + 0.2,  # ~22 km
        reported_lon=CENTER_LON,
        accuracy_m=150,
    )
    assert result.status == GeofenceStatus.OUTSIDE
