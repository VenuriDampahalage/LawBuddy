"""Thin wrapper around the OpenAI Responses API for the agent's LLM calls."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from backend.core.config import get_settings


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key.get_secret_value(), timeout=120)


def _reasoning(effort: str | None) -> dict[str, Any]:
    """The `reasoning` argument, or nothing for the model's default / unsupported models."""
    if effort and get_settings().reasoning_effort_supported:
        return {"reasoning": {"effort": effort}}
    return {}


def structured[T: BaseModel](
    instructions: str, user_input: str, schema: type[T], effort: str | None = "low"
) -> T:
    """One call that must return an instance of `schema` (structured output).
    Planning/selection are classification-like, so reasoning effort defaults to low
    (measured: ~1s faster per call, no reasoning tokens)."""
    resp = _client().responses.parse(
        model=get_settings().chat_model,
        instructions=instructions,
        input=user_input,
        text_format=schema,
        **_reasoning(effort),
    )
    if resp.output_parsed is None:
        raise RuntimeError("Model returned no parseable output")
    return resp.output_parsed


def stream_text(instructions: str, user_input: str, effort: str | None = None) -> Iterator[str]:
    """Yield answer text deltas as they are generated."""
    stream = _client().responses.create(
        model=get_settings().chat_model,
        instructions=instructions,
        input=user_input,
        stream=True,
        **_reasoning(effort),
    )
    for event in stream:
        if event.type == "response.output_text.delta":
            yield event.delta
        elif event.type == "response.failed":
            raise RuntimeError(f"Generation failed: {event.response.error}")
