import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
    verify_password,
    get_password_hash,
    create_password_reset_token,
    verify_password_reset_token,
)
from app.core.email import send_password_reset_email
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    GoogleLoginResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.schemas.token import TokenPair, RefreshRequest
from app.schemas.token import SessionOut
from app.schemas.user import UserOut
from app.models.user import User
from app.models.role import Role
from app.models.oauth_state import OAuthState
from app.models.refresh_token import RefreshToken
from app.services.rate_limiter import rate_limiter
from app.services.auth_service import authenticate_user, add_audit_log

router = APIRouter(tags=["Auth"])
GOOGLE_OAUTH_STATE_TTL_MINUTES = 10


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _persist_refresh_token(db: Session, user_id: int, refresh_token: str) -> None:
    payload = decode_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    exp = payload.get("exp")
    if exp is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
    )


def _list_active_refresh_tokens(db: Session, user_id: int) -> list[RefreshToken]:
    now = _utc_now()
    return db.scalars(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
    ).all()


def _enforce_active_session_limit(db: Session, user_id: int) -> None:
    active_sessions = _list_active_refresh_tokens(db, user_id)
    max_sessions = max(1, settings.AUTH_MAX_ACTIVE_SESSIONS)
    if len(active_sessions) <= max_sessions:
        return

    now = _utc_now()
    for token in active_sessions[max_sessions:]:
        token.revoked_at = now
        token.revoked_reason = "session_limit"
        db.add(token)


def _issue_token_pair(db: Session, user_id: int) -> TokenPair:
    access_token = create_access_token(str(user_id))
    refresh_token = create_refresh_token(str(user_id))
    _persist_refresh_token(db, user_id, refresh_token)
    db.flush()
    _enforce_active_session_limit(db, user_id)
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


def _get_refresh_token_record(db: Session, refresh_token: str) -> RefreshToken | None:
    token_record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token)))
    if not token_record:
        return None

    now = _utc_now()
    if token_record.revoked_at is not None or token_record.expires_at <= now:
        return None

    return token_record


def _require_google_oauth_config() -> None:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")


def _build_unique_username(db: Session, email: str) -> str:
    email_name = email.split("@", 1)[0].lower()
    base_username = re.sub(r"[^a-z0-9._-]", "", email_name) or "googleuser"
    username = base_username
    suffix = 1
    while db.scalar(select(User).where(User.username == username)):
        username = f"{base_username}{suffix}"
        suffix += 1
    return username


def _get_google_default_role_id(db: Session) -> int:
    admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
    if admin_role:
        return admin_role.id

    raise HTTPException(status_code=500, detail="Admin role not available")


def _is_google_admin_email(email: str) -> bool:
    configured = settings.GOOGLE_ADMIN_EMAILS
    if not configured:
        return False

    allowed = {item.strip().lower() for item in configured.split(",") if item.strip()}
    return email.lower() in allowed


def _get_google_role_id(db: Session, email: str) -> int:
    if _is_google_admin_email(email):
        return _get_google_default_role_id(db)

    role = db.scalar(select(Role).where(Role.name == "Sales"))
    if role:
        return role.id

    fallback_role = db.scalar(select(Role).order_by(Role.id.asc()))
    if not fallback_role:
        raise HTTPException(status_code=500, detail="No roles available for Google user provisioning")
    return fallback_role.id


def _create_google_oauth_state(db: Session, state: str) -> None:
    now = _utc_now()
    expires_at = now + timedelta(minutes=GOOGLE_OAUTH_STATE_TTL_MINUTES)
    db.add(
        OAuthState(
            provider="google",
            state=state,
            expires_at=expires_at,
        )
    )
    db.commit()


def _consume_google_oauth_state(db: Session, state: str) -> None:
    now = _utc_now()
    state_record = db.scalar(select(OAuthState).where(OAuthState.provider == "google", OAuthState.state == state))
    if not state_record:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    if state_record.consumed_at is not None:
        raise HTTPException(status_code=400, detail="OAuth state already used")

    if state_record.expires_at <= now:
        raise HTTPException(status_code=400, detail="OAuth state expired")

    state_record.consumed_at = now
    db.add(state_record)
    db.commit()


