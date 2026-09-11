"""Logo Tiger'dan personel/departman okuma (MSSQL, SALT OKUNUR).

İKİ KURAL:

1. Logo veritabanına ASLA yazmıyoruz. Yazma yolu yalnızca Tiger Objects
   REST'tir (writer.py). Logo tablolarına doğrudan INSERT/UPDATE yapmak Logo
   desteğini geçersiz kılar ve veri bütünlüğünü bozar.

2. Sorgu KODA GÖMÜLMEZ, yapılandırmadan gelir. Logo tablo isimleri firma
   numarası ve dönem içerir (LG_001_..., LG_002_...), sürümler arasında
   değişir ve her kurulumda farklı alanlar kullanılır. Sorguyu dışarı almak,
   Logo sürümü yükseltildiğinde kod değişmeden uyum sağlamayı mümkün kılar.

Bağımlılık: pyodbc (MIT) + FreeTDS ya da Microsoft ODBC Driver
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Department, Employee

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LogoEmployeeRow:
    """Logo'dan okunan ham personel satırı."""

    external_ref: str
    employee_no: str
    first_name: str
    last_name: str
    department_code: str | None = None
    department_name: str | None = None
    title: str | None = None
    active: bool = True


class LogoReader:
    """Logo MSSQL'den salt okunur veri çeker."""

    def __init__(self, dsn: str, employee_query: str) -> None:
        self._dsn = dsn
        self._employee_query = employee_query

    def fetch_employees(self) -> list[LogoEmployeeRow]:
        import pyodbc

        rows: list[LogoEmployeeRow] = []
        with pyodbc.connect(self._dsn, readonly=True) as connection:
            cursor = connection.cursor()
            cursor.execute(self._employee_query)

            columns = [column[0].lower() for column in cursor.description]
            for record in cursor.fetchall():
                data = dict(zip(columns, record, strict=True))
                rows.append(
                    LogoEmployeeRow(
                        external_ref=str(data["external_ref"]),
                        employee_no=str(data["employee_no"]).strip(),
                        first_name=str(data.get("first_name") or "").strip(),
                        last_name=str(data.get("last_name") or "").strip(),
                        department_code=_clean(data.get("department_code")),
                        department_name=_clean(data.get("department_name")),
                        title=_clean(data.get("title")),
                        active=bool(data.get("active", True)),
                    )
                )

        log.info("Logo'dan %d personel satırı okundu.", len(rows))
        return rows


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def sync_employees(db: Session, rows: list[LogoEmployeeRow]) -> dict[str, int]:
    """Logo'dan okunan satırları PDKS veritabanına işler.

    Eşleştirme external_ref üzerinden yapılır; personel numarası değişse bile
    kayıt kaybolmaz. Logo'da olmayan personel SİLİNMEZ, pasife çekilir -
    geçmiş puantaj kayıtlarının bağlı olduğu satırı silmek denetim izini yok
    eder.
    """
    stats = {"created": 0, "updated": 0, "deactivated": 0}
    now = datetime.now(UTC)

    department_cache = _sync_departments(db, rows, now)
    seen_refs: set[str] = set()

    for row in rows:
        seen_refs.add(row.external_ref)

        employee = db.execute(
            select(Employee).where(Employee.external_ref == row.external_ref)
        ).scalar_one_or_none()

        department_id = (
            department_cache.get(row.department_code) if row.department_code else None
        )

        if employee is None:
            db.add(
                Employee(
                    employee_no=row.employee_no,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    department_id=department_id,
                    title=row.title,
                    external_ref=row.external_ref,
                    source="logo",
                    synced_at=now,
                    active=row.active,
                    created_at=now,
                    updated_at=now,
                )
            )
            stats["created"] += 1
        else:
            employee.employee_no = row.employee_no
            employee.first_name = row.first_name
            employee.last_name = row.last_name
            employee.department_id = department_id
            employee.title = row.title
            employee.active = row.active
            employee.synced_at = now
            employee.updated_at = now
            stats["updated"] += 1

    # Logo'da artık görünmeyen personeli pasife çek
    stale = db.execute(
        select(Employee).where(
            Employee.source == "logo",
            Employee.active.is_(True),
            Employee.external_ref.isnot(None),
        )
    ).scalars()

    for employee in stale:
        if employee.external_ref not in seen_refs:
            employee.active = False
            employee.updated_at = now
            stats["deactivated"] += 1

    db.commit()
    log.info("Personel senkronu tamamlandı: %s", stats)
    return stats


def _sync_departments(
    db: Session, rows: list[LogoEmployeeRow], now: datetime
) -> dict[str, int]:
    """Satırlarda geçen departmanları oluşturur, kod -> id eşlemesi döner."""
    cache: dict[str, int] = {}

    for row in rows:
        if not row.department_code or row.department_code in cache:
            continue

        department = db.execute(
            select(Department).where(Department.code == row.department_code)
        ).scalar_one_or_none()

        if department is None:
            department = Department(
                code=row.department_code,
                name=row.department_name or row.department_code,
                external_ref=row.department_code,
                active=True,
                created_at=now,
            )
            db.add(department)
            db.flush()

        cache[row.department_code] = department.id

    return cache
