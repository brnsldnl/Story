"""Ingest API entegrasyon testleri (gerçek PostgreSQL'e karşı).

Bu testler edge agent ile sunucu arasındaki sözleşmeyi doğrular. Özellikle
mükerrer koruması kritiktir: offline kuyruk aynı olayı tekrar gönderdiğinde
ikinci bir puantaj hareketi oluşmamalıdır.
"""

from __future__ import annotations

import json
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

from app.api.deps import hash_terminal_key  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

TERMINAL_CODE = "TEST-KAPI-1"
TERMINAL_KEY = "test-anahtar-123"
CARD_UID = "04A2B3C4D5"


@pytest.fixture(autouse=True)
def clean_db():
    """Her testten önce veriyi temizle."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE card_reads, photos, cards, employees, terminals, "
                "sites, departments RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture()
def seeded():
    """Bir lokasyon, bir terminal, bir personel ve kartı oluşturur."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        site_id = db.execute(
            text(
                "INSERT INTO sites (code, name, created_at) "
                "VALUES ('MERKEZ', 'Merkez Ofis', :now) RETURNING id"
            ),
            {"now": now},
        ).scalar_one()

        terminal_id = db.execute(
            text(
                "INSERT INTO terminals (site_id, code, name, direction_mode, "
                "api_key_hash, created_at) "
                "VALUES (:site, :code, 'Ana Giriş', 'toggle', :key, :now) RETURNING id"
            ),
            {
                "site": site_id,
                "code": TERMINAL_CODE,
                "key": hash_terminal_key(TERMINAL_KEY),
                "now": now,
            },
        ).scalar_one()

        employee_id = db.execute(
            text(
                "INSERT INTO employees (employee_no, first_name, last_name, "
                "site_id, created_at, updated_at) "
                "VALUES ('1001', 'Ayşe', 'Yılmaz', :site, :now, :now) RETURNING id"
            ),
            {"site": site_id, "now": now},
        ).scalar_one()

        db.execute(
            text(
                "INSERT INTO cards (uid, technology, employee_id, valid_from, "
                "status, created_at) "
                "VALUES (:uid, 'mifare', :emp, :from_, 'active', :now)"
            ),
            {
                "uid": CARD_UID,
                "emp": employee_id,
                "from_": now - timedelta(days=30),
                "now": now,
            },
        )
        db.commit()

    return {"site_id": site_id, "terminal_id": terminal_id, "employee_id": employee_id}


@pytest.fixture()
def client():
    return TestClient(app)


def auth_headers(code: str = TERMINAL_CODE, key: str = TERMINAL_KEY) -> dict[str, str]:
    return {"X-Terminal-Code": code, "X-Terminal-Key": key}


def card_read_payload(**overrides):
    payload = {
        "client_event_id": str(uuid.uuid4()),
        "card_uid": CARD_UID,
        "read_at": datetime.now(timezone.utc).isoformat(),
        "technology": "mifare",
        "raw": {},
    }
    payload.update(overrides)
    return payload


def post_read(client, payload, photo: bytes | None = None):
    files = {"payload": (None, json.dumps(payload), "application/json")}
    if photo is not None:
        files["photo"] = ("snap.jpg", photo, "image/jpeg")
    return client.post("/api/v1/ingest/card-read", files=files, headers=auth_headers())


