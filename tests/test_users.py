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


def create_user_as_admin(*, username: str, email: str, password: str, role: str, auth_provider: str = "local") -> dict:
    response = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": email,
            "password": password,
            "role": role,
            "auth_provider": auth_provider,
        },
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_user():
    """Test creating a new user with role name."""
    uid = random.randint(10000, 99999)
    data = create_user_as_admin(
        username=f"testuser{uid}",
        email=f"test{uid}@example.com",
        password="Password123",
        role="Sales",
    )
    assert data["username"] == f"testuser{uid}"
    assert data["email"] == f"test{uid}@example.com"
    assert "id" in data


def test_anonymous_user_creation_is_blocked():
    uid = random.randint(10000, 99999)
    response = client.post(
        "/api/v1/users/",
        json={
            "username": f"anonuser{uid}",
            "email": f"anonuser{uid}@example.com",
            "password": "Password123",
            "role": "Sales",
        },
    )
    assert response.status_code == 401


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
    user_id = create_user_as_admin(
        username=f"pwduser{uid}",
        email=f"pwduser{uid}@example.com",
        password="Old@12345",
        role="Sales",
    )["id"]

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
    user_id = create_user_as_admin(
        username=f"deluser{uid}",
        email=f"deluser{uid}@example.com",
        password="Password123",
        role="Sales",
    )["id"]

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
        headers={"Authorization": f"Bearer {get_admin_token()}"},
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
        headers={"Authorization": f"Bearer {token}"},
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
        headers={"Authorization": f"Bearer {token}"},
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


@pytest.mark.slow
def test_non_admin_cannot_self_promote_or_update_other_users():
    uid = random.randint(10000, 99999)
    user_one = create_user_as_admin(
        username=f"selfrole{uid}",
        email=f"selfrole{uid}@example.com",
        password="Password123",
        role="Sales",
    )
    user_two = create_user_as_admin(
        username=f"otherrole{uid}",
        email=f"otherrole{uid}@example.com",
        password="Password123",
        role="Sales",
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": user_one["username"], "password": "Password123"},
    )
    assert login_resp.status_code == 200
    user_token = login_resp.json()["access_token"]

    db = SessionLocal()
    try:
        admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
        assert admin_role is not None
        promote_resp = client.put(
            f"/api/v1/users/{user_one['id']}",
            json={"role_id": admin_role.id},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert promote_resp.status_code == 403

        other_read_resp = client.get(
            f"/api/v1/users/{user_two['id']}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert other_read_resp.status_code == 403

        other_update_resp = client.put(
            f"/api/v1/users/{user_two['id']}",
            json={"email": f"changed{uid}@example.com"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert other_update_resp.status_code == 403

        admin_only_resp = client.get(
            "/api/v1/roles/",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert admin_only_resp.status_code == 403
    finally:
        db.close()


@pytest.mark.slow
def test_deactivated_role_loses_access():
    admin_token = get_admin_token()
    role_name = f"DeactivatedRole{random.randint(1000, 9999)}"

    create_role_resp = client.post(
        "/api/v1/roles/",
        json={"name": role_name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_role_resp.status_code == 201
    role_id = create_role_resp.json()["id"]

    assign_resp = client.put(
        f"/api/v1/roles/{role_id}/modules",
        json={"modules": ["sales"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert assign_resp.status_code == 200

    uid = random.randint(10000, 99999)
    create_user_resp = client.post(
        "/api/v1/users/",
        json={
            "username": f"deactuser{uid}",
            "email": f"deactuser{uid}@example.com",
            "password": "Password123",
            "role_id": role_id,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_user_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": f"deactuser{uid}", "password": "Password123"},
    )
    assert login_resp.status_code == 200
    user_token = login_resp.json()["access_token"]

    before_resp = client.get(
        "/api/v1/sales/quotation-terms",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert before_resp.status_code == 200

    deactivate_resp = client.delete(
        f"/api/v1/roles/{role_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_resp.status_code == 204

    after_resp = client.get(
        "/api/v1/sales/quotation-terms",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert after_resp.status_code == 401
