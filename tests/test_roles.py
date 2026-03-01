import random
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


def test_list_roles():
    """Test listing all roles (admin only)."""
    token = get_admin_token()
    response = client.get("/api/v1/roles/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    roles = response.json()
    assert isinstance(roles, list)
    assert len(roles) >= 1  # At least Admin role exists
    assert any(r["name"] == "Admin" for r in roles)


def test_get_role():
    """Test getting a single role by ID."""
    token = get_admin_token()
    response = client.get("/api/v1/roles/1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    role = response.json()
    assert "id" in role
    assert "name" in role


def test_get_role_not_found():
    """Test getting a non-existent role."""
    token = get_admin_token()
    response = client.get("/api/v1/roles/99999", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_create_role():
    """Test creating a new role (admin only)."""
    token = get_admin_token()
    role_name = f"TestRole{random.randint(1000, 9999)}"
    response = client.post(
        "/api/v1/roles/",
        json={"name": role_name, "description": "A test role"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == role_name
    assert data["description"] == "A test role"
    assert data["is_active"] is True


def test_create_role_duplicate():
    """Test creating a role with existing name fails."""
    token = get_admin_token()
    response = client.post(
        "/api/v1/roles/",
        json={"name": "Admin", "description": "duplicate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_update_role():
    """Test updating a role (admin only)."""
    token = get_admin_token()
    # First create a role to update
    role_name = f"UpdateRole{random.randint(1000, 9999)}"
    create_resp = client.post(
        "/api/v1/roles/",
        json={"name": role_name, "description": "original"},
        headers={"Authorization": f"Bearer {token}"},
    )
    role_id = create_resp.json()["id"]

    # Update it
    response = client.put(
        f"/api/v1/roles/{role_id}",
        json={"description": "updated description"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated description"


def test_deactivate_role():
    """Test deactivating a role (admin only)."""
    token = get_admin_token()
    # First create a role to deactivate
    role_name = f"DeactivateRole{random.randint(1000, 9999)}"
    create_resp = client.post(
        "/api/v1/roles/",
        json={"name": role_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    role_id = create_resp.json()["id"]

    # Deactivate it
    response = client.delete(
        f"/api/v1/roles/{role_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    # Verify it's deactivated
    get_resp = client.get(f"/api/v1/roles/{role_id}", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.json()["is_active"] is False


def test_cannot_deactivate_admin_role():
    """Test that Admin role cannot be deactivated."""
    token = get_admin_token()
    # Get Admin role ID (should be 1)
    response = client.delete(
        "/api/v1/roles/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Cannot deactivate Admin" in response.json()["detail"]
