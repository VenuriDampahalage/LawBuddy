from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from backend.core import ratelimit
from backend.core.config import get_settings
from backend.core.security import (
    DB,
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.models import Conversation, User
from backend.schemas import (
    AuthConfigOut,
    DeleteAccountIn,
    GoogleSignInIn,
    PasswordIn,
    ProfileIn,
    RegisterIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INCORRECT = "Incorrect email or password"
_google_transport = google_requests.Request()


@router.get("/config", response_model=AuthConfigOut)
def auth_config() -> AuthConfigOut:
    """Public settings the sign-in page needs (which providers are enabled)."""
    return AuthConfigOut(google_client_id=get_settings().google_client_id or None)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, db: DB) -> User:
    """Public sign-up. Always creates a normal user; admins are created with the CLI."""
    s, ip = get_settings(), ratelimit.client_ip(request)
    ratelimit.enforce(ratelimit.registrations, f"ip:{ip}", s.registrations_per_ip,
                      "Too many accounts were created from this network.")
    ratelimit.registrations.hit(f"ip:{ip}")

    email = body.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        hint = (" It was created with Google; use “Continue with Google”."
                if existing.password_hash is None else "")
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"An account with this email already exists.{hint}")
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password),
                role="user")
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenOut)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request,
          db: DB) -> TokenOut:
    """OAuth2 password flow: form fields `username` (the email) and `password`."""
    s, ip = get_settings(), ratelimit.client_ip(request)
    email = form.username.lower().strip()
    msg = "Too many failed sign-in attempts."
    ratelimit.enforce(ratelimit.login_failures, f"email:{email}", s.login_failures_per_email, msg)
    ratelimit.enforce(ratelimit.login_failures, f"ip:{ip}", s.login_failures_per_ip, msg)

    user = db.scalar(select(User).where(User.email == email))
    # Same error for unknown email, Google-only account and wrong password
    # (no account enumeration).
    ok = (user is not None and user.is_active and user.password_hash is not None
          and verify_password(form.password, user.password_hash))
    if not ok:
        ratelimit.login_failures.hit(f"email:{email}")
        ratelimit.login_failures.hit(f"ip:{ip}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INCORRECT,
                            headers={"WWW-Authenticate": "Bearer"})
    ratelimit.login_failures.reset(f"email:{email}")
    return TokenOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


def verify_google_token(credential: str, client_id: str) -> dict[str, Any]:
    """Check Google's ID token: signature (Google's public keys), issuer, expiry and that it
    was issued for OUR client ID. Raises ValueError if anything is wrong."""
    return google_id_token.verify_oauth2_token(credential, _google_transport, audience=client_id,
                                               clock_skew_in_seconds=10)


@router.post("/google", response_model=TokenOut)
def google_sign_in(body: GoogleSignInIn, request: Request, db: DB) -> TokenOut:
    """Sign in (or sign up) with a Google ID token from the "Sign in with Google" button."""
    s, ip = get_settings(), ratelimit.client_ip(request)
    if not s.google_client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not enabled")
    ratelimit.enforce(ratelimit.login_failures, f"ip:{ip}", s.login_failures_per_ip,
                      "Too many failed sign-in attempts.")
    try:
        claims = verify_google_token(body.credential, s.google_client_id)
    except ValueError:
        ratelimit.login_failures.hit(f"ip:{ip}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Google sign-in could not be verified. Please try again.") from None

    sub, email = claims.get("sub"), (claims.get("email") or "").lower()
    if not sub or not email or not claims.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Your Google account has no verified email address.")

    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        # Same verified email as an existing account -> link it (one person, one account).
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            # is_active set explicitly: column defaults are only applied when the row is
            # flushed, and the disabled-account check below runs before that.
            user = User(email=email, full_name=claims.get("name"), role="user",
                        password_hash=None, is_active=True)
            db.add(user)
        user.google_sub = sub
    user.avatar_url = claims.get("picture") or user.avatar_url
    if not user.full_name and claims.get("name"):
        user.full_name = claims["name"]
    if user.is_active is False:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled.")
    db.commit()
    return TokenOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(body: ProfileIn, user: CurrentUser, db: DB) -> User:
    user.full_name = (body.full_name or "").strip() or None
    db.commit()
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordIn, request: Request, user: CurrentUser, db: DB) -> None:
    """Change the password, or set a first one on a Google-only account."""
    s, key = get_settings(), f"email:{user.email}"
    if user.password_hash is not None:
        ratelimit.enforce(ratelimit.login_failures, key, s.login_failures_per_email,
                          "Too many incorrect password attempts.")
        if not body.current_password or not verify_password(body.current_password,
                                                            user.password_hash):
            ratelimit.login_failures.hit(key)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(body: DeleteAccountIn, request: Request, user: CurrentUser,
                         db: DB) -> None:
    """Delete the account, its conversations and the assistant's memory of them."""
    if body.confirm_email.strip().lower() != user.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Type your email address exactly to confirm.")
    if user.role == "admin":
        admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin",
                                                                       User.is_active))
        if admins <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "You are the only admin. Make someone else an admin first.")
    thread_ids = [str(c) for c in db.scalars(select(Conversation.id)
                                             .where(Conversation.user_id == user.id))]
    agent = request.app.state.agent
    for tid in thread_ids:
        await run_in_threadpool(agent.delete_thread, tid)
    db.delete(user)            # conversations and messages cascade
    db.commit()
