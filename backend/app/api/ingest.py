"""Terminal veri alım uçları.

Edge agent'ların konuştuğu tek yüzey burasıdır. İki tasarım kararı kritiktir:

1. MÜKERRER KORUMASI: Aynı client_event_id ile gelen ikinci istek yeni kayıt
   oluşturmaz, 409 döner. Offline kuyruk "gönderdim mi acaba" durumunda
   çekinmeden tekrar gönderebilsin diye.

2. TANINMAYAN KART DA KAYDEDİLİR: Kart eşleşmese bile okuma reject_reason ile
   yazılır. Kaydı düşürmek, "kartım çalışmıyor" şikayetini araştırılamaz hale
   getirir.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..models import CardRead, Photo, Terminal
from ..services.photo_storage import PhotoStorage
from ..services.resolver import resolve_direction, resolve_employee
from .deps import authenticate_terminal

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

MAX_PHOTO_BYTES = 2 * 1024 * 1024


@router.post("/card-read", status_code=status.HTTP_201_CREATED)
def ingest_card_read(
    payload: str = Form(...),
    photo: UploadFile | None = File(default=None),
    terminal: Terminal = Depends(authenticate_terminal),
    db: Session = Depends(get_db),
):
    """Terminalden gelen tek bir kart okumasını kaydeder."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Geçersiz JSON: {exc}") from exc

    try:
        client_event_id = uuid.UUID(data["client_event_id"])
        card_uid = str(data["card_uid"]).upper()
        read_at = datetime.fromisoformat(data["read_at"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Eksik veya hatalı alan: {exc}"
        ) from exc

    if read_at.tzinfo is None:
        read_at = read_at.replace(tzinfo=UTC)

    settings = get_settings()
    now = datetime.now(UTC)

    # Terminal saati ileri kaymışsa puantajın tamamı bozulur; sessizce kabul
    # etmek yerine uyarı bırakıyoruz.
    if read_at > now + timedelta(minutes=5):
        log.warning(
            "Terminal %s gelecek tarihli okuma gönderdi (%s). NTP senkronu kontrol edilmeli.",
            terminal.code,
            read_at,
        )

    photo_row: Photo | None = None
    if photo is not None:
        contents = photo.file.read()
        if len(contents) > MAX_PHOTO_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fotoğraf çok büyük."
            )
        storage = PhotoStorage(settings.photo_storage_path)
        storage_key, digest = storage.save(contents, read_at)

        photo_row = Photo(
            storage_key=storage_key,
            captured_at=read_at,
            sha256=digest,
            byte_size=len(contents),
            # KVKK: imha tarihi kaydın kendisinde taşınır, sonradan
            # hatırlanması gereken bir politika değildir.
            purge_after=now + timedelta(days=settings.photo_retention_days),
            created_at=now,
        )
        db.add(photo_row)
        db.flush()

    employee = resolve_employee(db, card_uid, read_at)
    reject_reason = None if employee else "unknown_card"
    direction = resolve_direction(db, terminal, employee, read_at)

    card_read = CardRead(
        terminal_id=terminal.id,
        card_uid=card_uid,
        read_at=read_at,
        received_at=now,
        employee_id=employee.id if employee else None,
        direction=direction,
        photo_id=photo_row.id if photo_row else None,
        client_event_id=client_event_id,
        reject_reason=reject_reason,
        raw=data.get("raw", {}),
        created_at=now,
    )
    db.add(card_read)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Aynı olay daha önce kaydedilmiş: offline kuyruğun tekrar gönderimi.
        # Bu bir hata değil, beklenen durum.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu olay zaten kayıtlı."
        ) from None

    return {
        "id": card_read.id,
        "employee_id": card_read.employee_id,
        "direction": direction,
        "recognized": employee is not None,
        # Terminal ekranında gösterilecek geri bildirim
        "display_name": employee.full_name if employee else "Tanınmayan kart",
    }


class HeartbeatPayload(BaseModel):
    """Terminalin kendi durumu hakkında bildirdikleri."""

    queue_depth: int = 0
    agent_version: str | None = None


@router.post("/heartbeat")
def heartbeat(
    payload: HeartbeatPayload,
    terminal: Terminal = Depends(authenticate_terminal),
    db: Session = Depends(get_db),
):
    """Terminalin hayatta olduğunu bildirir.

    Sessiz veri kaybına karşı tek savunma budur: kart okunmasa bile terminal
    heartbeat gönderir, panel 'bu kapı 3 saattir sessiz' diyebilir.

    queue_depth ayrıca erken uyarı verir: bir terminalde kuyruk birikiyorsa
    ağ sorunu vardır ve o kapının verileri henüz sunucuda değildir.
    """
    now = datetime.now(UTC)
    terminal.last_seen_at = now
    if payload.agent_version:
        terminal.agent_version = payload.agent_version
    db.commit()

    if payload.queue_depth > 50:
        log.warning(
            "Terminal %s kuyruğunda %d kayıt bekliyor; ağ bağlantısı kontrol edilmeli.",
            terminal.code,
            payload.queue_depth,
        )

    return {"ok": True, "server_time": now.isoformat()}
