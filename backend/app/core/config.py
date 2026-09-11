"""Uygulama yapılandırması (ortam değişkenleri)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
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
    # RFC 7518 HS256 için en az 32 bayt anahtar önerir; daha kısasını
    # kabul etmiyoruz.
    jwt_secret: str = Field(default="GELISTIRME-ORTAMI-ICIN-GECICI-ANAHTAR-DEGISTIRIN")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    # --- QR kanalı ---
    # Terminal QR anahtarları bu ana anahtardan TÜRETİLİR; veritabanında
    # saklanmaz. Değiştirilirse tüm terminallerin yeniden kurulumu gerekir.
    qr_master_secret: str = Field(
        default="GELISTIRME-ORTAMI-ICIN-GECICI-QR-ANAHTARI-DEGISTIRIN"
    )
    # Okutmanın yalnızca kayıtlı cihazdan yapılabilmesi
    qr_require_registered_device: bool = True

    # --- Fotoğraf deposu ve KVKK saklama süresi ---
    photo_storage_path: str = "/var/lib/pdks/photos"
    # KVKK: fotoğraflar bu süre sonunda otomatik ve GERÇEKTEN silinir.
    photo_retention_days: int = 60

    timezone: str = "Europe/Istanbul"


    @field_validator("jwt_secret", "qr_master_secret")
    @classmethod
    def _secret_uzunlugu(cls, value: str) -> str:
        """Kısa anahtar, olmayan anahtardan daha tehlikelidir: güvende
        olduğunuzu sanırsınız."""
        if len(value.encode()) < 32:
            raise ValueError(
                "Gizli anahtar en az 32 bayt olmalıdır "
                "(openssl rand -base64 48 ile üretebilirsiniz)."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
