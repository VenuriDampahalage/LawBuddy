"""Public interface of the RAG engine. The backend imports only from here.

    with LawAgent.connect() as agent:
        for event in agent.stream("Can the police hold me for 3 days?", thread_id="abc"):
            ...   # {"type": "status"|"token"|"done", ...}

    from backend.rag.api import ingest_pdf     # admin uploads
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.core.config import get_settings
from backend.rag.amendments.service import (
    AmendmentError,
    approve_proposal,
    edit_proposal,
    get_proposal,
    list_proposals,
    proposal_counts,
    reject_proposal,
    reopen_proposal,
    revert_proposal,
    scan_amendments,
    scan_in_progress,
)
from backend.rag.documents import (
    ActInfo,
    DocumentInfo,
    LawInfo,
    delete_document,
    document_path,
    fail_interrupted,
    get_document,
    list_documents,
    list_laws,
    set_pending,
    store_upload,
)
from backend.rag.graph.graph import build_graph
from backend.rag.ingestion.pipeline import ingest_pdf, process_document, register_document

__all__ = [
    "ActInfo",
    "AmendmentError",
    "DocumentInfo",
    "LawAgent",
    "LawInfo",
    "approve_proposal",
    "delete_document",
    "document_path",
    "edit_proposal",
    "fail_interrupted",
    "get_document",
    "get_proposal",
    "ingest_pdf",
    "list_documents",
    "list_laws",
    "list_proposals",
    "process_document",
    "proposal_counts",
    "register_document",
    "reject_proposal",
    "reopen_proposal",
    "revert_proposal",
    "scan_amendments",
    "scan_in_progress",
    "set_pending",
    "store_upload",
]


def _fresh_turn(question: str) -> dict[str, Any]:
    """Per-turn fields are reset each turn; `history` accumulates via its reducer."""
    return {"question": question, "attempts": 0, "search_queries": [], "candidates": [],
            "definitions": [], "selected": [], "sufficient": False, "missing": "",
            "answer": "", "citations": []}


class LawAgent:
    def __init__(self, checkpointer=None) -> None:
        self.checkpointer = checkpointer
        self.graph = build_graph(checkpointer)

    @classmethod
    @contextmanager
    def connect(cls) -> Iterator[LawAgent]:
        """Agent with conversation memory persisted in Postgres (LangGraph checkpoints)."""
        conninfo = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
        with ConnectionPool(
            conninfo,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            check=ConnectionPool.check_connection,   # Neon drops idle connections
        ) as pool:
            saver = PostgresSaver(pool)
            saver.setup()      # creates/migrates LangGraph's own checkpoint tables
            yield cls(saver)

    def stream(self, question: str, thread_id: str) -> Iterator[dict[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        final: dict[str, Any] = {}
        for mode, chunk in self.graph.stream(_fresh_turn(question), config,
                                             stream_mode=["custom", "values"]):
            if mode == "custom":
                yield chunk
            else:
                final = chunk
        yield {"type": "done", "answer": final.get("answer", ""),
               "citations": final.get("citations", []), "category": final.get("category"),
               "standalone_question": final.get("standalone_question")}

    def ask(self, question: str, thread_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for event in self.stream(question, thread_id):
            if event["type"] == "done":
                result = event
        return result

    def delete_thread(self, thread_id: str) -> None:
        """Forget a conversation's memory (when the user deletes the conversation)."""
        if self.checkpointer is not None:
            self.checkpointer.delete_thread(thread_id)

    def history(self, thread_id: str) -> list[dict[str, str]]:
        snap = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        return list(snap.values.get("history", [])) if snap and snap.values else []
