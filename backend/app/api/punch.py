"""QR kod ile mobil okutma ucu.

Bu, kart kanalının alternatifidir; kartın yerine geçer, puantaj motorunu
etkilemez. Kayıt aynı attendance_events tablosuna channel='qr' ile düşer.

DOĞRULAMA ZİNCİRİ - sıra önemlidir, her katman farklı bir saldırıyı keser:

  1. Kimlik      : çalışanın oturumu (JWT)          -> kim olduğunu söyler
  2. Dönen QR    : terminal ekranındaki güncel kod  -> ORADA olduğunu kanıtlar
  3. Cihaz bağı  : kayıtlı cihaz                    -> hesap ele geçse bile korur
  4. Konum       : coğrafi çit                      -> destekleyici kanıt

Asıl güvence 2. adımdır. Konum tek başına zayıftır (sahte konum üretmek
kolaydır); dönen QR olmadan konum doğrulaması güvenlik tiyatrosudur.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..models import AttendanceEvent, Employee, EmployeeDevice, Site, Terminal
from ..services.geofence import GeofenceStatus, check_geofence
from ..services.qr_token import QRTokenError, derive_terminal_secret, verify_token
from ..services.resolver import resolve_direction
from .deps import get_current_employee

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/punch", tags=["punch"])


class QRPunchRequest(BaseModel):
    """Mobil uygulamanın gönderdiği okutma isteği."""

    qr_token: str = Field(..., description="Terminal ekranından okunan QR içeriği")
    client_event_id: uuid.UUID

    # Konum - cihaz izin vermediyse boş gelebilir
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0)
    # Android/iOS sahte konum sağlayıcı bildirimi
    mock_location: bool = False

    device_id: str | None = None
    device_name: str | None = None
    platform: str | None = None


@router.post("/qr", status_code=status.HTTP_201_CREATED)
def punch_with_qr(
    payload: QRPunchRequest,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    now = datetime.now(UTC)

    # --- 1. QR kodu doğrula, terminali bul --------------------------------
    def resolve_secret(terminal_code: str) -> str | None:
        terminal = db.execute(
            select(Terminal).where(
                Terminal.code == terminal_code,
                Terminal.active.is_(True),
                Terminal.qr_enabled.is_(True),
            )
        ).scalar_one_or_none()
        if terminal is None:
            return None
        return derive_terminal_secret(settings.qr_master_secret, terminal_code)

    try:
        verified = verify_token(payload.qr_token, resolve_secret)
    except QRTokenError as exc:
        # Süresi dolmuş kod kullanıcı hatasıdır; mesajı anlaşılır tutuyoruz.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    terminal = db.execute(
        select(Terminal).where(Terminal.code == verified.terminal_code)
    ).scalar_one()

    # --- 2. Cihaz bağı ----------------------------------------------------
    if settings.qr_require_registered_device:
        if not payload.device_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Cihaz kimliği gönderilmedi."
            )
        device = db.execute(
            select(EmployeeDevice).where(
                EmployeeDevice.device_id == payload.device_id,
                EmployeeDevice.revoked_at.is_(None),
            )
        ).scalar_one_or_none()

        if device is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Bu cihaz kayıtlı değil. Yöneticinizden cihaz kaydı isteyin.",
            )
        if device.employee_id != employee.id:
            # Cihaz başkasına kayıtlı: kart ödünç vermenin mobil karşılığı.
            log.warning(
                "Cihaz %s personel %s adına kayıtlı, okutmayı %s denedi.",
                payload.device_id,
                device.employee_id,
                employee.id,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Bu cihaz başka bir çalışana kayıtlı."
            )
        device.last_used_at = now

    # --- 3. Konum / coğrafi çit ------------------------------------------
    site = db.execute(select(Site).where(Site.id == terminal.site_id)).scalar_one()

    # Terminal kendi çitini tanımlamışsa o kullanılır; kampüsteki uzak
    # kapılar için bu ayrım gerekir.
    center_lat = terminal.latitude if terminal.latitude is not None else site.latitude
    center_lon = terminal.longitude if terminal.longitude is not None else site.longitude
    radius = terminal.geofence_radius_m or site.geofence_radius_m

    if site.geofence_enforcement == "off":
        geofence = check_geofence(
            center_lat=None, center_lon=None, radius_m=None,
            reported_lat=None, reported_lon=None,
        )
    else:
        geofence = check_geofence(
            center_lat=center_lat,
            center_lon=center_lon,
            radius_m=radius,
            reported_lat=payload.latitude,
            reported_lon=payload.longitude,
            accuracy_m=payload.accuracy_m,
        )

    reject_reason: str | None = None

    if payload.mock_location:
        # Sahte konum bildirimi kaydı düşürmez ama iz bırakır: tek seferlik
        # bir cihaz ayarı olabilir, tekrarlıyorsa incelenmesi gerekir.
        log.warning(
            "Personel %s sahte konum sağlayıcı bildiren cihazdan okuttu.", employee.id
        )
        reject_reason = "mock_location"

    if geofence.status == GeofenceStatus.OUTSIDE:
        if site.geofence_enforcement == "reject":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                geofence.reason or "İş yeri konumunun dışındasınız.",
            )
        # 'flag' politikası: kaydı düşürmüyoruz, amir onayına düşürüyoruz.
        # GPS kapalı alanda sapar; kaydı silmek sorunu araştırılamaz yapar.
        reject_reason = "outside_geofence"

    # --- 4. Kaydet --------------------------------------------------------
    direction = resolve_direction(db, terminal, employee, now)

    event = AttendanceEvent(
        terminal_id=terminal.id,
        channel="qr",
        card_uid=None,
        read_at=now,
        received_at=now,
        employee_id=employee.id,
        direction=direction,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_m=payload.accuracy_m,
        geofence_status=geofence.status,
        distance_m=geofence.distance_m,
        mock_location_flagged=payload.mock_location,
        device_id=payload.device_id,
        client_event_id=payload.client_event_id,
        reject_reason=reject_reason,
        raw={"qr_age_seconds": verified.age_seconds, "platform": payload.platform},
        created_at=now,
    )
    db.add(event)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Mobil istemcinin yeniden gönderimi; beklenen durum.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu okutma zaten kayıtlı."
        ) from None

    return {
        "id": event.id,
        "direction": direction,
        "terminal": terminal.name,
        "geofence_status": geofence.status,
        "distance_m": geofence.distance_m,
        "needs_review": reject_reason is not None,
        "display_name": employee.full_name,
    }
