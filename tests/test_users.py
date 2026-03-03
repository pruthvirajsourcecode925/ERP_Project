import random
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User

client = TestClient(app)


def get_admin_token() -> str:
    """Helper to get bootstrap admin auth token."""
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


def test_create_user():
    """Test creating a new user with role name."""
    uid = random.randint(10000, 99999)
    user_data = {
        "username": f"testuser{uid}",
        "email": f"test{uid}@example.com",
        "password": "Password123",
        "role": "Sales",
        "auth_provider": "local",
    }
    response = client.post("/api/v1/users/", json=user_data)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user_data["username"]
    assert data["email"] == user_data["email"]
    assert "id" in data


def test_get_user():
    """Test fetching user by ID (requires auth)."""
    token = get_admin_token()
    response = client.get(
        "/api/v1/users/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "username" in response.json()


def test_update_user():
    """Test updating user email (requires auth)."""
    token = get_admin_token()
    user_update_data = {"email": f"updated{random.randint(1000,9999)}@example.com"}
    response = client.put(
        "/api/v1/users/1",
        json=user_update_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == user_update_data["email"]


@pytest.mark.slow
def test_update_user_password():
    """Test updating password actually updates login credentials."""
    uid = random.randint(10000, 99999)
    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"pwduser{uid}",
            "email": f"pwduser{uid}@example.com",
            "password": "Old@12345",
            "role": "Sales",
        },
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]

    token = get_admin_token()
    update_resp = client.put(
        f"/api/v1/users/{user_id}",
        json={"password": "New@12345"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_resp.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"pwduser{uid}", "password": "Old@12345"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": f"pwduser{uid}", "password": "New@12345"},
    )
    assert new_login.status_code == 200


def test_list_users():
    """Test listing users (admin only)."""
    token = get_admin_token()
    response = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) >= 1  # At least admin user


def test_delete_user():
    """Test soft-deleting a user (admin only)."""
    token = get_admin_token()
    # First create a user to delete
    uid = random.randint(10000, 99999)
    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"deluser{uid}",
            "email": f"deluser{uid}@example.com",
            "password": "Password123",
            "role": "Sales",
        },
    )
    user_id = create_resp.json()["id"]

    # Delete it
    response = client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


def test_cannot_delete_self():
    """Test that admin cannot delete themselves."""
    token = get_admin_token()
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = me.json()["id"]
    response = client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Cannot delete yourself" in response.json()["detail"]


@pytest.mark.slow
def test_non_admin_cannot_create_admin_user():
    uid = random.randint(10000, 99999)
    username = f"salesuser{uid}"
    password = "Password123"

    create_sales_resp = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "role": "Sales",
        },
    )
    assert create_sales_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200
    sales_token = login_resp.json()["access_token"]

    admin_create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"newadmin{uid}",
            "email": f"newadmin{uid}@example.com",
            "password": "Admin@12345",
            "role": "Admin",
        },
        headers={"Authorization": f"Bearer {sales_token}"},
    )
    assert admin_create_resp.status_code == 403


def test_admin_can_create_admin_user():
    token = get_admin_token()
    uid = random.randint(10000, 99999)

    admin_create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"admincreated{uid}",
            "email": f"admincreated{uid}@example.com",
            "password": "Admin@12345",
            "role": "Admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert admin_create_resp.status_code == 200
    assert admin_create_resp.json()["username"] == f"admincreated{uid}"


def test_list_users_with_filters():
    token = get_admin_token()
    uid = random.randint(10000, 99999)
    username = f"filteruser{uid}"

    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "Password123",
            "role": "Sales",
            "auth_provider": "local",
        },
    )
    assert create_resp.status_code == 200

    response = client.get(
        f"/api/v1/users/?username=filteruser&role=Sales&is_locked=false&auth_provider=local&skip=0&limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    users = response.json()
    assert any(u["username"] == username for u in users)


@pytest.mark.slow
def test_unlock_disable_enable_user():
    token = get_admin_token()
    uid = random.randint(10000, 99999)
    username = f"stateuser{uid}"

    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "Password123",
            "role": "Sales",
        },
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]

    lock_resp = client.put(
        f"/api/v1/users/{user_id}",
        json={"is_locked": True, "failed_attempts": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["is_locked"] is True

    unlock_resp = client.post(
        f"/api/v1/users/{user_id}/unlock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["is_locked"] is False

    disable_resp = client.post(
        f"/api/v1/users/{user_id}/disable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["is_active"] is False

    enable_resp = client.post(
        f"/api/v1/users/{user_id}/enable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enable_resp.status_code == 200
    assert enable_resp.json()["is_active"] is True