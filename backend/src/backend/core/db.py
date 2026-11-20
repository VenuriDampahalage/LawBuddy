"""The one database engine / connection pool for the whole backend (API and RAG agent)."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,          # Neon closes idle connections (scale-to-zero)
        pool_size=10,                # searches run in parallel (rag/retrieval/search.py)
        connect_args={"connect_timeout": 15},
    )


@lru_cache
def _factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _factory()()


get_session = new_session        # name used throughout the RAG code


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with new_session() as db:
        yield db
