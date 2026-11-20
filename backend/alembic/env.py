"""Alembic environment: one migration history for every table in the database.

DATABASE_URL comes from backend/.env (or the environment), never from alembic.ini,
so credentials stay out of version control.
"""

from logging.config import fileConfig

import pgvector.sqlalchemy  # noqa: F401  (registers the VECTOR type for autogenerate)
from alembic import context
from sqlalchemy import create_engine, pool

from backend.core.config import get_settings
from backend.models import Base as BackendBase
from backend.rag.db.models import Base as EngineBase

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [EngineBase.metadata, BackendBase.metadata]

# Tables managed by someone else: LangGraph's PostgresSaver creates and migrates its own
# checkpoint tables via saver.setup(). Autogenerate must never try to drop them.
EXTERNAL_TABLE_PREFIXES = ("checkpoint",)


def include_name(name, type_, parent_names) -> bool:
    return not (type_ == "table" and bool(name) and name.startswith(EXTERNAL_TABLE_PREFIXES))


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        include_name=include_name,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
