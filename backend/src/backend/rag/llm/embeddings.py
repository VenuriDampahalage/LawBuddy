"""OpenAI embeddings (text-embedding-3-small by default)."""

from functools import lru_cache

from openai import OpenAI

from backend.core.config import get_settings

BATCH_SIZE = 128  # well under the per-request input and token limits


@lru_cache
def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key.get_secret_value())


def embed_texts(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        resp = _client().embeddings.create(model=s.embedding_model, input=texts[i:i + BATCH_SIZE])
        out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
