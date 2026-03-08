from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.production.models import ProductionOperation, ProductionOperationStatus, ProductionOrder, ProductionOrderStatus
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


def _ensure_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role

    role = Role(name=name, description=f"{name} role", is_active=True)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _ensure_admin_user(db) -> User:
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
    return admin


def _get_admin_token() -> str:
    db = SessionLocal()
    try:
        admin = _ensure_admin_user(db)
        return create_access_token(str(admin.id))
    finally:
        db.close()


def _seed_sales_order(db) -> SalesOrder:
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
    return sales_order


def _seed_route_card(db, *, sales_order_id: int) -> RouteCard:
    code = uuid4().hex[:10].upper()

    drawing = Drawing(
        drawing_number=f"DRW-{code[:8]}",
        part_name=f"Part {code}",
        is_active=True,
    )
    db.add(drawing)
    db.flush()

    drawing_revision = DrawingRevision(
        drawing_id=drawing.id,
        revision_code="A",
        revision_date=date.today(),
        file_path=f"/tmp/{code.lower()}.pdf",
        is_current=True,
    )
    db.add(drawing_revision)
    db.flush()

    route_card = RouteCard(
        route_number=f"RC-{code[:8]}",
        drawing_revision_id=drawing_revision.id,
        sales_order_id=sales_order_id,
        status=RouteCardStatus.RELEASED,
        released_date=datetime.now(timezone.utc),
        route_card_file_name=f"route_{code.lower()}.pdf",
        route_card_file_path=f"/tmp/route_{code.lower()}.pdf",
        route_card_file_uploaded_at=datetime.now(timezone.utc),
        route_card_file_content_type="application/pdf",
    )
    db.add(route_card)
    db.commit()
    db.refresh(route_card)
    return route_card


def _seed_dispatch_context(db) -> dict[str, int]:
    admin = _ensure_admin_user(db)
    sales_order = _seed_sales_order(db)
    route_card = _seed_route_card(db, sales_order_id=sales_order.id)

    production_order = ProductionOrder(
        production_order_number=_unique("PROD"),
        sales_order_id=sales_order.id,
        route_card_id=route_card.id,
        planned_quantity=Decimal("25.000"),
        status=ProductionOrderStatus.RELEASED,
        start_date=date.today(),
        due_date=date.today(),
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(production_order)
    db.flush()

    operation = ProductionOperation(
        production_order_id=production_order.id,
        operation_number=10,
        operation_name="Dispatch PDF Prep",
        status=ProductionOperationStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(operation)
    db.commit()

    return {
        "sales_order_id": sales_order.id,
        "production_order_id": production_order.id,
    }


def _create_dispatch_order(token: str, *, sales_order_id: int) -> dict:
    response = client.post(
        "/api/v1/dispatch/order",
        json={
            "dispatch_number": _unique("DSP"),
            "sales_order_id": sales_order_id,
            "dispatch_date": date.today().isoformat(),
            "shipping_method": "Road",
            "destination": "Customer Site",
            "remarks": "Dispatch pdf test order",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_dispatch_item(
    token: str,
    *,
    dispatch_order_id: int,
    production_order_id: int,
    line_number: int,
    quantity: str,
) -> dict:
    response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order_id}/item",
        json={
            "dispatch_order_id": dispatch_order_id,
            "production_order_id": production_order_id,
            "line_number": line_number,
            "item_code": _unique("ITEM"),
            "description": f"Dispatch pdf item {line_number}",
            "quantity": quantity,
            "uom": "Nos",
            "lot_number": _unique("LOT"),
            "is_traceability_verified": True,
            "remarks": "Dispatch pdf item",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_invoice(
    token: str,
    *,
    dispatch_order_id: int,
    subtotal: str,
    tax_amount: str,
    total_amount: str,
) -> dict:
    response = client.post(
        "/api/v1/dispatch/invoice",
        json={
            "invoice_number": _unique("INV"),
            "dispatch_order_id": dispatch_order_id,
            "invoice_date": date.today().isoformat(),
            "currency": "INR",
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "remarks": "Dispatch invoice for pdf tests",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_challan(token: str, *, dispatch_order_id: int) -> dict:
    response = client.post(
        "/api/v1/dispatch/challan",
        json={
            "challan_number": _unique("DC"),
            "dispatch_order_id": dispatch_order_id,
            "issue_date": date.today().isoformat(),
            "received_by": "Receiver",
            "remarks": "Dispatch challan for pdf tests",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assert_pdf_response(response) -> None:
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_invoice_pdf_generation():
    create_db_and_tables()
    token = _get_admin_token()

    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
        line_number=1,
        quantity="5.000",
    )
    _create_invoice(
        token,
        dispatch_order_id=dispatch_order["id"],
        subtotal="100.00",
        tax_amount="18.00",
        total_amount="118.00",
    )

    response = client.get(
        f"/api/v1/dispatch/report/invoice/{dispatch_order['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_pdf_response(response)


def test_challan_pdf_generation():
    create_db_and_tables()
    token = _get_admin_token()

    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
        line_number=1,
        quantity="5.000",
    )
    challan = _create_challan(token, dispatch_order_id=dispatch_order["id"])

    response = client.get(
        f"/api/v1/dispatch/report/challan/{dispatch_order['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_pdf_response(response)

    content_disposition = response.headers.get("content-disposition", "")
    assert challan["challan_number"] in content_disposition


def test_dynamic_rows():
    create_db_and_tables()
    token = _get_admin_token()

    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    _add_dispatch_item(token, dispatch_order_id=dispatch_order["id"], production_order_id=seeded["production_order_id"], line_number=1, quantity="2.000")
    _add_dispatch_item(token, dispatch_order_id=dispatch_order["id"], production_order_id=seeded["production_order_id"], line_number=2, quantity="3.000")
    _add_dispatch_item(token, dispatch_order_id=dispatch_order["id"], production_order_id=seeded["production_order_id"], line_number=3, quantity="4.000")
    _create_invoice(
        token,
        dispatch_order_id=dispatch_order["id"],
        subtotal="180.00",
        tax_amount="18.00",
        total_amount="198.00",
    )

    response = client.get(
        f"/api/v1/dispatch/report/invoice/{dispatch_order['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_pdf_response(response)


def test_optional_gst():
    create_db_and_tables()
    token = _get_admin_token()

    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
        line_number=1,
        quantity="5.000",
    )
    _create_invoice(
        token,
        dispatch_order_id=dispatch_order["id"],
        subtotal="100.00",
        tax_amount="0.00",
        total_amount="100.00",
    )

    response = client.get(
        f"/api/v1/dispatch/report/invoice/{dispatch_order['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_pdf_response(response)


def test_optional_amount_challan():
    create_db_and_tables()
    token = _get_admin_token()

    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
        line_number=1,
        quantity="5.000",
    )
    _create_challan(token, dispatch_order_id=dispatch_order["id"])

    response = client.get(
        f"/api/v1/dispatch/report/challan/{dispatch_order['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_pdf_response(response)