# ---------------------------------------------------------------------


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_gecerli_kart_okumasi_kaydedilir(client, seeded):
    response = post_read(client, card_read_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["recognized"] is True
    assert body["employee_id"] == seeded["employee_id"]
    assert body["display_name"] == "Ayşe Yılmaz"
    # İlk hareket giriş olmalı
    assert body["direction"] == "in"


def test_ayni_olay_iki_kez_gonderilirse_tek_kayit_olusur(client, seeded):
    """Offline kuyruğun yeniden gönderimi mükerrer puantaj üretmemeli."""
    payload = card_read_payload()

    first = post_read(client, payload)
    second = post_read(client, payload)

    assert first.status_code == 201
    assert second.status_code == 409

    with SessionLocal() as db:
        count = db.execute(text("SELECT COUNT(*) FROM card_reads")).scalar_one()
    assert count == 1


def test_yon_sirayla_giris_cikis_olur(client, seeded):
    now = datetime.now(timezone.utc)

    first = post_read(client, card_read_payload(read_at=now.isoformat()))
    second = post_read(
        client, card_read_payload(read_at=(now + timedelta(hours=8)).isoformat())
    )
    third = post_read(
        client, card_read_payload(read_at=(now + timedelta(hours=9)).isoformat())
    )

    assert first.json()["direction"] == "in"
    assert second.json()["direction"] == "out"
    assert third.json()["direction"] == "in"


def test_taninmayan_kart_da_kaydedilir(client, seeded):
    """Kayıt düşürmek 'kartım çalışmıyor' şikayetini araştırılamaz yapar."""
    response = post_read(client, card_read_payload(card_uid="BILINMEYEN1"))

    assert response.status_code == 201
    assert response.json()["recognized"] is False

    with SessionLocal() as db:
        reason = db.execute(
            text("SELECT reject_reason FROM card_reads WHERE card_uid = 'BILINMEYEN1'")
        ).scalar_one()
    assert reason == "unknown_card"


def test_fotograf_kaydedilir_ve_imha_tarihi_atanir(client, seeded):
    """KVKK: her fotoğrafın imha tarihi kaydın kendisinde taşınmalı."""
    response = post_read(client, card_read_payload(), photo=b"\xff\xd8\xff\xe0sahte-jpeg")

    assert response.status_code == 201

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT p.byte_size, p.purge_after, p.storage_key "
                "FROM photos p JOIN card_reads c ON c.photo_id = p.id"
            )
        ).one()

    assert row.byte_size == len(b"\xff\xd8\xff\xe0sahte-jpeg")
    assert row.purge_after > datetime.now(timezone.utc)
    assert row.storage_key.endswith(".jpg")


def test_fotografsiz_okuma_kabul_edilir(client, seeded):
    """Kamera arızası puantajı durdurmamalı."""
    response = post_read(client, card_read_payload(), photo=None)

    assert response.status_code == 201
    with SessionLocal() as db:
        photo_id = db.execute(text("SELECT photo_id FROM card_reads")).scalar_one()
    assert photo_id is None


def test_yanlis_anahtar_reddedilir(client, seeded):
    files = {"payload": (None, json.dumps(card_read_payload()), "application/json")}
    response = client.post(
        "/api/v1/ingest/card-read",
        files=files,
        headers=auth_headers(key="yanlis-anahtar"),
    )
    assert response.status_code == 401


def test_bilinmeyen_terminal_reddedilir(client, seeded):
    files = {"payload": (None, json.dumps(card_read_payload()), "application/json")}
    response = client.post(
        "/api/v1/ingest/card-read",
        files=files,
        headers=auth_headers(code="OLMAYAN-KAPI"),
    )
    assert response.status_code == 401


def test_heartbeat_terminal_son_gorulme_zamanini_gunceller(client, seeded):
    response = client.post(
        "/api/v1/ingest/heartbeat",
        json={"queue_depth": 3, "agent_version": "0.1.0"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT last_seen_at, agent_version FROM terminals WHERE code = :c"),
            {"c": TERMINAL_CODE},
        ).one()

    assert row.last_seen_at is not None
    assert row.agent_version == "0.1.0"


def test_gecmis_tarihli_okuma_kabul_edilir(client, seeded):
    """Offline kalmış terminal günler sonra veri gönderebilir."""
    old = datetime.now(timezone.utc) - timedelta(days=2)
    response = post_read(client, card_read_payload(read_at=old.isoformat()))

    assert response.status_code == 201
    with SessionLocal() as db:
        row = db.execute(text("SELECT read_at, received_at FROM card_reads")).one()
    # read_at korunur, received_at şimdiyi gösterir: offline süre ölçülebilir
    assert row.received_at > row.read_at
