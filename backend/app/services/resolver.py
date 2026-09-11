"""Kart UID'sinden personel çözümleme ve yön belirleme."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import Card, CardRead, Employee, Terminal


def resolve_employee(db: Session, card_uid: str, read_at: datetime) -> Employee | None:
    """Okuma ANINDA bu kartın kime ait olduğunu bulur.

    Zaman kritiktir: kart devredilmişse geçmiş okumalar eski sahibine ait
    kalmalıdır. Bu yüzden "şu an kimde" değil, "o an kimdeydi" sorulur.
    """
    stmt = (
        select(Employee)
        .join(Card, Card.employee_id == Employee.id)
        .where(
            Card.uid == card_uid,
            Card.status == "active",
            Card.valid_from <= read_at,
            or_(Card.valid_to.is_(None), Card.valid_to >= read_at),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def resolve_direction(
    db: Session, terminal: Terminal, employee: Employee | None, read_at: datetime
) -> str:
    """Bu okumanın giriş mi çıkış mı olduğunu belirler."""
    if terminal.direction_mode in ("in", "out"):
        return terminal.direction_mode

    if employee is None:
        return "unknown"

    # toggle: kişinin bu lokasyondaki son hareketinin tersi.
    # Lokasyon bazlı bakıyoruz; farklı şubelerdeki hareketler birbirinin
    # yönünü bozmamalı.
    last_direction = db.execute(
        select(CardRead.direction)
        .join(Terminal, Terminal.id == CardRead.terminal_id)
        .where(
            and_(
                CardRead.employee_id == employee.id,
                CardRead.read_at < read_at,
                CardRead.direction.in_(("in", "out")),
                Terminal.site_id == terminal.site_id,
            )
        )
        .order_by(CardRead.read_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return "out" if last_direction == "in" else "in"
