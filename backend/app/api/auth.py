"""Oturum açma."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import create_access_token, verify_password
from ..models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    # Kullanıcı yoksa da parola doğrulaması yapılır: var olan ve olmayan
    # hesapları yanıt süresinden ayırt etmeyi zorlaştırır.
    stored = user.password_hash if user else "$2b$12$" + "x" * 53
    password_ok = verify_password(payload.password, stored)

    if user is None or not password_ok or not user.active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "E-posta veya parola hatalı."
        )

    user.last_login_at = datetime.now(UTC)
    db.commit()

    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id), role=user.role, employee_id=user.employee_id
        ),
        role=user.role,
        full_name=user.full_name,
    )
