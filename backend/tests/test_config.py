"""Settings parsing (no database or API calls)."""

import pytest

from backend.core.config import Settings


@pytest.mark.parametrize("raw, expected", [
    ("https://lawbuddy.vercel.app", ["https://lawbuddy.vercel.app"]),
    ("https://lawbuddy.vercel.app/, http://localhost:5173 ",
     ["https://lawbuddy.vercel.app", "http://localhost:5173"]),
    ('["https://lawbuddy.vercel.app/", "http://localhost:5173"]',
     ["https://lawbuddy.vercel.app", "http://localhost:5173"]),
    ("", []),
])
def test_cors_origins_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origins == expected


def test_no_frontend_address_is_hardcoded(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == []
