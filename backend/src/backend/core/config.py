"""All settings for the backend (API + RAG agent), loaded from the environment / backend/.env.

Real environment variables take precedence over the .env file, so a deployment sets them in
its dashboard and needs no .env at all.
"""

import json
import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/ (the deployable project root): backend/src/backend/core/config.py -> parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[3]

log = logging.getLogger(__name__)

WEAK_SECRETS = {"", "change-me", "changeme", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    # --- OpenAI ---
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    chat_model: str = "gpt-6-luna"
    # Set false if CHAT_MODEL is switched to a model without the `reasoning` parameter.
    reasoning_effort_supported: bool = True
    # Reasoning effort per step ("none" | "low" | "medium" | "high"; empty = the model's
    # default). Lower effort = less waiting before the first word. Measured on gpt-6-luna:
    # answer first token ~3.7s at default vs ~1.1-2.5s at low; select ~1s faster at none.
    # Checked with the eval set (backend/eval) — re-run it after changing these.
    plan_effort: str = "low"
    select_effort: str = "none"
    answer_effort: str = "low"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- LlamaParse (llama-cloud) ---
    llama_cloud_api_key: SecretStr = Field(default=SecretStr(""))
    llamaparse_tier: str = "cost_effective"  # fast | cost_effective | agentic | agentic_plus
    llamaparse_version: str = "latest"

    # --- Storage ---
    database_url: str = "postgresql+psycopg://lawbuddy:lawbuddy@localhost:5432/lawbuddy"
    raw_pdf_dir: Path = BACKEND_ROOT / "data" / "raw_pdfs"      # uploaded PDFs
    parsed_dir: Path = BACKEND_ROOT / "data" / "parsed"         # LlamaParse cache

    # --- Auth ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    # "Sign in with Google": the OAuth *Web* client ID from Google Cloud Console
    # (…apps.googleusercontent.com). Public value; no client secret is needed.
    google_client_id: str | None = None

    # --- HTTP ---
    # The frontend's address(es): websites allowed to call this API from the browser.
    # Set in .env / the host's environment variables, comma-separated, e.g.
    #   CORS_ORIGINS=https://lawbuddy.vercel.app,http://localhost:5173
    # (Local development works without it: Vite proxies /api, so the browser sees one site.)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_upload_mb: int = 50

    # Brute-force protection (per server process).
    login_failures_per_email: int = 10       # per 15 minutes
    login_failures_per_ip: int = 30          # per 15 minutes
    registrations_per_ip: int = 10           # per hour

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        """Accept a comma-separated string or a JSON list; drop trailing slashes, because the
        browser's Origin header never has one ("https://x.vercel.app/" would never match)."""
        if isinstance(value, str):
            value = value.strip()
            value = json.loads(value) if value.startswith("[") else value.split(",")
        if isinstance(value, list):
            return [str(o).strip().rstrip("/") for o in value if str(o).strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.jwt_secret.strip().lower() in WEAK_SECRETS or len(s.jwt_secret) < 32:
        # Development fallback: a random secret per process. Tokens stop working after a
        # restart. Set JWT_SECRET (>= 32 random chars) in .env for anything real.
        log.warning("JWT_SECRET is missing or weak; using a temporary random secret. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        s.jwt_secret = secrets.token_urlsafe(48)
    if not s.cors_origins:
        log.warning("CORS_ORIGINS is not set: browsers on other sites can't call this API. "
                    "Set it to the frontend's address, e.g. CORS_ORIGINS=https://lawbuddy.vercel.app")
    return s
