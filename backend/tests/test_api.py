"""API tests against the configured database (no LLM calls).

Every account created here uses the `lbtest-` prefix and is deleted afterwards
(conversations/messages cascade). Skipped when the database is unreachable.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError

from backend.api import auth as auth_api
from backend.core import ratelimit
from backend.core.config import get_settings
from backend.core.db import new_session
from backend.core.security import hash_password
from backend.main import app
from backend.models import User

PREFIX = "lbtest-"


def _db_available() -> bool:
    try:
        with new_session() as db:
            db.execute(text("select 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="database not reachable")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:      # runs the lifespan (agent + memory pool)
        yield c
    with new_session() as db:
        db.execute(delete(User).where(User.email.like(f"{PREFIX}%")))
        db.commit()


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    ratelimit.reset_all()          # every test starts with a clean brute-force counter
    yield
    ratelimit.reset_all()


def _email() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:10]}@example.com"


def _register_and_login(client, email=None, password="correct-horse-1") -> dict:
    email = email or _email()
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin_headers(client) -> dict:
    email, password = _email(), "admin-pass-123"
    with new_session() as db:
        db.add(User(email=email, role="admin", password_hash=hash_password(password)))
        db.commit()
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_register_login_me(client):
    email = _email()
    headers = _register_and_login(client, email)
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == email and me["role"] == "user"


def test_register_cannot_create_admin_and_rejects_duplicates(client):
    email = _email()
    r = client.post("/api/auth/register",
                    json={"email": email, "password": "password-123", "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "user"
    r = client.post("/api/auth/register", json={"email": email.upper(), "password": "x" * 9})
    assert r.status_code == 409


def test_bad_credentials_and_tokens(client):
    email = _email()
    _register_and_login(client, email)
    r = client.post("/api/auth/login", data={"username": email, "password": "wrong-password"})
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me",
                      headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_admin_endpoints_require_admin(client):
    user = _register_and_login(client)
    assert client.get("/api/admin/documents").status_code == 401
    assert client.get("/api/admin/documents", headers=user).status_code == 403
    r = client.post("/api/admin/documents", headers=user,
                    files={"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 403

    admin = _admin_headers(client)
    docs = client.get("/api/admin/documents", headers=admin)
    assert docs.status_code == 200
    assert all({"id", "status", "acts", "chunks"} <= d.keys() for d in docs.json())


def test_upload_rejects_non_pdf(client):
    admin = _admin_headers(client)
    r = client.post("/api/admin/documents", headers=admin,
                    files={"file": ("notes.pdf", b"hello, not a pdf", "application/pdf")})
    assert r.status_code == 415


def test_conversations_are_private(client):
    alice, bob = _register_and_login(client), _register_and_login(client)
    conv = client.post("/api/conversations", headers=alice).json()
    assert [c["id"] for c in client.get("/api/conversations", headers=alice).json()] == [conv["id"]]
    assert client.get("/api/conversations", headers=bob).json() == []

    for method, url in [("get", f"/api/conversations/{conv['id']}/messages"),
                        ("delete", f"/api/conversations/{conv['id']}")]:
        assert getattr(client, method)(url, headers=bob).status_code == 404
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=bob,
                    json={"content": "hello"})
    assert r.status_code == 404

    assert client.delete(f"/api/conversations/{conv['id']}", headers=alice).status_code == 204
    assert client.get("/api/conversations", headers=alice).json() == []


def test_message_validation(client):
    user = _register_and_login(client)
    conv = client.post("/api/conversations", headers=user).json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=user,
                    json={"content": ""})
    assert r.status_code == 422


# ---- brute-force protection ---------------------------------------------------------

def test_login_is_rate_limited_per_email(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_failures_per_email", 3)
    email = _email()
    _register_and_login(client, email)
    for _ in range(3):
        r = client.post("/api/auth/login", data={"username": email, "password": "wrong-pass"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", data={"username": email, "password": "correct-horse-1"})
    assert r.status_code == 429                      # even the right password is refused now
    assert int(r.headers["Retry-After"]) > 0
    assert "try again" in r.json()["detail"]


# ---- Google sign-in (Google's token check is replaced by a fake) ----------------------

def _fake_google(monkeypatch, claims: dict | None):
    monkeypatch.setattr(get_settings(), "google_client_id", "test-client.apps.googleusercontent.com")

    def verify(credential: str, client_id: str) -> dict:
        assert client_id == "test-client.apps.googleusercontent.com"
        if claims is None:
            raise ValueError("Token has wrong audience")
        return claims

    monkeypatch.setattr(auth_api, "verify_google_token", verify)


def _claims(email: str, sub: str | None = None, **extra) -> dict:
    return {"sub": sub or uuid.uuid4().hex, "email": email, "email_verified": True,
            "name": "Google Person", "picture": "https://example.com/a.png", **extra}


def test_auth_config_reports_google_client_id(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    assert client.get("/api/auth/config").json() == {"google_client_id": None}
    _fake_google(monkeypatch, None)
    assert client.get("/api/auth/config").json()["google_client_id"].startswith("test-client")


def test_google_disabled_without_client_id(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    r = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 404


def test_google_creates_user_then_signs_in_again(client, monkeypatch):
    email, sub = _email(), uuid.uuid4().hex
    _fake_google(monkeypatch, _claims(email, sub))
    r = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert user["email"] == email and user["role"] == "user"
    assert user["full_name"] == "Google Person" and user["avatar_url"]
    # second sign-in: same account, not a duplicate
    r2 = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r2.json()["user"]["id"] == user["id"]
    # a Google-only account cannot be signed into with a password
    r3 = client.post("/api/auth/login", data={"username": email, "password": "anything-123"})
    assert r3.status_code == 401
    # and registering the same email with a password points to Google
    r4 = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
    assert r4.status_code == 409 and "Google" in r4.json()["detail"]


def test_google_links_existing_password_account(client, monkeypatch):
    email = _email()
    _register_and_login(client, email)
    _fake_google(monkeypatch, _claims(email))
    r = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 200
    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["email"] == email
    # the password still works too
    r = client.post("/api/auth/login", data={"username": email, "password": "correct-horse-1"})
    assert r.status_code == 200


def test_google_rejects_invalid_or_unverified_tokens(client, monkeypatch):
    _fake_google(monkeypatch, None)                                   # bad signature/audience
    assert client.post("/api/auth/google", json={"credential": "x" * 40}).status_code == 401
    _fake_google(monkeypatch, _claims(_email(), email_verified=False))
    r = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 401 and "verified email" in r.json()["detail"]


# ---- short-lived PDF links for citations -----------------------------------------------

def test_pdf_link_tokens(client):
    user = _register_and_login(client)
    admin = _admin_headers(client)
    docs = client.get("/api/admin/documents", headers=admin).json()
    if len(docs) < 2:
        pytest.skip("needs at least two ingested documents")
    doc, other = docs[0]["id"], docs[1]["id"]

    assert client.get(f"/api/documents/{doc}/file").status_code == 401        # no auth at all
    link = client.get(f"/api/documents/{doc}/link", headers=user).json()
    assert link["expires_in"] == 600 and "token=" in link["url"]
    r = client.get(link["url"])                                                # no header needed
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"

    token = link["url"].split("token=")[1]
    assert client.get(f"/api/documents/{other}/file?token={token}").status_code == 401  # other doc
    user_token = user["Authorization"].removeprefix("Bearer ")
    assert client.get(f"/api/documents/{doc}/file?token={user_token}").status_code == 401
    # a file token is not a login token
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_duplicate_upload_leaves_no_extra_file(client):
    from backend.core.config import get_settings as engine_settings

    admin = _admin_headers(client)
    docs = client.get("/api/admin/documents", headers=admin).json()
    ready = [d for d in docs if d["status"] == "ready"]
    if not ready:
        pytest.skip("needs an ingested document")
    raw = engine_settings().raw_pdf_dir
    source = raw / ready[0]["filename"]
    before = sorted(p.name for p in raw.glob("*.pdf"))
    r = client.post("/api/admin/documents", headers=admin,
                    files={"file": ("renamed-copy.pdf", source.read_bytes(), "application/pdf")})
    assert r.status_code == 202 and r.json()["created"] is False
    assert sorted(p.name for p in raw.glob("*.pdf")) == before


# ---- account page ----------------------------------------------------------------------

def test_update_profile_and_flags(client):
    h = _register_and_login(client)
    r = client.patch("/api/auth/me", headers=h, json={"full_name": "  Kasun Perera  "})
    assert r.status_code == 200 and r.json()["full_name"] == "Kasun Perera"
    me = client.get("/api/auth/me", headers=h).json()
    assert me["has_password"] is True and me["google_linked"] is False


def test_change_password(client):
    email = _email()
    h = _register_and_login(client, email)
    r = client.post("/api/auth/me/password", headers=h,
                    json={"current_password": "wrong-one-123", "new_password": "brand-new-pass"})
    assert r.status_code == 400 and "incorrect" in r.json()["detail"]
    r = client.post("/api/auth/me/password", headers=h,
                    json={"current_password": "correct-horse-1", "new_password": "brand-new-pass"})
    assert r.status_code == 204
    assert client.post("/api/auth/login", data={"username": email, "password": "correct-horse-1"}
                       ).status_code == 401
    assert client.post("/api/auth/login", data={"username": email, "password": "brand-new-pass"}
                       ).status_code == 200


def test_google_only_account_can_set_first_password(client, monkeypatch):
    email = _email()
    _fake_google(monkeypatch, _claims(email))
    tok = client.post("/api/auth/google", json={"credential": "x" * 40}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/me", headers=h).json()["has_password"] is False
    r = client.post("/api/auth/me/password", headers=h, json={"new_password": "first-pass-123"})
    assert r.status_code == 204
    assert client.post("/api/auth/login", data={"username": email, "password": "first-pass-123"}
                       ).status_code == 200


def test_delete_account(client):
    email = _email()
    h = _register_and_login(client, email)
    conv = client.post("/api/conversations", headers=h).json()
    r = client.request("DELETE", "/api/auth/me", headers=h, json={"confirm_email": "other@x.com"})
    assert r.status_code == 400
    r = client.request("DELETE", "/api/auth/me", headers=h, json={"confirm_email": email.upper()})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401
    with new_session() as db:
        from backend.models import Conversation
        assert db.get(Conversation, uuid.UUID(conv["id"])) is None


def test_only_admin_cannot_delete_themselves(client):
    with new_session() as db:
        others = db.scalar(text("select count(*) from users where role='admin' and is_active "
                                "and email not like 'lbtest-%'"))
    if others:
        pytest.skip("a real admin exists, so a test admin is never the only one")
    admin = _admin_headers(client)
    me = client.get("/api/auth/me", headers=admin).json()
    r = client.request("DELETE", "/api/auth/me", headers=admin,
                       json={"confirm_email": me["email"]})
    assert r.status_code == 409


# ---- answer feedback -------------------------------------------------------------------

def test_answer_feedback(client):
    from backend.models import Message

    alice, bob = _register_and_login(client), _register_and_login(client)
    conv = client.post("/api/conversations", headers=alice).json()
    with new_session() as db:
        q = Message(conversation_id=uuid.UUID(conv["id"]), role="user", content="q?", citations=[])
        a = Message(conversation_id=uuid.UUID(conv["id"]), role="assistant", content="a",
                    citations=[])
        db.add_all([q, a])
        db.commit()
        qid, aid = q.id, a.id
    url = f"/api/conversations/{conv['id']}/messages/{aid}/feedback"
    r = client.put(url, headers=alice, json={"value": -1})
    assert r.status_code == 200 and r.json()["feedback"] == -1
    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=alice).json()
    assert msgs[-1]["feedback"] == -1 and msgs[-1]["status"] == "complete"
    assert client.put(url, headers=alice, json={"value": 0}).json()["feedback"] is None
    assert client.put(url, headers=bob, json={"value": 1}).status_code == 404       # not owner
    assert client.put(url, headers=alice, json={"value": 5}).status_code == 422     # bad value
    user_msg = f"/api/conversations/{conv['id']}/messages/{qid}/feedback"
    assert client.put(user_msg, headers=alice, json={"value": 1}).status_code == 404


# ---- admin: users ----------------------------------------------------------------------

def _me(client, headers) -> dict:
    return client.get("/api/auth/me", headers=headers).json()


def test_admin_user_list_requires_admin_and_searches(client):
    user = _register_and_login(client)
    assert client.get("/api/admin/users", headers=user).status_code == 403
    admin = _admin_headers(client)
    email = _me(client, user)["email"]
    found = client.get("/api/admin/users", headers=admin, params={"q": email[:15]}).json()
    assert any(u["email"] == email for u in found)
    row = next(u for u in found if u["email"] == email)
    assert row["role"] == "user" and row["is_active"] and row["conversations"] == 0
    admins = client.get("/api/admin/users", headers=admin, params={"filter": "admins"}).json()
    assert all(u["role"] == "admin" for u in admins)


def test_admin_can_promote_demote_disable_enable(client):
    admin = _admin_headers(client)
    user = _register_and_login(client)
    uid = _me(client, user)["id"]
    r = client.patch(f"/api/admin/users/{uid}", headers=admin, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    r = client.patch(f"/api/admin/users/{uid}", headers=admin, json={"role": "user"})
    assert r.json()["role"] == "user"
    r = client.patch(f"/api/admin/users/{uid}", headers=admin, json={"is_active": False})
    assert r.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=user).status_code == 401      # locked out
    client.patch(f"/api/admin/users/{uid}", headers=admin, json={"is_active": True})
    assert client.get("/api/auth/me", headers=user).status_code == 200      # back in


def test_admin_cannot_lock_themselves_out(client):
    admin = _admin_headers(client)
    me = _me(client, admin)["id"]
    for change in ({"role": "user"}, {"is_active": False}):
        r = client.patch(f"/api/admin/users/{me}", headers=admin, json=change)
        assert r.status_code == 409 and "your own" in r.json()["detail"]


def test_last_active_admin_is_protected(client, monkeypatch):
    from backend.api import admin as admin_api

    a1, a2 = _admin_headers(client), _admin_headers(client)
    monkeypatch.setattr(admin_api, "_active_admins", lambda db: 1)   # pretend a2 is the last
    r = client.patch(f"/api/admin/users/{_me(client, a2)['id']}", headers=a1, json={"role": "user"})
    assert r.status_code == 409 and "last active admin" in r.json()["detail"]


# ---- admin: feedback -------------------------------------------------------------------

def test_admin_feedback_list(client):
    from backend.models import Message

    user, admin = _register_and_login(client), _admin_headers(client)
    conv = client.post("/api/conversations", headers=user).json()
    cid = uuid.UUID(conv["id"])
    with new_session() as db:
        db.add(Message(conversation_id=cid, role="user", content="Can police hold me 3 days?",
                       citations=[]))
        db.commit()
        db.add(Message(conversation_id=cid, role="assistant", content="Generally no. [1]",
                       citations=[{"ref": 1, "citation": "CCPA, s.37, p. 15"}], feedback=-1))
        db.commit()
    assert client.get("/api/admin/feedback", headers=user).status_code == 403
    data = client.get("/api/admin/feedback", headers=admin).json()
    assert data["not_helpful"] >= 1
    item = next(i for i in data["items"] if i["conversation_id"] == str(cid))
    assert item["question"] == "Can police hold me 3 days?" and item["rating"] == -1
    assert item["citations"][0]["citation"].startswith("CCPA")
    helpful = client.get("/api/admin/feedback", headers=admin, params={"rating": "helpful"}).json()
    assert all(i["rating"] == 1 for i in helpful["items"])


# ---- admin: amendment review (real proposals; every test restores the original state) ----

def _proposal(client, admin, target):
    items = client.get("/api/admin/amendments", headers=admin, params={"status_filter": "all"}).json()["items"]
    return next((p for p in items if (p["new_provision"] or p["target_provision"]) == target), None)


def test_amendments_admin_only(client):
    user = _register_and_login(client)
    assert client.get("/api/admin/amendments", headers=user).status_code == 403
    assert client.post("/api/admin/amendments/scan", headers=user).status_code == 403


def test_amendment_approve_and_revert(client):
    admin = _admin_headers(client)
    p = _proposal(client, admin, "s.443")
    if p is None or p["status"] != "pending":
        pytest.skip("needs the pending s.443 proposal from the sample corpus")
    r = client.post(f"/api/admin/amendments/{p['id']}/approve", headers=admin)
    try:
        assert r.status_code == 200 and r.json()["status"] == "approved"
        again = client.post(f"/api/admin/amendments/{p['id']}/approve", headers=admin)
        assert again.status_code == 409                               # can't approve twice
    finally:
        r = client.post(f"/api/admin/amendments/{p['id']}/revert", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "pending"


def test_amendment_reject_reopen_and_edit(client):
    from backend.core.db import get_session
    from backend.rag.amendments.service import recompute_open_proposals
    from backend.rag.db.models import AmendmentProposal

    admin = _admin_headers(client)
    p = _proposal(client, admin, "s.281")
    if p is None or p["status"] != "pending":
        pytest.skip("needs the pending s.281 proposal from the sample corpus")
    try:
        r = client.post(f"/api/admin/amendments/{p['id']}/reject", headers=admin)
        assert r.json()["status"] == "rejected"
        open_ids = [i["id"] for i in client.get("/api/admin/amendments", headers=admin).json()["items"]]
        assert p["id"] not in open_ids                                  # gone from "to review"
        r = client.post(f"/api/admin/amendments/{p['id']}/reopen", headers=admin)
        assert r.json()["status"] == "pending"
        r = client.patch(f"/api/admin/amendments/{p['id']}", headers=admin,
                         json={"proposed_text": "Edited text.", "proposed_heading": "New heading"})
        assert r.status_code == 200 and r.json()["edited"] is True
        assert r.json()["proposed_text"] == "Edited text."
        assert client.patch(f"/api/admin/amendments/{p['id']}", headers=admin,
                            json={"proposed_text": ""}).status_code == 422
    finally:
        with get_session() as db:                                       # undo the edit
            row = db.get(AmendmentProposal, uuid.UUID(p["id"]))
            row.edited, row.status, row.proposed_heading = False, "pending", p["proposed_heading"]
            db.commit()
        recompute_open_proposals()
    restored = _proposal(client, admin, "s.281")
    assert restored["proposed_text"] == p["proposed_text"] and restored["status"] == "pending"
