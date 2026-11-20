"""Admin: manage user accounts and review rated answers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from backend.core.security import DB, AdminUser
from backend.models import Conversation, Message, User

router = APIRouter(prefix="/admin", tags=["admin: users & feedback"])


# ---- users ---------------------------------------------------------------------------

class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    has_password: bool
    google_linked: bool
    created_at: datetime
    conversations: int = 0
    last_active: datetime | None = None


class UserUpdateIn(BaseModel):
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


def _active_admins(db) -> int:
    return db.scalar(select(func.count()).select_from(User)
                     .where(User.role == "admin", User.is_active)) or 0


def _with_activity(db, users: list[User]) -> list[AdminUserOut]:
    """Attach conversation counts and last activity in two grouped queries."""
    ids = [u.id for u in users]
    if not ids:
        return []
    convs = dict(db.execute(
        select(Conversation.user_id, func.count()).where(Conversation.user_id.in_(ids))
        .group_by(Conversation.user_id)).all())
    last = dict(db.execute(
        select(Conversation.user_id, func.max(Message.created_at))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id.in_(ids)).group_by(Conversation.user_id)).all())
    out = []
    for u in users:
        item = AdminUserOut.model_validate(u)
        item.conversations, item.last_active = convs.get(u.id, 0), last.get(u.id)
        out.append(item)
    return out


@router.get("/users", response_model=list[AdminUserOut])
def list_users(_: AdminUser, db: DB,
               q: str | None = Query(default=None, max_length=200),
               filter: Literal["all", "admins", "disabled"] = "all") -> list[AdminUserOut]:
    stmt = select(User).order_by(User.created_at.desc()).limit(500)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like),
                              func.lower(func.coalesce(User.full_name, "")).like(like)))
    if filter == "admins":
        stmt = stmt.where(User.role == "admin")
    elif filter == "disabled":
        stmt = stmt.where(User.is_active.is_(False))
    return _with_activity(db, list(db.scalars(stmt)))


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: uuid.UUID, body: UserUpdateIn, me: AdminUser, db: DB) -> AdminUserOut:
    """Change a user's role or enable/disable them.

    Guard rails: admins can't change their own role or disable themselves (no accidental
    lock-out), and the last active admin can never be demoted or disabled."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == me.id and (body.role not in (None, user.role) or body.is_active is False):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "You can't change your own role or disable your own account.")
    removing_admin = user.role == "admin" and user.is_active and (
        body.role == "user" or body.is_active is False)
    if removing_admin and _active_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This is the last active admin. Make someone else an admin first.")
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    return _with_activity(db, [user])[0]


# ---- feedback ------------------------------------------------------------------------

class FeedbackItemOut(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    rating: int
    question: str | None
    answer: str
    citations: list[dict[str, Any]]
    answered_at: datetime
    user_email: str


class FeedbackSummaryOut(BaseModel):
    helpful: int
    not_helpful: int
    items: list[FeedbackItemOut]


@router.get("/feedback", response_model=FeedbackSummaryOut)
def list_feedback(_: AdminUser, db: DB,
                  rating: Literal["not_helpful", "helpful", "all"] = "not_helpful",
                  limit: int = Query(default=100, ge=1, le=500)) -> FeedbackSummaryOut:
    """Rated answers with the question that was asked, newest first."""
    counts = dict(db.execute(select(Message.feedback, func.count())
                             .where(Message.feedback.is_not(None))
                             .group_by(Message.feedback)).all())
    # The question is the latest user message before the answer in the same conversation;
    # fetched as a correlated subquery so the whole list is ONE round trip to the database.
    asked = aliased(Message)
    question_sq = (select(asked.content)
                   .where(asked.conversation_id == Message.conversation_id,
                          asked.role == "user", asked.created_at <= Message.created_at)
                   .order_by(asked.created_at.desc()).limit(1)
                   .correlate(Message).scalar_subquery())
    stmt = (select(Message, User.email, question_sq)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(Message.role == "assistant", Message.feedback.is_not(None))
            .order_by(Message.created_at.desc()).limit(limit))
    if rating == "not_helpful":
        stmt = stmt.where(Message.feedback == -1)
    elif rating == "helpful":
        stmt = stmt.where(Message.feedback == 1)

    items = []
    for msg, email, question in db.execute(stmt).all():
        items.append(FeedbackItemOut(
            message_id=msg.id, conversation_id=msg.conversation_id, rating=msg.feedback,
            question=question, answer=msg.content, citations=msg.citations or [],
            answered_at=msg.created_at, user_email=email))
    return FeedbackSummaryOut(helpful=counts.get(1, 0), not_helpful=counts.get(-1, 0),
                              items=items)
