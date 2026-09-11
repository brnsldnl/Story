"""Uygulama yapılandırması (ortam değişkenleri)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Kendi veritabanımız (PostgreSQL) ---
    database_url: str = "postgresql+psycopg://pdks:pdks@localhost:5432/pdks"

    # --- Logo Tiger (MSSQL, SALT OKUNUR) ---
    # Logo tablolarına asla yazmıyoruz; yazma Tiger Objects REST üzerinden.
    logo_mssql_dsn: str | None = None
    logo_sync_enabled: bool = False

    # --- Tiger Objects REST (yazma yolu) ---
    logo_rest_base_url: str | None = None
    logo_rest_client_id: str | None = None
    logo_rest_client_secret: str | None = None
    logo_rest_firm_number: int = 1

    # --- Güvenlik ---
    jwt_secret: str = Field(default="degistirin-bu-degeri")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    # --- Fotoğraf deposu ve KVKK saklama süresi ---
    photo_storage_path: str = "/var/lib/pdks/photos"
    # KVKK: fotoğraflar bu süre sonunda otomatik ve GERÇEKTEN silinir.
    photo_retention_days: int = 60

    timezone: str = "Europe/Istanbul"


@lru_cache
def get_settings() -> Settings:
    return Settings()
