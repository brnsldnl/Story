"""SQLAlchemy modelleri.

Şemanın kaynağı db/init/001_init.sql dosyasıdır; buradaki modeller o şemayı
yansıtır. Tablolar ve kısıtlar SQL tarafında tanımlıdır çünkü veri bütünlüğü
uygulamaya değil veritabanına emanet edilmelidir.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="Europe/Istanbul")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Terminal(Base):
    __tablename__ = "terminals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sites.id"))
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    direction_mode: Mapped[str] = mapped_column(Text, default="toggle")
    api_key_hash: Mapped[str] = mapped_column(Text)
    camera_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agent_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    site: Mapped[Site] = relationship()


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_no: Mapped[str] = mapped_column(Text, unique=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=True
    )
    site_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sites.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, default="manual")
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    department: Mapped[Department | None] = relationship()

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uid: Mapped[str] = mapped_column(Text, index=True)
    technology: Mapped[str] = mapped_column(Text, default="mifare")
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, default="active")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship()


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CardRead(Base):
    """Ham okuma. Bu tabloya UPDATE/DELETE uygulanmaz."""

    __tablename__ = "card_reads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    terminal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("terminals.id"))
    card_uid: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    direction: Mapped[str] = mapped_column(Text, default="unknown")
    photo_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("photos.id"), nullable=True
    )
    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee | None] = relationship()
    terminal: Mapped[Terminal] = relationship()
    photo: Mapped[Photo | None] = relationship()


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(Time)
    end_time: Mapped[datetime] = mapped_column(Time)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, default=False)
    break_mode: Mapped[str] = mapped_column(Text, default="auto")
    break_minutes: Mapped[int] = mapped_column(Integer, default=60)
    grace_in_minutes: Mapped[int] = mapped_column(Integer, default=0)
    grace_out_minutes: Mapped[int] = mapped_column(Integer, default=0)
    rounding_minutes: Mapped[int] = mapped_column(Integer, default=0)
    min_overtime_minutes: Mapped[int] = mapped_column(Integer, default=15)
    overtime_requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shifts.id"))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekday_mask: Mapped[int] = mapped_column(Integer, default=62)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    shift: Mapped[Shift] = relationship()


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, default="public")
    site_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sites.id"), nullable=True
    )


class Leave(Base):
    __tablename__ = "leaves"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    leave_type: Mapped[str] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Adjustment(Base):
    __tablename__ = "adjustments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="pending")
    created_by: Mapped[int] = mapped_column(BigInteger)
    approved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OvertimeApproval(Base):
    __tablename__ = "overtime_approvals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    requested_minutes: Mapped[int] = mapped_column(Integer)
    approved_minutes: Mapped[int] = mapped_column(Integer, default=0)
    approved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AttendanceDay(Base):
    """Türetilmiş puantaj günü. Elle düzenlenmez, yeniden hesaplanır."""

    __tablename__ = "attendance_days"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shifts.id"), nullable=True
    )
    first_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    normal_minutes: Mapped[int] = mapped_column(Integer, default=0)
    extra_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    night_minutes: Mapped[int] = mapped_column(Integer, default=0)
    weekend_minutes: Mapped[int] = mapped_column(Integer, default=0)
    holiday_minutes: Mapped[int] = mapped_column(Integer, default=0)
    unapproved_overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="ok")
    has_adjustment: Mapped[bool] = mapped_column(Boolean, default=False)
    engine_version: Mapped[int] = mapped_column(Integer, default=1)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="manager")
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
