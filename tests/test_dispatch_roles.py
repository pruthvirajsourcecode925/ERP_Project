from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.main import app
from app.models.role import Role, RoleModuleAccess
from app.models.user import User
from app.modules.sales.models import (
    ContractReview,
    ContractReviewStatus,
    Customer,
    CustomerPOReview,
    CustomerPOReviewStatus,
    Enquiry,
    EnquiryStatus,
    Quotation,
    QuotationStatus,
    SalesOrder,
    SalesOrderStatus,
)


client = TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _ensure_schema() -> None:
    create_db_and_tables()


def _ensure_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role

    role = Role(name=name, description=f"{name} role", is_active=True)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _set_role_modules(db, *, role_id: int, module_keys: list[str]) -> None:
    existing = db.scalars(select(RoleModuleAccess).where(RoleModuleAccess.role_id == role_id)).all()
    for access in existing:
        db.delete(access)
    db.flush()

    for module_key in module_keys:
        db.add(RoleModuleAccess(role_id=role_id, module_key=module_key))


def _create_user_token(role_name: str, *, module_keys: list[str] | None = None, username_prefix: str | None = None) -> str:
    db = SessionLocal()
    try:
        role = _ensure_role(db, role_name)
        if module_keys is not None:
            _set_role_modules(db, role_id=role.id, module_keys=module_keys)

        seed = uuid4().hex[:10]
        username = f"{(username_prefix or role_name.lower())}_{seed}"
        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=get_password_hash("Password@123"),
            role_id=role.id,
            auth_provider="local",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            is_deleted=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token(str(user.id))
    finally:
        db.close()


def _get_admin_token() -> str:
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


def _seed_sales_order() -> int:
    db = SessionLocal()
    try:
        code = uuid4().hex[:10].upper()

        customer = Customer(
            customer_code=f"CUST{code[:8]}",
            name=f"Customer {code}",
            email=f"customer.{code.lower()}@example.com",
            is_active=True,
        )
        db.add(customer)
        db.flush()

        enquiry = Enquiry(
            enquiry_number=f"ENQ{code[:8]}",
            customer_id=customer.id,
            enquiry_date=date.today(),
            currency="INR",
            status=EnquiryStatus.DRAFT,
        )
        db.add(enquiry)
        db.flush()

        contract_review = ContractReview(
            document_number=f"CR-{date.today().year}-{code[:8]}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            enquiry_id=enquiry.id,
            status=ContractReviewStatus.APPROVED,
            scope_clarity_ok=True,
            capability_ok=True,
            capacity_ok=True,
            delivery_commitment_ok=True,
            quality_requirements_ok=True,
        )
        db.add(contract_review)
        db.flush()

        quotation = Quotation(
            document_number=f"QT-{date.today().year}-{code[:8]}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_number=f"QTN{code[:8]}",
            enquiry_id=enquiry.id,
            contract_review_id=contract_review.id,
            customer_id=customer.id,
            issue_date=date.today(),
            valid_until=date.today(),
            currency="INR",
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("18.00"),
            total_amount=Decimal("118.00"),
            status=QuotationStatus.DRAFT,
        )
        db.add(quotation)
        db.flush()

        po_review = CustomerPOReview(
            document_number=f"POA-{date.today().year}-{code[:8]}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_id=quotation.id,
            customer_po_number=f"PO{code[:8]}",
            customer_po_date=date.today(),
            accepted=True,
            status=CustomerPOReviewStatus.ACCEPTED,
        )
        db.add(po_review)
        db.flush()

        sales_order = SalesOrder(
            sales_order_number=f"SO{code[:8]}",
            customer_id=customer.id,
            enquiry_id=enquiry.id,
            contract_review_id=contract_review.id,
            quotation_id=quotation.id,
            customer_po_review_id=po_review.id,
            order_date=date.today(),
            currency="INR",
            total_amount=Decimal("118.00"),
            status=SalesOrderStatus.RELEASED,
        )
        db.add(sales_order)
        db.commit()
        db.refresh(sales_order)
        return sales_order.id
    finally:
        db.close()


def _dispatch_create_payload(*, sales_order_id: int) -> dict:
    return {
        "dispatch_number": _unique("DSP"),
        "sales_order_id": sales_order_id,
        "dispatch_date": date.today().isoformat(),
        "shipping_method": "Road",
        "destination": "Customer Site",
        "remarks": "Dispatch role validation test",
    }


def test_admin_can_dispatch():
    _ensure_schema()
    sales_order_id = _seed_sales_order()

    response = client.post(
        "/api/v1/dispatch/order",
        json=_dispatch_create_payload(sales_order_id=sales_order_id),
        headers={"Authorization": f"Bearer {_get_admin_token()}"},
    )
    assert response.status_code == 201


def test_dispatch_role_can_create_dispatch():
    _ensure_schema()
    sales_order_id = _seed_sales_order()
    token = _create_user_token("Dispatch", module_keys=["dispatch"])

    response = client.post(
        "/api/v1/dispatch/order",
        json=_dispatch_create_payload(sales_order_id=sales_order_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


def test_sales_role_cannot_dispatch():
    _ensure_schema()
    sales_order_id = _seed_sales_order()
    token = _create_user_token("Sales", module_keys=["sales"])

    response = client.post(
        "/api/v1/dispatch/order",
        json=_dispatch_create_payload(sales_order_id=sales_order_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_unauthorized_user_blocked():
    _ensure_schema()
    sales_order_id = _seed_sales_order()
    token = _create_user_token("Purchase", module_keys=["purchase"], username_prefix="unauthorized")

    response = client.post(
        "/api/v1/dispatch/order",
        json=_dispatch_create_payload(sales_order_id=sales_order_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_quality_role_can_create_dispatch():
    _ensure_schema()
    sales_order_id = _seed_sales_order()
    token = _create_user_token("Quality", module_keys=[])

    response = client.post(
        "/api/v1/dispatch/order",
        json=_dispatch_create_payload(sales_order_id=sales_order_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201