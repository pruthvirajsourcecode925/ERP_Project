import random
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def get_admin_token() -> str:
    """Helper to get admin auth token."""
    uid = random.randint(10000, 99999)
    username = f"adminuser{uid}"
    password = "Admin@12345"
    create_resp = client.post(
        "/api/v1/users/",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "role": "Admin",
        },
    )
    assert create_resp.status_code == 200

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return resp.json()["access_token"]


def test_list_roles():
    """Test listing all roles (public endpoint)."""
    response = client.get("/api/v1/roles/")
    assert response.status_code == 200
    roles = response.json()
    assert isinstance(roles, list)
    assert len(roles) >= 1  # At least Admin role exists
    assert any(r["name"] == "Admin" for r in roles)


def test_get_role():
    """Test getting a single role by ID."""
    response = client.get("/api/v1/roles/1")
    assert response.status_code == 200
    role = response.json()
    assert "id" in role
    assert "name" in role


def test_get_role_not_found():
    """Test getting a non-existent role."""
    response = client.get("/api/v1/roles/99999")
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
    get_resp = client.get(f"/api/v1/roles/{role_id}")
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
