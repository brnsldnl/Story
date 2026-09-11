"""Ortak bağımlılıklar: terminal ve kullanıcı kimlik doğrulama."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import Terminal


def hash_terminal_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def authenticate_terminal(
    x_terminal_code: str = Header(...),
    x_terminal_key: str = Header(...),
    db: Session = Depends(get_db),
) -> Terminal:
    """Terminal API anahtarını doğrular.

    Anahtar veritabanında hash'li tutulur ve karşılaştırma sabit zamanlı
    yapılır; sunucu veritabanı sızsa bile anahtarlar kullanılamaz olmalı.
    """
    terminal = db.execute(
        select(Terminal).where(Terminal.code == x_terminal_code)
    ).scalar_one_or_none()

    expected = hash_terminal_key(x_terminal_key)

    # Terminal bulunamadıysa da aynı işi yaparak zamanlama farkı bırakmıyoruz.
    stored = terminal.api_key_hash if terminal else "0" * 64
    valid = hmac.compare_digest(stored, expected)

    if terminal is None or not valid or not terminal.active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Terminal kimlik doğrulaması başarısız."
        )

    return terminal
