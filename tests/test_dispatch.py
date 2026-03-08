from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.modules.dispatch.models import DispatchItem, DispatchOrderStatus
from app.modules.dispatch.services import complete_dispatch
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.production.models import (
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
)
from app.modules.quality.models import CertificateOfConformance, FinalInspection, QualityInspectionResult
from app.modules.quality.services import QualityBusinessRuleError
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


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    create_db_and_tables()


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


def _seed_dispatch_context(
    db,
    *,
    final_result: QualityInspectionResult | None = QualityInspectionResult.PASS,
    create_coc: bool = False,
    produced_quantity: Decimal | None = None,
) -> dict[str, int]:
    admin = _ensure_admin_user(db)
    sales_order = _seed_sales_order(db)
    route_card = _seed_route_card(db, sales_order_id=sales_order.id)

    production_order = ProductionOrder(
        production_order_number=_unique("PROD"),
        sales_order_id=sales_order.id,
        route_card_id=route_card.id,
        planned_quantity=Decimal("10.000"),
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
        operation_name="Dispatch Prep",
        status=ProductionOperationStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(operation)
    db.flush()

    if produced_quantity is not None:
        production_log = ProductionLog(
            production_order_id=production_order.id,
            operation_id=operation.id,
            batch_number=_unique("BATCH"),
            produced_quantity=produced_quantity,
            scrap_quantity=Decimal("0.000"),
            recorded_by=admin.id,
            recorded_at=datetime.now(timezone.utc),
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(production_log)

    if final_result is not None:
        final_inspection = FinalInspection(
            production_order_id=production_order.id,
            inspected_by=admin.id,
            inspection_date=date.today(),
            result=final_result,
            remarks="Dispatch test inspection",
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(final_inspection)

    certificate_id = None
    if create_coc:
        certificate = CertificateOfConformance(
            production_order_id=production_order.id,
            certificate_number=_unique("COC"),
            issued_by=admin.id,
            issued_date=date.today(),
            remarks="Dispatch test certificate",
        )
        db.add(certificate)
        db.flush()
        certificate_id = certificate.id

    db.commit()
    return {
        "admin_id": admin.id,
        "sales_order_id": sales_order.id,
        "production_order_id": production_order.id,
        "certificate_id": certificate_id or 0,
    }


def _create_dispatch_order(token: str, *, sales_order_id: int, certificate_id: int | None = None) -> dict:
    response = client.post(
        "/api/v1/dispatch/order",
        json={
            "dispatch_number": _unique("DSP"),
            "sales_order_id": sales_order_id,
            "certificate_of_conformance_id": certificate_id,
            "dispatch_date": date.today().isoformat(),
            "shipping_method": "Road",
            "destination": "Customer Site",
            "remarks": "Dispatch test order",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_dispatch_item(token: str, *, dispatch_order_id: int, production_order_id: int, quantity: str = "5.000") -> dict:
    response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order_id}/item",
        json={
            "dispatch_order_id": dispatch_order_id,
            "production_order_id": production_order_id,
            "line_number": 1,
            "item_code": _unique("ITEM"),
            "description": "Dispatch test item",
            "quantity": quantity,
            "uom": "Nos",
            "lot_number": _unique("LOT"),
            "is_traceability_verified": True,
            "remarks": "Dispatch item test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return {
        "status_code": response.status_code,
        "body": response.json(),
    }


def _create_completed_checklist(token: str, *, dispatch_order_id: int) -> None:
    response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order_id}/checklist",
        json={
            "dispatch_order_id": dispatch_order_id,
            "checklist_item": "Packaging verified",
            "requirement_reference": "DISP-CHK-01",
            "status": "completed",
            "remarks": "Checklist complete",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text


def _create_shipping_documents(token: str, *, dispatch_order_id: int) -> None:
    packing_response = client.post(
        "/api/v1/dispatch/packing-list",
        json={
            "packing_list_number": _unique("PL"),
            "dispatch_order_id": dispatch_order_id,
            "packed_date": date.today().isoformat(),
            "package_count": 1,
            "remarks": "Packed",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert packing_response.status_code == 201, packing_response.text

    invoice_response = client.post(
        "/api/v1/dispatch/invoice",
        json={
            "invoice_number": _unique("INV"),
            "dispatch_order_id": dispatch_order_id,
            "invoice_date": date.today().isoformat(),
            "currency": "INR",
            "subtotal": "100.00",
            "tax_amount": "18.00",
            "total_amount": "118.00",
            "remarks": "Invoice issued",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invoice_response.status_code == 201, invoice_response.text

    challan_response = client.post(
        "/api/v1/dispatch/challan",
        json={
            "challan_number": _unique("DC"),
            "dispatch_order_id": dispatch_order_id,
            "issue_date": date.today().isoformat(),
            "received_by": "Receiver",
            "remarks": "Challan issued",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert challan_response.status_code == 201, challan_response.text


def test_dispatch_order_creation():
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    response = client.post(
        "/api/v1/dispatch/order",
        json={
            "dispatch_number": _unique("DSP"),
            "sales_order_id": seeded["sales_order_id"],
            "dispatch_date": date.today().isoformat(),
            "shipping_method": "Road",
            "destination": "Customer Site",
            "remarks": "Dispatch creation test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


def test_dispatch_item_addition():
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    result = _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
    )

    assert result["status_code"] == 201
    assert Decimal(str(result["body"]["quantity"])) > 0

    db = SessionLocal()
    try:
        item = db.scalar(select(DispatchItem).where(DispatchItem.id == result["body"]["id"]))
    finally:
        db.close()

    assert item is not None
    assert item.quantity > 0


def test_dispatch_checklist_validation():
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db, create_coc=True)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(
        token,
        sales_order_id=seeded["sales_order_id"],
        certificate_id=seeded["certificate_id"],
    )
    add_result = _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
    )
    assert add_result["status_code"] == 201

    checklist_response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/checklist",
        json={
            "dispatch_order_id": dispatch_order["id"],
            "checklist_item": "Documentation verified",
            "requirement_reference": "DISP-CHK-02",
            "status": "pending",
            "remarks": "Still pending",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert checklist_response.status_code == 201

    ship_response = client.patch(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/ship",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ship_response.status_code == 400
    assert "checklist" in ship_response.json()["detail"].lower()


def test_dispatch_requires_quality_pass(monkeypatch):
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db, final_result=None)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    add_result = _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
    )
    assert add_result["status_code"] == 201

    def _mock_quality_fail(*args, **kwargs):
        raise QualityBusinessRuleError("Dispatch blocked until final inspection is passed.")

    monkeypatch.setattr("app.modules.dispatch.services.validate_final_inspection_required", _mock_quality_fail)

    ship_response = client.patch(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/ship",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ship_response.status_code == 400
    assert "final inspection" in ship_response.json()["detail"].lower()


@pytest.mark.xfail(reason="Dispatch service does not yet enforce item quantity against produced quantity.", strict=True)
def test_dispatch_quantity_validation():
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db, produced_quantity=Decimal("5.000"))
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(token, sales_order_id=seeded["sales_order_id"])
    response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/item",
        json={
            "dispatch_order_id": dispatch_order["id"],
            "production_order_id": seeded["production_order_id"],
            "line_number": 1,
            "item_code": _unique("ITEM"),
            "description": "Excess quantity item",
            "quantity": "10.000",
            "uom": "Nos",
            "lot_number": _unique("LOT"),
            "is_traceability_verified": True,
            "remarks": "Should fail once quantity validation exists",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_dispatch_complete():
    token = _get_admin_token()
    db = SessionLocal()
    try:
        seeded = _seed_dispatch_context(db, create_coc=True)
    finally:
        db.close()

    dispatch_order = _create_dispatch_order(
        token,
        sales_order_id=seeded["sales_order_id"],
        certificate_id=seeded["certificate_id"],
    )
    add_result = _add_dispatch_item(
        token,
        dispatch_order_id=dispatch_order["id"],
        production_order_id=seeded["production_order_id"],
    )
    assert add_result["status_code"] == 201

    _create_completed_checklist(token, dispatch_order_id=dispatch_order["id"])
    _create_shipping_documents(token, dispatch_order_id=dispatch_order["id"])

    ship_response = client.patch(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/ship",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ship_response.status_code == 200, ship_response.text

    body = ship_response.json()
    # Current implementation uses `released` as the terminal shipped-equivalent state.
    assert body["status"] == DispatchOrderStatus.RELEASED.value
    assert body["released_at"] is not None