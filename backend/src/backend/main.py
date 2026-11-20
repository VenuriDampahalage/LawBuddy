"""LawBuddy API.

Run (from repo root):  uv run uvicorn backend.main:app --reload --port 8000
Docs:                  http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from backend.api import admin, amendments, auth, chat, documents, laws
from backend.core.config import get_settings
from backend.rag import api as engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    failed = await run_in_threadpool(engine.fail_interrupted)
    if failed:
        log.warning("%d document(s) were mid-processing at shutdown; marked failed", failed)
    with engine.LawAgent.connect() as agent:      # Postgres-backed conversation memory
        app.state.agent = agent
        yield


app = FastAPI(title="LawBuddy API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, laws.router, documents.admin, documents.public, chat.router,
               admin.router, amendments.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
