"""Password hashing (Argon2) and JWT access tokens, plus the auth dependencies."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_db
from backend.models import User

_hasher = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def create_access_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "role": user.role, "iat": now,
               "exp": now + timedelta(minutes=s.access_token_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


FILE_TOKEN_SECONDS = 10 * 60


def create_file_token(document_id: uuid.UUID) -> str:
    """Signed, short-lived permission to download ONE document's PDF (no user identity)."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"doc": str(document_id), "purpose": "file", "iat": now,
               "exp": now + timedelta(seconds=FILE_TOKEN_SECONDS)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def file_token_valid(token: str, document_id: uuid.UUID) -> bool:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return False
    return payload.get("purpose") == "file" and payload.get("doc") == str(document_id)


_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                              detail="Not authenticated",
                              headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)],
                     db: Annotated[Session, Depends(get_db)]) -> User:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
