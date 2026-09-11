"""QR ile mobil okutma entegrasyon testleri.

Doğrulama zincirinin her katmanını ayrı ayrı sınar: süresi dolmuş kod,
kayıtsız cihaz, başkasının cihazı, çit dışı konum, sahte konum.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"
)
os.environ.setdefault("PHOTO_STORAGE_PATH", "/tmp/pdks-test-photos")

from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.services.qr_token import (  # noqa: E402
    DEFAULT_PERIOD_SECONDS,
    derive_terminal_secret,
    generate_token,
)

TERMINAL_CODE = "QR-KAPI-1"
SITE_LAT, SITE_LON = 41.0821, 29.0100
DEVICE_ID = "cihaz-abc-123"
PASSWORD = "cok-gizli-parola"


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE attendance_events, employee_devices, photos, cards, "
                "users, employees, terminals, sites, departments "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture()
def seeded():
    """Çit tanımlı bir lokasyon, QR açık terminal, personel, kullanıcı, cihaz."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        site_id = db.execute(
            text(
                "INSERT INTO sites (code, name, latitude, longitude, "
                "geofence_radius_m, geofence_enforcement, created_at) "
                "VALUES ('MERKEZ','Merkez',:lat,:lon,150,'flag',:n) RETURNING id"
            ),
            {"lat": SITE_LAT, "lon": SITE_LON, "n": now},
        ).scalar_one()

        db.execute(
            text(
                "INSERT INTO terminals (site_id, code, name, direction_mode, "
                "api_key_hash, qr_enabled, created_at) "
                "VALUES (:s,:c,'QR Kapı','toggle','x',TRUE,:n)"
            ),
            {"s": site_id, "c": TERMINAL_CODE, "n": now},
        )

        emp_id = db.execute(
            text(
                "INSERT INTO employees (employee_no, first_name, last_name, "
                "site_id, created_at, updated_at) "
                "VALUES ('3001','Zeynep','Kaya',:s,:n,:n) RETURNING id"
            ),
            {"s": site_id, "n": now},
        ).scalar_one()

        other_emp_id = db.execute(
            text(
                "INSERT INTO employees (employee_no, first_name, last_name, "
                "site_id, created_at, updated_at) "
                "VALUES ('3002','Can','Ak',:s,:n,:n) RETURNING id"
            ),
            {"s": site_id, "n": now},
        ).scalar_one()

        db.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name, role, "
                "employee_id, created_at) "
                "VALUES ('zeynep@sirket.com',:p,'Zeynep Kaya','employee',:e,:n)"
            ),
            {"p": hash_password(PASSWORD), "e": emp_id, "n": now},
        )

        db.execute(
            text(
                "INSERT INTO employee_devices (employee_id, device_id, "
                "device_name, platform, registered_at) "
                "VALUES (:e,:d,'Zeynep telefonu','android',:n)"
            ),
            {"e": emp_id, "d": DEVICE_ID, "n": now},
        )
        db.commit()

    return {"site_id": site_id, "employee_id": emp_id, "other_employee_id": other_emp_id}


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def token(client, seeded):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "zeynep@sirket.com", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def current_qr() -> str:
    from app.core.config import get_settings

    secret = derive_terminal_secret(get_settings().qr_master_secret, TERMINAL_CODE)
    return generate_token(secret, TERMINAL_CODE)


def punch(client, token, **overrides):
    body = {
        "qr_token": current_qr(),
        "client_event_id": str(uuid.uuid4()),
        "latitude": SITE_LAT,
        "longitude": SITE_LON,
        "accuracy_m": 12,
        "mock_location": False,
        "device_id": DEVICE_ID,
        "platform": "android",
    }
    body.update(overrides)
    return client.post(
        "/api/v1/punch/qr", json=body, headers={"Authorization": f"Bearer {token}"}
    )


# --- Mutlu yol -------------------------------------------------------


def test_gecerli_qr_ve_konum_ile_okutma_kaydedilir(client, token, seeded):
    response = punch(client, token)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["direction"] == "in"
    assert body["geofence_status"] == "inside"
    assert body["needs_review"] is False
    assert body["display_name"] == "Zeynep Kaya"

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT channel, card_uid, employee_id FROM attendance_events")
        ).one()
    assert row.channel == "qr"
    assert row.card_uid is None
    assert row.employee_id == seeded["employee_id"]


def test_qr_okutma_kart_ile_ayni_yon_mantigini_kullanir(client, token, seeded):
    """İki kanal aynı tabloya yazdığı için giriş/çıkış sırası ortak."""
    assert punch(client, token).json()["direction"] == "in"
    assert punch(client, token).json()["direction"] == "out"


# --- Kimlik doğrulama ------------------------------------------------


def test_oturumsuz_okutma_reddedilir(client, seeded):
    response = client.post(
        "/api/v1/punch/qr",
        json={"qr_token": current_qr(), "client_event_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


def test_yanlis_parola_ile_giris_reddedilir(client, seeded):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "zeynep@sirket.com", "password": "yanlis"},
    )
    assert response.status_code == 401


# --- QR kod katmanı --------------------------------------------------


