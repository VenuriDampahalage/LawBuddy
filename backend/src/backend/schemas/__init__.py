"""Request / response models for the API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- auth ----------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None
    avatar_url: str | None = None
    role: str
    has_password: bool = True
    google_linked: bool = False
    created_at: datetime


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)


class PasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    confirm_email: str = Field(max_length=255)


class GoogleSignInIn(BaseModel):
    credential: str = Field(min_length=20, max_length=5000)   # Google ID token (JWT)


class AuthConfigOut(BaseModel):
    google_client_id: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- documents -----------------------------------------------------------------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    status: str
    error: str | None
    page_count: int | None
    created_at: datetime
    updated_at: datetime
    acts: int
    chunks: int


class ActOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    kind: str
    act_number: int | None
    year: int | None
    page_start: int | None
    page_end: int | None
    sections: int


class DocumentDetailOut(DocumentOut):
    act_list: list[ActOut]


class UploadOut(BaseModel):
    document: DocumentOut
    created: bool          # False: this exact PDF was already uploaded


# ---- chat ----------------------------------------------------------------------------
class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    status: str = "complete"
    feedback: int | None = None
    created_at: datetime


class FeedbackIn(BaseModel):
    value: Literal[1, -1, 0]          # 0 clears the rating


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
