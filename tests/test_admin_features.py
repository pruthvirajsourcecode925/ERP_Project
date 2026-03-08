from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal
from app.main import app
from app.models.role import Role
from app.models.user import User


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


def test_global_search():
    response = client.get(
        "/api/v1/search?q=test",
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert response.status_code == 200


def test_audit_log_access():
    response = client.get(
        "/api/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert response.status_code == 200


def test_dashboard_summary():
    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {get_admin_token()}"},
    )
    assert response.status_code == 200

    data = response.json()
    assert "total_customers" in data
    assert "total_suppliers" in data
    assert "active_production_jobs" in data
    assert "pending_dispatch" in data
    assert "open_ncr" in data