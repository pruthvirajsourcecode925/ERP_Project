import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token, create_password_reset_token, get_password_hash
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from sqlalchemy import select
from uuid import uuid4

client = TestClient(app)


def get_admin_token() -> str:
    db = SessionLocal()
    admin_id = None
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
        if admin and admin_role:
            admin.password_hash = get_password_hash("Admin@12345")
            admin.role_id = admin_role.id
            admin.is_active = True
            admin.is_locked = False
            admin.failed_attempts = 0
            admin.auth_provider = "both"
            db.add(admin)
            db.commit()
            admin_id = admin.id
    finally:
        db.close()

    assert admin_id is not None
    return create_access_token(str(admin_id))


def create_test_user() -> tuple[str, str]:
    """Create a unique local user for auth tests."""
    uid = uuid4().hex[:10]
    username = f"authuser{uid}"
    password = "Test@12345"
    resp = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "role": "Sales",
        },
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert resp.status_code == 200
    return username, password


@pytest.mark.slow
def test_login_success():
    """Test login with bootstrap admin user."""
    username, password = create_test_user()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_failure():
    """Test login with invalid credentials."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "wronguser", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials or account locked"


def test_token_generation():
    """Test that create_access_token produces a valid JWT string."""
    token = create_access_token("1")
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 20


@pytest.mark.slow
def test_protected_route_me():
    """Test accessing /me with a valid token."""
    username, password = create_test_user()
    # Login first
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = login_resp.json()["access_token"]

    # Access protected /me
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == username
    assert "email" in data


@pytest.mark.slow
def test_change_password():
    """Test change-password flow for a local user."""
    import random

    uid = random.randint(10000, 99999)
    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"pwdchange{uid}",
            "email": f"pwdchange{uid}@example.com",
            "password": "Old@12345",
            "role": "Sales",
        },
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert create_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": f"pwdchange{uid}", "password": "Old@12345"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    change_resp = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "Old@12345", "new_password": "New@12345"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert change_resp.status_code == 200
    assert "updated" in change_resp.json()["message"].lower()

    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"pwdchange{uid}", "password": "Old@12345"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"pwdchange{uid}", "password": "New@12345"},
    )
    assert new_login.status_code == 200


@pytest.mark.slow
def test_forgot_password_and_reset():
    """Test forgot-password and reset-password flow."""
    import random

    uid = random.randint(10000, 99999)
    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"resetuser{uid}",
            "email": f"resetuser{uid}@example.com",
            "password": "Old@12345",
            "role": "Sales",
        },
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]

    forgot_resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"resetuser{uid}@example.com"},
    )
    assert forgot_resp.status_code == 200

    reset_token = create_password_reset_token(str(user_id))
    reset_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "New@12345"},
    )
    assert reset_resp.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"resetuser{uid}", "password": "Old@12345"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"resetuser{uid}", "password": "New@12345"},
    )
    assert new_login.status_code == 200


def test_google_login_returns_authorization_url(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")

    response = client.get("/api/v1/auth/google/login")
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert data["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state" in data
    assert len(data["state"]) > 10


def test_google_callback_creates_user_and_returns_tokens(monkeypatch):
    import random

    from app.core.config import settings

    uid = random.randint(10000, 99999)
    test_email = f"googleuser{uid}@example.com"

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")

    class MockResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def mock_post(url, data=None, timeout=None):
        assert "oauth2.googleapis.com/token" in url
        assert data is not None
        assert data["grant_type"] == "authorization_code"
        return MockResponse(200, {"access_token": "google-access-token"})

    def mock_get(url, headers=None, timeout=None):
        assert "googleapis.com/oauth2/v3/userinfo" in url
        assert headers is not None
        return MockResponse(
            200,
            {
                "sub": "google-subject-id",
                "email": test_email,
                "email_verified": True,
                "name": "Google Test User",
            },
        )

    monkeypatch.setattr("app.api.v1.endpoints.auth.httpx.post", mock_post)
    monkeypatch.setattr("app.api.v1.endpoints.auth.httpx.get", mock_get)

    login_resp = client.get("/api/v1/auth/google/login")
    assert login_resp.status_code == 200
    oauth_state = login_resp.json()["state"]

    callback_resp = client.get("/api/v1/auth/google/callback", params={"code": "test-code", "state": oauth_state})
    assert callback_resp.status_code == 200
    callback_data = callback_resp.json()
    assert "access_token" in callback_data
    assert "refresh_token" in callback_data

    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {callback_data['access_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == test_email


def test_google_callback_rejects_invalid_state(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")

    callback_resp = client.get("/api/v1/auth/google/callback", params={"code": "test-code", "state": "invalid-state"})
    assert callback_resp.status_code == 400
    assert callback_resp.json()["detail"] == "Invalid OAuth state"


def test_refresh_token_rotation_invalidates_old_refresh_token():
    username, password = create_test_user()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200
    old_refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert refresh_resp.status_code == 200
    refreshed_data = refresh_resp.json()
    assert "access_token" in refreshed_data
    assert "refresh_token" in refreshed_data
    assert refreshed_data["refresh_token"] != old_refresh_token

    reuse_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["detail"] == "Invalid refresh token"


def test_logout_revokes_refresh_token():
    username, password = create_test_user()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200
    assert "logged out" in logout_resp.json()["message"].lower()

    refresh_after_logout = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_after_logout.status_code == 401
    assert refresh_after_logout.json()["detail"] == "Invalid refresh token"


def test_login_rate_limit_exceeded(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_REQUESTS", 2)

    username = "ratelimit-login-user"
    payload = {"username": username, "password": "wrongpassword"}

    resp1 = client.post("/api/v1/auth/login", json=payload)
    resp2 = client.post("/api/v1/auth/login", json=payload)
    resp3 = client.post("/api/v1/auth/login", json=payload)

    assert resp1.status_code == 401
    assert resp2.status_code == 401
    assert resp3.status_code == 429
    assert "too many requests" in resp3.json()["detail"].lower()


@pytest.mark.slow
def test_refresh_rate_limit_exceeded(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "AUTH_REFRESH_MAX_REQUESTS", 2)

    username, password = create_test_user()
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    first = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    third = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert first.status_code == 200
    assert second.status_code == 401
    assert third.status_code == 429
    assert "too many requests" in third.json()["detail"].lower()


@pytest.mark.slow
def test_list_sessions_and_logout_all(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_MAX_ACTIVE_SESSIONS", 10)

    username, password = create_test_user()

    login_one = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_one.status_code == 200

    login_two = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_two.status_code == 200

    access_two = login_two.json()["access_token"]
    refresh_one = login_one.json()["refresh_token"]
    refresh_two = login_two.json()["refresh_token"]

    sessions_resp = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {access_two}"},
    )
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()
    assert len(sessions) >= 2
    assert "session_id" in sessions[0]

    logout_all_resp = client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_two}"},
    )
    assert logout_all_resp.status_code == 200
    assert "all sessions" in logout_all_resp.json()["message"].lower()

    refresh_after_logout_one = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_one},
    )
    refresh_after_logout_two = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_two},
    )
    assert refresh_after_logout_one.status_code == 401
    assert refresh_after_logout_two.status_code == 401


@pytest.mark.slow
def test_auth_max_active_sessions_revokes_oldest(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_MAX_ACTIVE_SESSIONS", 2)

    username, password = create_test_user()

    login_one = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_one.status_code == 200
    refresh_one = login_one.json()["refresh_token"]

    login_two = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_two.status_code == 200

    login_three = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_three.status_code == 200

    oldest_refresh_reuse = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_one},
    )
    assert oldest_refresh_reuse.status_code == 401
    assert oldest_refresh_reuse.json()["detail"] == "Invalid refresh token"
