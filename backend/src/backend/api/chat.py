"""Conversations and the streaming chat endpoint.

POST /conversations/{id}/messages returns Server-Sent Events:
    event: status   data: {"type": "status", "stage": "searching"}
    event: token    data: {"type": "token", "text": "..."}
    event: done     data: {"type": "done", "answer": "...", "citations": [...], "message_id": ...}
    event: error    data: {"type": "error", "message": "..."}
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from backend.core.db import new_session
from backend.core.security import DB, CurrentUser
from backend.models import Conversation, Message, User
from backend.schemas import ConversationOut, FeedbackIn, MessageIn, MessageOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["chat"])


def _owned(db, conversation_id: uuid.UUID, user: User) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:      # 404 either way: don't leak existence
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create(user: CurrentUser, db: DB) -> Conversation:
    conv = Conversation(user_id=user.id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("", response_model=list[ConversationOut])
def list_conversations(user: CurrentUser, db: DB) -> list[Conversation]:
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                           .order_by(Conversation.updated_at.desc()).limit(200)))


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def messages(conversation_id: uuid.UUID, user: CurrentUser, db: DB) -> list[Message]:
    return _owned(db, conversation_id, user).messages


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(conversation_id: uuid.UUID, request: Request, user: CurrentUser, db: DB) -> None:
    conv = _owned(db, conversation_id, user)
    db.delete(conv)
    db.commit()
    await run_in_threadpool(request.app.state.agent.delete_thread, str(conversation_id))


@router.post("/{conversation_id}/messages")
async def send(conversation_id: uuid.UUID, body: MessageIn, request: Request,
               user: CurrentUser, db: DB) -> EventSourceResponse:
    conv = _owned(db, conversation_id, user)
    question = body.content.strip()
    # Save the user's message first, so it is kept even if generation fails.
    db.add(Message(conversation_id=conv.id, role="user", content=question, citations=[]))
    if not conv.title:
        conv.title = question[:80] + ("…" if len(question) > 80 else "")
    db.commit()

    agent = request.app.state.agent

    async def events():
        final = None
        partial: list[str] = []
        try:
            async for ev in iterate_in_threadpool(agent.stream(question, str(conv.id))):
                if ev["type"] == "done":
                    final = ev
                    continue                 # sent below, after it has been saved
                if ev["type"] == "token":
                    partial.append(ev["text"])
                yield {"event": ev["type"], "data": json.dumps(ev)}
        except asyncio.CancelledError:
            # The browser went away (Stop button, closed tab): keep what was written so far,
            # marked as stopped, so the conversation still makes sense after a reload.
            _save_answer(conv.id, "".join(partial), [], status="stopped")
            raise
        except Exception:
            log.exception("chat generation failed (conversation %s)", conv.id)
            yield {"event": "error", "data": json.dumps(
                {"type": "error", "message": "Sorry, something went wrong while answering. "
                                             "Please try again."})}
            return
        if final is None:
            return
        final["message_id"] = str(_save_answer(conv.id, final["answer"], final["citations"]))
        yield {"event": "done", "data": json.dumps(final)}

    return EventSourceResponse(events(), ping=15)


def _save_answer(conversation_id: uuid.UUID, content: str, citations: list,
                 status: str = "complete") -> uuid.UUID:
    """Store an assistant message (own session: the request's may already be closed)."""
    with new_session() as s:
        msg = Message(conversation_id=conversation_id, role="assistant", content=content,
                      citations=citations, status=status)
        s.add(msg)
        conv = s.get(Conversation, conversation_id)
        if conv is not None:
            conv.updated_at = func.now()
        s.commit()
        return msg.id


@router.put("/{conversation_id}/messages/{message_id}/feedback", response_model=MessageOut)
def feedback(conversation_id: uuid.UUID, message_id: uuid.UUID, body: FeedbackIn,
             user: CurrentUser, db: DB) -> Message:
    """Rate an answer: 1 = helpful, -1 = not helpful, 0 = clear the rating."""
    conv = _owned(db, conversation_id, user)
    msg = db.get(Message, message_id)
    if msg is None or msg.conversation_id != conv.id or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    msg.feedback = body.value or None
    db.commit()
    return msg
