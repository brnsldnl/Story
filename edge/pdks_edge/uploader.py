"""Kuyruktaki okumaları sunucuya gönderir.

Bağımlılık: httpx (BSD)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .queue import OfflineQueue, PendingRead

log = logging.getLogger(__name__)


class Uploader:
    def __init__(
        self,
        base_url: str,
        terminal_code: str,
        api_key: str,
        timeout: float = 10.0,
        verify: bool | str = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._terminal_code = terminal_code
        self._api_key = api_key
        self._timeout = timeout
        self._verify = verify
        self._client = None

    def _get_client(self):
        import httpx

        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                verify=self._verify,
                headers={
                    "X-Terminal-Code": self._terminal_code,
                    "X-Terminal-Key": self._api_key,
                },
            )
        return self._client

    def flush(self, queue: OfflineQueue, batch_size: int = 20) -> int:
        """Gönderilebilecek kayıtları gönderir, başarılı gönderim sayısını döner."""
        sent = 0
        for item in queue.due(limit=batch_size):
            try:
                self._send(item)
            # Geniş yakalama KASITLIDIR: gönderimde ne olursa olsun kayıt
            # kuyrukta kalmalı. Beklenmedik bir hatanın kaydı düşürmesi,
            # bir çalışanın puantajının yanlış hesaplanması demektir.
            except Exception as exc:  # noqa: BLE001
                queue.mark_failed(item, str(exc))
                # Sıralamayı koru: bir kayıt gönderilemiyorsa sonrakileri de
                # zorlamıyoruz, muhtemelen ağ tamamen kopuk.
                break
            else:
                queue.mark_sent(item)
                sent += 1
        return sent

    def _send(self, item: PendingRead) -> None:
        import httpx

        client = self._get_client()
        payload = {
            "client_event_id": item.client_event_id,
            "card_uid": item.card_uid,
            "read_at": item.read_at,
            "technology": item.technology,
            "raw": item.raw,
        }

        files = {"payload": (None, json.dumps(payload), "application/json")}
        photo_path = Path(item.photo_path) if item.photo_path else None
        if photo_path and photo_path.exists():
            files["photo"] = (photo_path.name, photo_path.read_bytes(), "image/jpeg")

        response = client.post(f"{self._base_url}/api/v1/ingest/card-read", files=files)

        # 409: sunucu bu olayı zaten kaydetmiş. Bu bir hata değil - offline
        # kuyruğun yeniden gönderiminde beklenen durumdur, başarı sayılır.
        if response.status_code == 409:
            log.info("Olay zaten kayıtlı, atlanıyor: %s", item.client_event_id)
            return

        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code}: {response.text[:200]}",
                request=response.request,
                response=response,
            )

    def heartbeat(self, queue_depth: int, agent_version: str) -> None:
        """Terminalin hayatta olduğunu bildirir.

        Sessiz veri kaybına karşı tek savunma budur: bir terminal kart
        okumasa bile heartbeat göndermeli ki panel 'bu kapı 3 saattir sessiz'
        diyebilsin.
        """
        import httpx

        try:
            client = self._get_client()
            client.post(
                f"{self._base_url}/api/v1/ingest/heartbeat",
                json={"queue_depth": queue_depth, "agent_version": agent_version},
            )
        except httpx.HTTPError as exc:
            log.debug("Heartbeat gönderilemedi: %s", exc)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
