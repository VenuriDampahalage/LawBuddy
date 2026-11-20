"""Agent state. Everything stored here is checkpointed in Postgres per conversation thread,
so it must be JSON-friendly (plain dicts/lists/strings)."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Turn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class AgentState(TypedDict, total=False):
    # Conversation memory: appended to on every turn (reducer = list concatenation).
    history: Annotated[list[Turn], operator.add]

    # Per-turn fields, reset by the caller at the start of each turn.
    question: str
    category: str
    standalone_question: str
    search_queries: list[str]
    attempts: int
    candidates: list[dict]
    definitions: list[dict]
    selected: list[dict]
    sufficient: bool
    missing: str
    answer: str
    citations: list[dict]


# ---- structured LLM outputs -----------------------------------------------------------

class Plan(BaseModel):
    category: Literal["legal", "greeting", "off_topic"]
    standalone_question: str
    search_queries: list[str] = Field(description="2-3 queries in statutory language")


class Selection(BaseModel):
    relevant: list[int] = Field(description="candidate numbers, most important first, max 6")
    sufficient: bool
    missing: str = Field(description="what is missing if not sufficient, else empty")


class Broaden(BaseModel):
    search_queries: list[str]
