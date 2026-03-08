from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.main import app
from app.models.role import Role
from app.models.user import User


client = TestClient(app)

REQUEST_COUNT = 100
AVERAGE_RESPONSE_LIMIT_SECONDS = 1.0


def _ensure_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is not None:
        return role

    role = Role(name=name, description=f"{name} role", is_active=True)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _ensure_admin_token() -> str:
    db = SessionLocal()
    try:
        admin_role = _ensure_role(db, "Admin")
        admin = db.scalar(select(User).where(User.username == "admin"))
        if admin is None:
            admin = User(
                username="admin",
                email="admin@example.com",
                password_hash=get_password_hash("Admin@12345"),
                role_id=admin_role.id,
                auth_provider="both",
                is_active=True,
                is_locked=False,
                failed_attempts=0,
                is_deleted=False,
            )
        else:
            admin.password_hash = get_password_hash("Admin@12345")
            admin.role_id = admin_role.id
            admin.auth_provider = "both"
            admin.is_active = True
            admin.is_locked = False
            admin.failed_attempts = 0

        db.add(admin)
        db.commit()
        db.refresh(admin)
        return create_access_token(str(admin.id))
    finally:
        db.close()


def _request_duration(path: str, headers: dict[str, str]) -> float:
    started_at = perf_counter()
    response = client.get(path, headers=headers)
    elapsed = perf_counter() - started_at
    assert response.status_code == 200, response.text
    return elapsed


def _run_concurrent_gets(path: str) -> float:
    create_db_and_tables()
    headers = {"Authorization": f"Bearer {_ensure_admin_token()}"}

    with ThreadPoolExecutor(max_workers=20) as executor:
        durations = list(executor.map(lambda _: _request_duration(path, headers), range(REQUEST_COUNT)))

    average_duration = sum(durations) / len(durations)
    assert average_duration < AVERAGE_RESPONSE_LIMIT_SECONDS
    return average_duration


@pytest.mark.performance
def test_production_api_average_response_under_one_second():
    _run_concurrent_gets("/api/v1/production/order")


@pytest.mark.performance
def test_dispatch_api_average_response_under_one_second():
    _run_concurrent_gets("/api/v1/dispatch/order")


@pytest.mark.performance
def test_sales_api_average_response_under_one_second():
    _run_concurrent_gets("/api/v1/sales/quotation-terms")