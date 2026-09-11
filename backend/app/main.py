"""FastAPI uygulaması."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .api import auth, ingest, punch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = FastAPI(
    title="PDKS API",
    description="Personel Devam Kontrol Sistemi",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(punch.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
