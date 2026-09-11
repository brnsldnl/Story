"""Puantaj hesap motoru.

Bu modül bilinçli olarak veritabanından BAĞIMSIZDIR: girdi olarak sade veri
yapıları alır, çıktı olarak sade bir sonuç döner. Böylece iş kuralları
veritabanı kurmadan test edilebilir ve mevzuat değiştiğinde yalnızca burası
değişir.

Hesap sırası:
    1. Gün tipini belirle (tatil / hafta sonu / izin / vardiyasız)
    2. Ham okumaları giriş-çıkış çiftlerine eşle
    3. Mola kesintisini uygula
    4. Geç kalma / erken çıkış hesapla
    5. Süreyi normal / fazla / gece / tatil kırılımına ayır
    6. Mesai onayını uygula

EN KRİTİK NOKTA: Gece vardiyası gün sınırını aşar. 22:00-06:00 vardiyasında
çalışan bir kişinin 2 Mart 06:00'daki çıkışı, 1 Mart'ın puantajına aittir.
Bu yüzden "iş günü" takvim gününden farklı bir kavramdır ve vardiyanın
başlangıç gününe göre belirlenir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

log = logging.getLogger(__name__)

ENGINE_VERSION = 1

# İş Kanunu m.69: gece dönemi 20:00 - 06:00
NIGHT_START = time(20, 0)
NIGHT_END = time(6, 0)


class DayStatus:
    OK = "ok"
    MISSING_OUT = "missing_out"
    MISSING_IN = "missing_in"
    ABSENT = "absent"
    LEAVE = "leave"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"
    NOT_SCHEDULED = "not_scheduled"


@dataclass(frozen=True)
class Punch:
    """Tek bir giriş veya çıkış hareketi (ham okuma veya onaylı düzeltme)."""

    at: datetime
    direction: str  # 'in' | 'out'
    source: str = "card"  # 'card' | 'adjustment'


@dataclass(frozen=True)
class ShiftRule:
    """Vardiya kuralları. Veritabanındaki shifts tablosunun yansıması."""

    code: str
    start_time: time
    end_time: time
    crosses_midnight: bool = False
    break_mode: str = "auto"
    break_minutes: int = 60
    grace_in_minutes: int = 0
    grace_out_minutes: int = 0
    rounding_minutes: int = 0
    min_overtime_minutes: int = 15
    overtime_requires_approval: bool = True

    @property
    def planned_minutes(self) -> int:
        """Vardiyanın brüt süresi (mola dahil)."""
        start = _minutes_of_day(self.start_time)
        end = _minutes_of_day(self.end_time)
        if self.crosses_midnight or end <= start:
            end += 24 * 60
        return end - start


@dataclass
class DayResult:
    """Bir çalışanın bir iş gününe ait hesaplanmış puantajı."""

    work_date: date
    status: str = DayStatus.OK

    first_in_at: datetime | None = None
    last_out_at: datetime | None = None

    worked_minutes: int = 0
    break_minutes: int = 0
    late_minutes: int = 0
    early_leave_minutes: int = 0

    normal_minutes: int = 0
    extra_minutes: int = 0
    overtime_minutes: int = 0
    night_minutes: int = 0
    weekend_minutes: int = 0
    holiday_minutes: int = 0
    unapproved_overtime_minutes: int = 0

    has_adjustment: bool = False
    engine_version: int = ENGINE_VERSION
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DayContext:
    """Hesap için gereken tüm girdiler."""

    work_date: date
    punches: list[Punch]
    shift: ShiftRule | None = None
    is_holiday: bool = False
    is_half_holiday: bool = False
    is_weekend: bool = False
    is_on_leave: bool = False
    # Amirin onayladığı mesai dakikası (None = onay kaydı yok)
    approved_overtime_minutes: int | None = None


def _minutes_of_day(value: time) -> int:
    return value.hour * 60 + value.minute


def _round_to(minutes: int, step: int) -> int:
    """Süreyi en yakın adıma yuvarlar. step=0 ise yuvarlama yapılmaz."""
    if step <= 0:
        return minutes
    return int(round(minutes / step) * step)


def pair_punches(punches: list[Punch]) -> tuple[list[tuple[Punch, Punch]], list[str]]:
    """Hareketleri giriş-çıkış çiftlerine eşler.

    Gerçek hayatta hareketler hiçbir zaman tertemiz gelmez: insanlar çıkış
    okutmayı unutur, kartı iki kez değdirir, mola için çıkıp girer. Bu
    fonksiyon eldeki veriden yapabileceğinin en iyisini yapar ve
    yapamadıklarını uyarı olarak bildirir - sessizce tahmin yürütmez.
    """
    ordered = sorted(punches, key=lambda p: p.at)
    pairs: list[tuple[Punch, Punch]] = []
    warnings: list[str] = []
    open_in: Punch | None = None

    for punch in ordered:
        if punch.direction == "in":
            if open_in is not None:
                # Arka arkaya iki giriş: aradaki çıkış kaçmış.
                warnings.append(
                    f"{open_in.at:%H:%M} girişinin çıkışı yok, bu giriş yok sayıldı."
                )
            open_in = punch
        elif punch.direction == "out":
            if open_in is None:
                warnings.append(
                    f"{punch.at:%H:%M} çıkışının girişi yok, bu çıkış yok sayıldı."
                )
                continue
            pairs.append((open_in, punch))
            open_in = None

    if open_in is not None:
        warnings.append(f"{open_in.at:%H:%M} girişi açık kaldı, çıkış okutulmamış.")

    return pairs, warnings


def night_minutes_in(start: datetime, end: datetime) -> int:
    """Verilen aralığın gece dönemine (20:00-06:00) düşen dakika sayısı.

    Aralık birden fazla günü kapsayabileceği için dakika dakika değil, gün
    gün ilerleyerek hesaplanır.
    """
    if end <= start:
        return 0

    total = 0
    cursor = start

    while cursor < end:
        day_end = datetime.combine(
            cursor.date() + timedelta(days=1), time(0, 0), tzinfo=cursor.tzinfo
        )
        segment_end = min(end, day_end)

        # Bu güne ait iki gece bloğu: 00:00-06:00 ve 20:00-24:00
        for block_start_t, block_end_t in ((time(0, 0), NIGHT_END), (NIGHT_START, None)):
            block_start = datetime.combine(
                cursor.date(), block_start_t, tzinfo=cursor.tzinfo
            )
            block_end = (
                day_end
                if block_end_t is None
                else datetime.combine(cursor.date(), block_end_t, tzinfo=cursor.tzinfo)
            )

            overlap_start = max(cursor, block_start)
            overlap_end = min(segment_end, block_end)
            if overlap_end > overlap_start:
                total += int((overlap_end - overlap_start).total_seconds() // 60)

        cursor = segment_end

    return total


def compute_day(context: DayContext) -> DayResult:
    """Bir iş gününün puantajını hesaplar."""
    result = DayResult(work_date=context.work_date)
    result.has_adjustment = any(p.source == "adjustment" for p in context.punches)

    # --- 1. Gün tipi -----------------------------------------------------
    if context.is_on_leave and not context.punches:
        result.status = DayStatus.LEAVE
        return result

    if context.is_holiday and not context.punches:
        result.status = DayStatus.HOLIDAY
        return result

    if context.is_weekend and not context.punches:
        result.status = DayStatus.WEEKEND
        return result

    if context.shift is None and not context.punches:
        result.status = DayStatus.NOT_SCHEDULED
        return result

    if not context.punches:
        result.status = DayStatus.ABSENT
        return result

    # --- 2. Giriş-çıkış eşleme -------------------------------------------
    pairs, warnings = pair_punches(context.punches)
    result.warnings.extend(warnings)

    ordered = sorted(context.punches, key=lambda p: p.at)
    result.first_in_at = next((p.at for p in ordered if p.direction == "in"), None)
    result.last_out_at = next(
        (p.at for p in reversed(ordered) if p.direction == "out"), None
    )

    if not pairs:
        # Hareket var ama eşleşen çift yok: tek başına giriş veya tek çıkış.
        result.status = (
            DayStatus.MISSING_OUT if result.first_in_at else DayStatus.MISSING_IN
        )
        return result

    if result.first_in_at is None:
        result.status = DayStatus.MISSING_IN
    elif any("açık kaldı" in w for w in warnings):
        result.status = DayStatus.MISSING_OUT

    # --- 3. Çalışılan süre ve mola ---------------------------------------
    gross_minutes = sum(
        int((out.at - inn.at).total_seconds() // 60) for inn, out in pairs
    )

    shift = context.shift
    auto_break = shift is not None and shift.break_mode == "auto"

    if auto_break:
        # Otomatik kesinti: vardiyada tanımlı mola süresi düşülür.
        result.break_minutes = min(shift.break_minutes, gross_minutes)
    elif shift is not None and shift.break_mode == "card" and len(pairs) > 1:
        # Mola kartla okutuluyor: çiftler arasındaki boşluklar zaten
        # çalışılmayan süre olarak dışarıda kaldı, burada yalnızca raporlamak
        # için topluyoruz.
        result.break_minutes = sum(
            int((pairs[i + 1][0].at - pairs[i][1].at).total_seconds() // 60)
            for i in range(len(pairs) - 1)
        )

    # Kartla mola modunda boşluklar zaten çiftlerin dışında kaldığı için
    # ikinci kez düşmüyoruz; yalnızca otomatik kesinti brütten indirilir.
    worked = gross_minutes - (result.break_minutes if auto_break else 0)
    worked = max(0, worked)

    if shift is not None:
        worked = _round_to(worked, shift.rounding_minutes)
    result.worked_minutes = worked

    # --- 4. Geç kalma / erken çıkış --------------------------------------
    if shift is not None and result.first_in_at is not None:
        planned_start = _expected_start(context.work_date, shift, result.first_in_at)
        late = int((result.first_in_at - planned_start).total_seconds() // 60)
        result.late_minutes = max(0, late - shift.grace_in_minutes)

    if shift is not None and result.last_out_at is not None:
        planned_end = _expected_end(context.work_date, shift, result.last_out_at)
        early = int((planned_end - result.last_out_at).total_seconds() // 60)
        result.early_leave_minutes = max(0, early - shift.grace_out_minutes)

    # --- 5. Gece / tatil / hafta sonu kırılımı ---------------------------
    result.night_minutes = sum(night_minutes_in(inn.at, out.at) for inn, out in pairs)

    if context.is_holiday:
        result.holiday_minutes = worked
    elif context.is_weekend:
        result.weekend_minutes = worked

    # --- 6. Normal / fazla ayrımı ve mesai onayı -------------------------
    if shift is None:
        planned = 0
    else:
        planned = shift.planned_minutes
        if shift.break_mode == "auto":
            planned -= shift.break_minutes

    if planned <= 0:
        # Vardiyasız gün (tatilde çağrılmış vb.): tamamı fazla çalışmadır.
        candidate_overtime = worked
        result.normal_minutes = 0
    else:
        result.normal_minutes = min(worked, planned)
        candidate_overtime = max(0, worked - planned)

    if shift is not None and candidate_overtime < shift.min_overtime_minutes:
        # Eşik altı fazla kalma mesai sayılmaz (5 dakika geç çıkan herkese
        # mesai yazmak maliyeti anlamsız şişirir).
        candidate_overtime = 0

    if shift is not None and shift.overtime_requires_approval:
        approved = context.approved_overtime_minutes
        if approved is None:
            # Onay kaydı yok: süre raporlanır ama ücretlendirilmez.
            result.unapproved_overtime_minutes = candidate_overtime
            result.overtime_minutes = 0
        else:
            result.overtime_minutes = min(candidate_overtime, approved)
            result.unapproved_overtime_minutes = max(
                0, candidate_overtime - result.overtime_minutes
            )
    else:
        result.overtime_minutes = candidate_overtime

    return result


def _expected_start(work_date: date, shift: ShiftRule, reference: datetime) -> datetime:
    """Vardiyanın planlanan başlangıç anı (iş gününe göre)."""
    return datetime.combine(work_date, shift.start_time, tzinfo=reference.tzinfo)


def _expected_end(work_date: date, shift: ShiftRule, reference: datetime) -> datetime:
    """Vardiyanın planlanan bitiş anı.

    Gece vardiyasında bitiş ERTESİ GÜNDEDİR; bu ayrımı kaçırmak gece
    çalışanlarına her gün yanlışlıkla 8 saat erken çıkış yazdırır.
    """
    end_date = work_date + timedelta(days=1) if shift.crosses_midnight else work_date
    return datetime.combine(end_date, shift.end_time, tzinfo=reference.tzinfo)
