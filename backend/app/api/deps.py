"""Ortak bağımlılıklar: terminal ve kullanıcı kimlik doğrulama."""

from __future__ import annotations

import hashlib
import hmac

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import decode_access_token
from ..models import Employee, Terminal, User


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


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Erişim jetonundan oturum sahibini çözer."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum açılmamış.")

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Oturum geçersiz veya süresi dolmuş."
        ) from exc

    user = db.execute(
        select(User).where(User.id == int(claims["sub"]))
    ).scalar_one_or_none()

    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı bulunamadı.")

    return user


def get_current_employee(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee:
    """Oturum sahibinin personel kaydını döner.

    QR ile okutma bir personel adına yapılır; personel kaydı olmayan bir
    yönetici hesabı kendi adına okutma yapamaz.
    """
    if user.employee_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Bu hesap bir personel kaydına bağlı değil.",
        )

    employee = db.execute(
        select(Employee).where(Employee.id == user.employee_id)
    ).scalar_one_or_none()

    if employee is None or not employee.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Personel kaydı aktif değil.")

    return employee
