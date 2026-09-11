"""Coğrafi çit (geofence) doğrulaması.

Konum doğrulaması DESTEKLEYİCİ bir kanıttır, asıl güvence değildir: mobil
cihazlarda sahte konum üretmek kolaydır. Asıl güvence dönen QR koddur
(qr_token.py). Buradaki kontrol, "QR kodu bir şekilde ele geçirdim ama
şehrin öbür ucundayım" durumunu yakalar.

Bu yüzden çit dışı okutma varsayılan olarak REDDEDİLMEZ, İŞARETLENİR:
GPS binaların içinde sapabilir, kapalı alanda doğruluk düşer. Kaydı düşürmek
yerine amir onayına düşürmek hem daha doğru hem de sorunu araştırılabilir
bırakır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000

# Bu değerden kötü konum doğruluğu bildiren okutmalar 'unknown' sayılır:
# 500 metre hatalı bir konumla çit kontrolü yapmak anlamsızdır.
MAX_USABLE_ACCURACY_M = 200


class GeofenceStatus:
    INSIDE = "inside"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"


@dataclass(frozen=True)
class GeofenceResult:
    status: str
    distance_m: int | None = None
    reason: str | None = None

    @property
    def should_reject(self) -> bool:
        return self.status == GeofenceStatus.OUTSIDE


def haversine_distance_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """İki koordinat arasındaki yüzey mesafesini metre cinsinden verir."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def check_geofence(
    *,
    center_lat: float | None,
    center_lon: float | None,
    radius_m: int | None,
    reported_lat: float | None,
    reported_lon: float | None,
    accuracy_m: int | None = None,
) -> GeofenceResult:
    """Bildirilen konumun çit içinde olup olmadığını belirler."""
    if center_lat is None or center_lon is None or not radius_m:
        return GeofenceResult(
            GeofenceStatus.NOT_REQUIRED, reason="Lokasyon için çit tanımlanmamış."
        )

    if reported_lat is None or reported_lon is None:
        return GeofenceResult(
            GeofenceStatus.UNKNOWN, reason="Cihaz konum bildirmedi."
        )

    if accuracy_m is not None and accuracy_m > MAX_USABLE_ACCURACY_M:
        # Doğruluğu bu kadar kötü bir konumla karar vermek, yanlış karar
        # vermekten daha kötüdür: yanlış olduğunu bilmeden karar veririz.
        return GeofenceResult(
            GeofenceStatus.UNKNOWN,
            reason=f"Konum doğruluğu yetersiz ({accuracy_m} m).",
        )

    distance = haversine_distance_m(center_lat, center_lon, reported_lat, reported_lon)

    # Cihazın bildirdiği hata payını çalışanın lehine sayıyoruz: sınırda
    # duran birini hatalı biçimde dışarıda göstermemek için.
    effective_distance = distance - (accuracy_m or 0)

    if effective_distance <= radius_m:
        return GeofenceResult(GeofenceStatus.INSIDE, distance_m=int(distance))

    return GeofenceResult(
        GeofenceStatus.OUTSIDE,
        distance_m=int(distance),
        reason=f"Çit merkezine {int(distance)} m uzaklıkta (sınır {radius_m} m).",
    )
