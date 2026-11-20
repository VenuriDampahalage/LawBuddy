"""Admin review of amendments: scan amendment Acts, review proposed section text, apply."""

import logging
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.security import AdminUser
from backend.rag import api as engine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/amendments", tags=["admin: amendments"])


class ProposalOut(BaseModel):
    id: uuid.UUID
    status: str
    operation: str
    summary: str
    problem: str | None
    edited: bool
    amendment_act: str
    amendment_year: int | None
    amendment_provision: str | None
    amendment_heading: str | None
    amendment_text: str
    target_act: str
    target_provision: str
    new_provision: str | None
    current_heading: str | None
    proposed_heading: str | None
    current_text: str
    proposed_text: str
    reviewed_at: datetime | None
    created_at: datetime


class ProposalListOut(BaseModel):
    scanning: bool
    counts: dict[str, int]
    items: list[ProposalOut]


class EditIn(BaseModel):
    proposed_text: str = Field(min_length=1, max_length=100_000)
    proposed_heading: str | None = Field(default=None, max_length=500)


def _call(fn, *args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    except engine.AmendmentError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


def _scan() -> None:
    try:
        engine.scan_amendments()
    except Exception:
        log.exception("amendment scan failed")


@router.get("", response_model=ProposalListOut)
def list_proposals(_: AdminUser,
                   status_filter: Literal["open", "approved", "rejected", "all"] = "open"
                   ) -> ProposalListOut:
    items = engine.list_proposals(None if status_filter == "all" else status_filter)
    return ProposalListOut(scanning=engine.scan_in_progress(), counts=engine.proposal_counts(),
                           items=[ProposalOut(**i) for i in items])


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
def scan(background: BackgroundTasks, _: AdminUser) -> dict[str, bool]:
    """Look for new amending sections and propose amended text (runs in the background)."""
    if not engine.scan_in_progress():
        background.add_task(_scan)
    return {"started": True}


@router.patch("/{proposal_id}", response_model=ProposalOut)
def edit(proposal_id: uuid.UUID, body: EditIn, _: AdminUser) -> ProposalOut:
    _call(engine.edit_proposal, proposal_id, body.proposed_text, body.proposed_heading)
    return ProposalOut(**engine.get_proposal(proposal_id))


@router.post("/{proposal_id}/{action}", response_model=ProposalOut)
def act(proposal_id: uuid.UUID, action: Literal["approve", "reject", "reopen", "revert"],
        user: AdminUser) -> ProposalOut:
    if action == "approve":
        _call(engine.approve_proposal, proposal_id, user.id)
    elif action == "reject":
        _call(engine.reject_proposal, proposal_id, user.id)
    elif action == "reopen":
        _call(engine.reopen_proposal, proposal_id)
    else:
        _call(engine.revert_proposal, proposal_id)
    return ProposalOut(**_call(engine.get_proposal, proposal_id))