def _enforce_auth_rate_limit(db: Session, key: str, limit: int, user_id: int | None = None) -> None:
    allowed = rate_limiter.is_allowed(
        key=key,
        limit=limit,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    if allowed:
        return

    add_audit_log(
        db=db,
        user_id=user_id,
        action="RATE_LIMIT_EXCEEDED",
        table_name="auth",
        new_value={"key": key, "limit": limit, "window_seconds": settings.AUTH_RATE_LIMIT_WINDOW_SECONDS},
    )
    raise HTTPException(status_code=429, detail="Too many requests, please try again later")

@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    _enforce_auth_rate_limit(db=db, key=f"login:{payload.username.lower()}", limit=settings.AUTH_LOGIN_MAX_REQUESTS)
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials or account locked")
    return _issue_token_pair(db, user.id)


@router.post("/refresh", response_model=TokenPair)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    refresh_hash = hash_token(payload.refresh_token)
    _enforce_auth_rate_limit(db=db, key=f"refresh:{refresh_hash}", limit=settings.AUTH_REFRESH_MAX_REQUESTS)

    data = decode_refresh_token(payload.refresh_token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id_raw = data.get("sub")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    token_record = _get_refresh_token_record(db, payload.refresh_token)
    if not token_record or token_record.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not user or not user.is_active or user.is_locked:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    token_record.revoked_at = _utc_now()
    token_record.revoked_reason = "rotated"
    db.add(token_record)

    access_token = create_access_token(str(user_id))
    refresh_token = create_refresh_token(str(user_id))
    _persist_refresh_token(db, user_id, refresh_token)
    db.commit()

    add_audit_log(db=db, user_id=user_id, action="TOKEN_REFRESHED", table_name="users", record_id=user_id)

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    token_payload = decode_refresh_token(payload.refresh_token)
    if not token_payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if str(current_user.id) != str(token_payload.get("sub")):
        raise HTTPException(status_code=403, detail="Refresh token does not belong to current user")

    token_record = _get_refresh_token_record(db, payload.refresh_token)
    if token_record:
        token_record.revoked_at = _utc_now()
        token_record.revoked_reason = "logout"
        db.add(token_record)
        db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="LOGOUT_SUCCESS",
        table_name="users",
        record_id=current_user.id,
    )
    return MessageResponse(message="Logged out successfully")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sessions = _list_active_refresh_tokens(db, current_user.id)
    return [
        SessionOut(
            session_id=session.id,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )
        for session in sessions
    ]


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sessions = _list_active_refresh_tokens(db, current_user.id)
    now = _utc_now()
    revoked_count = 0

    for session in sessions:
        session.revoked_at = now
        session.revoked_reason = "logout_all"
        db.add(session)
        revoked_count += 1

    db.commit()
    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="LOGOUT_ALL_SUCCESS",
        table_name="users",
        record_id=current_user.id,
        new_value={"revoked_sessions": revoked_count},
    )
    return MessageResponse(message="Logged out from all sessions")


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="Password change not allowed for Google accounts")

    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.updated_by = current_user.id
    db.add(current_user)
    db.commit()

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PASSWORD_CHANGED",
        table_name="users",
        record_id=current_user.id,
    )

    return MessageResponse(message="Password updated successfully")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    # Always return a generic message to avoid user enumeration
    user = db.scalar(select(User).where(User.email == payload.email))

    if user:
        # Create reset token and audit log. Email sending can be wired later.
        reset_token = create_password_reset_token(str(user.id))
        reset_link = None
        if settings.FRONTEND_RESET_PASSWORD_URL:
            reset_link = f"{settings.FRONTEND_RESET_PASSWORD_URL}?token={reset_token}"

        add_audit_log(
            db=db,
            user_id=user.id,
            action="PASSWORD_RESET_REQUESTED",
            table_name="users",
            record_id=user.id,
        )
        if reset_link:
            try:
                send_password_reset_email(user.email, reset_link)
            except Exception as exc:
                add_audit_log(
                    db=db,
                    user_id=user.id,
                    action="PASSWORD_RESET_EMAIL_FAILED",
                    table_name="users",
                    record_id=user.id,
                    new_value={"error": str(exc)[:250]},
                )

    return MessageResponse(message="If the account exists, a reset link will be sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    user_id = verify_password_reset_token(payload.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.scalar(select(User).where(User.id == int(user_id)))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="Password reset not allowed for Google accounts")

    user.password_hash = get_password_hash(payload.new_password)
    user.updated_by = user.id
    db.add(user)
    db.commit()

    add_audit_log(
        db=db,
        user_id=user.id,
        action="PASSWORD_RESET_COMPLETED",
        table_name="users",
        record_id=user.id,
    )

    return MessageResponse(message="Password reset successful")


@router.get("/google/login", response_model=GoogleLoginResponse)
def google_login(state: str | None = None, db: Session = Depends(get_db)):
    _require_google_oauth_config()

    oauth_state = state or secrets.token_urlsafe(24)
    _create_google_oauth_state(db, oauth_state)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": oauth_state,
        "access_type": "online",
        "prompt": "select_account",
    }
    authorization_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return GoogleLoginResponse(authorization_url=authorization_url, state=oauth_state)


@router.get("/google/callback", response_model=TokenPair)
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    _require_google_oauth_config()
    _consume_google_oauth_state(db, state)

    try:
        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to connect to Google token endpoint")

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Google token exchange failed")

    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google token payload missing access token")

    try:
        profile_response = httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to connect to Google userinfo endpoint")

    if profile_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch Google user profile")

    google_profile = profile_response.json()
    email = google_profile.get("email")
    email_verified = google_profile.get("email_verified", False)
    if not email or not email_verified:
        raise HTTPException(status_code=400, detail="Google account email is missing or not verified")

    user = db.scalar(select(User).where(User.email == email, User.is_deleted.is_(False)))
    if user:
        if user.is_locked or not user.is_active:
            raise HTTPException(status_code=403, detail="Account is inactive or locked")
        if user.auth_provider == "local":
            user.auth_provider = "both"
        if _is_google_admin_email(email):
            user.role_id = _get_google_default_role_id(db)
        user.failed_attempts = 0
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        role_id = _get_google_role_id(db, email)
        user = User(
            username=_build_unique_username(db, email),
            email=email,
            password_hash=get_password_hash(secrets.token_urlsafe(32)),
            role_id=role_id,
            auth_provider="google",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            is_deleted=False,
            created_by=None,
            updated_by=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    add_audit_log(db=db, user_id=user.id, action="GOOGLE_LOGIN_SUCCESS", table_name="users", record_id=user.id)
    return _issue_token_pair(db, user.id)