def test_suresi_dolmus_qr_reddedilir(client, token, seeded):
    """Ekranın fotoğrafını çekip sonra okutmak işe yaramamalı."""
    from app.core.config import get_settings

    secret = derive_terminal_secret(get_settings().qr_master_secret, TERMINAL_CODE)
    eski = generate_token(
        secret,
        TERMINAL_CODE,
        now=datetime.now(timezone.utc).timestamp() - DEFAULT_PERIOD_SECONDS * 10,
    )

    response = punch(client, token, qr_token=eski)
    assert response.status_code == 400
    assert "süresi dolmuş" in response.json()["detail"]


def test_uydurma_qr_reddedilir(client, token, seeded):
    response = punch(client, token, qr_token="QR-KAPI-1.99999.sahteimza")
    assert response.status_code == 400


def test_qr_kapali_terminalin_kodu_kabul_edilmez(client, token, seeded):
    with SessionLocal() as db:
        db.execute(
            text("UPDATE terminals SET qr_enabled = FALSE WHERE code = :c"),
            {"c": TERMINAL_CODE},
        )
        db.commit()

    response = punch(client, token)
    assert response.status_code == 400


# --- Cihaz bağı ------------------------------------------------------


def test_kayitsiz_cihazdan_okutma_reddedilir(client, token, seeded):
    response = punch(client, token, device_id="bilinmeyen-cihaz")
    assert response.status_code == 403
    assert "kayıtlı değil" in response.json()["detail"]


def test_baskasinin_cihazindan_okutma_reddedilir(client, token, seeded):
    """Kart ödünç vermenin mobil karşılığı."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO employee_devices (employee_id, device_id, "
                "registered_at) VALUES (:e,'can-telefonu',:n)"
            ),
            {"e": seeded["other_employee_id"], "n": now},
        )
        db.commit()

    response = punch(client, token, device_id="can-telefonu")
    assert response.status_code == 403
    assert "başka bir çalışana" in response.json()["detail"]


def test_iptal_edilmis_cihaz_reddedilir(client, token, seeded):
    with SessionLocal() as db:
        db.execute(
            text("UPDATE employee_devices SET revoked_at = now() WHERE device_id = :d"),
            {"d": DEVICE_ID},
        )
        db.commit()

    assert punch(client, token).status_code == 403


# --- Konum katmanı ---------------------------------------------------


def test_cit_disindan_okutma_isaretlenir_ama_kaydedilir(client, token, seeded):
    """Varsayılan 'flag' politikası: kaydı düşürmek yerine incelemeye al."""
    response = punch(client, token, latitude=SITE_LAT + 0.05, longitude=SITE_LON)

    assert response.status_code == 201
    body = response.json()
    assert body["geofence_status"] == "outside"
    assert body["needs_review"] is True
    assert body["distance_m"] > 1000

    with SessionLocal() as db:
        reason = db.execute(
            text("SELECT reject_reason FROM attendance_events")
        ).scalar_one()
    assert reason == "outside_geofence"


def test_reject_politikasinda_cit_disi_okutma_reddedilir(client, token, seeded):
    with SessionLocal() as db:
        db.execute(text("UPDATE sites SET geofence_enforcement = 'reject'"))
        db.commit()

    response = punch(client, token, latitude=SITE_LAT + 0.05, longitude=SITE_LON)
    assert response.status_code == 403

    with SessionLocal() as db:
        count = db.execute(text("SELECT COUNT(*) FROM attendance_events")).scalar_one()
    assert count == 0


def test_konum_kapaliyken_okutma_kaydedilir(client, token, seeded):
    """Konum asıl güvence değil; QR kodu zaten fiziksel varlığı kanıtlıyor."""
    response = punch(client, token, latitude=None, longitude=None, accuracy_m=None)

    assert response.status_code == 201
    assert response.json()["geofence_status"] == "unknown"


def test_sahte_konum_bildiren_cihaz_isaretlenir(client, token, seeded):
    response = punch(client, token, mock_location=True)

    assert response.status_code == 201
    assert response.json()["needs_review"] is True

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT mock_location_flagged, reject_reason FROM attendance_events"
            )
        ).one()
    assert row.mock_location_flagged is True
    assert row.reject_reason == "mock_location"


def test_cit_kapaliysa_konum_kontrol_edilmez(client, token, seeded):
    with SessionLocal() as db:
        db.execute(text("UPDATE sites SET geofence_enforcement = 'off'"))
        db.commit()

    response = punch(client, token, latitude=SITE_LAT + 1.0, longitude=SITE_LON)
    assert response.status_code == 201
    assert response.json()["geofence_status"] == "not_required"


# --- Mükerrer koruması -----------------------------------------------


def test_ayni_olay_iki_kez_gonderilirse_tek_kayit_olusur(client, token, seeded):
    event_id = str(uuid.uuid4())

    first = punch(client, token, client_event_id=event_id)
    second = punch(client, token, client_event_id=event_id)

    assert first.status_code == 201
    assert second.status_code == 409

    with SessionLocal() as db:
        count = db.execute(text("SELECT COUNT(*) FROM attendance_events")).scalar_one()
    assert count == 1
