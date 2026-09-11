"""Logo Tiger'a yazma: Tiger Objects REST.

Logo tablolarına doğrudan yazmıyoruz. Yazma tek yoldan, Logo'nun kendi REST
servisleri üzerinden yapılır.

MEVCUT DURUM: Bordro modülü henüz kullanımda olmadığı için puantaj aktarımı
devre dışıdır. Arayüz ve kimlik doğrulama akışı şimdiden tanımlı; bordroya
geçildiğinde yalnızca push_timesheet gövdesi doldurulacak ve alan eşlemesi
yapılacaktır.

Bağımlılık: httpx (BSD)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)


class LogoWriteError(RuntimeError):
    """Logo REST çağrısı başarısız."""


@dataclass
class LogoRestConfig:
    base_url: str
    client_id: str
    client_secret: str
    firm_number: int = 1
    timeout: float = 30.0


class LogoRestClient:
    """Tiger Objects REST istemcisi.

    Token yönetimi burada kapsüllenir: çağıran taraf token'ın ne zaman
    yenilendiğini bilmek zorunda değildir.
    """

    def __init__(self, config: LogoRestConfig) -> None:
        self._config = config
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client = None

    def _get_client(self):
        import httpx

        if self._client is None:
            self._client = httpx.Client(
                base_url=self._config.base_url.rstrip("/"),
                timeout=self._config.timeout,
            )
        return self._client

    def _ensure_token(self) -> str:
        now = datetime.now()
        if (
            self._token
            and self._token_expires_at
            and now < self._token_expires_at - timedelta(minutes=2)
        ):
            return self._token

        client = self._get_client()
        response = client.post(
            "/api/v1/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "firmno": self._config.firm_number,
            },
        )
        if response.status_code >= 400:
            raise LogoWriteError(
                f"Logo token alınamadı (HTTP {response.status_code}): {response.text[:300]}"
            )

        data = response.json()
        self._token = data.get("access_token")
        if not self._token:
            raise LogoWriteError("Logo token yanıtında access_token yok.")

        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = now + timedelta(seconds=expires_in)
        return self._token

    def post(self, path: str, payload: dict) -> dict:
        client = self._get_client()
        response = client.post(
            path,
            json=payload,
            headers={"Authorization": f"Bearer {self._ensure_token()}"},
        )
        if response.status_code >= 400:
            raise LogoWriteError(
                f"Logo yazma hatası (HTTP {response.status_code}): {response.text[:300]}"
            )
        return response.json()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def push_timesheet(
    client: LogoRestClient, period_start: date, period_end: date, lines: list[dict]
) -> dict:
    """Aylık puantajı Logo'ya aktarır.

    Bordro modülü devreye alındığında tamamlanacaktır. Alan eşlemesi (hangi
    mesai türünün Logo'da hangi puantaj koduna karşılık geldiği) müşterinin
    bordro yapılandırmasına bağlı olduğu için burada varsayım yapılmamıştır -
    yanlış eşleme yanlış maaş demektir.
    """
    raise NotImplementedError(
        "Puantaj aktarımı bordro modülü devreye alındığında etkinleştirilecek. "
        "Aktarım öncesi mesai türü -> Logo puantaj kodu eşlemesi tanımlanmalıdır."
    )
