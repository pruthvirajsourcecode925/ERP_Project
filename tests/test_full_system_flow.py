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
from app.modules.production.models import ProductionOperation, ProductionOperationStatus
from app.modules.quality.models import CertificateOfConformance
from app.modules.sales.models import Customer


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


def _create_customer(db) -> Customer:
    code = uuid4().hex[:10].upper()
    customer = Customer(
        customer_code=f"CUST{code[:8]}",
        name=f"Customer {code}",
        email=f"customer.{code.lower()}@example.com",
        phone="9999999999",
        billing_address="Aerospace Park, Bengaluru",
        shipping_address="Receiving Bay 1, Bengaluru",
        is_active=True,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _create_production_operation(db, *, production_order_id: int, created_by: int) -> ProductionOperation:
    operation = ProductionOperation(
        production_order_id=production_order_id,
        operation_number=10,
        operation_name="Turning",
        status=ProductionOperationStatus.PENDING,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


def _create_coc(db, *, production_order_id: int, issued_by: int) -> CertificateOfConformance:
    coc = CertificateOfConformance(
        production_order_id=production_order_id,
        certificate_number=_unique("COC"),
        issued_by=issued_by,
        issued_date=date.today(),
        remarks="Full system flow certificate",
    )
    db.add(coc)
    db.commit()
    db.refresh(coc)
    return coc


def test_full_system_flow():
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        admin = _ensure_admin_user(db)
        customer = _create_customer(db)
    finally:
        db.close()

    enquiry_response = client.post(
        "/api/v1/sales/enquiry",
        json={
            "enquiry_number": _unique("ENQ"),
            "customer_id": customer.id,
            "enquiry_date": date.today().isoformat(),
            "requested_delivery_date": date.today().isoformat(),
            "currency": "INR",
            "notes": "Full flow enquiry",
            "status": "draft",
        },
        headers=headers,
    )
    assert enquiry_response.status_code == 201, enquiry_response.text
    enquiry = enquiry_response.json()

    contract_review_response = client.post(
        "/api/v1/sales/contract-review",
        json={
            "enquiry_id": enquiry["id"],
            "status": "approved",
            "scope_clarity_ok": True,
            "capability_ok": True,
            "capacity_ok": True,
            "delivery_commitment_ok": True,
            "quality_requirements_ok": True,
            "review_comments": "Approved for end-to-end flow",
        },
        headers=headers,
    )
    assert contract_review_response.status_code == 201, contract_review_response.text
    contract_review = contract_review_response.json()

    quotation_response = client.post(
        "/api/v1/sales/quotation",
        json={
            "quotation_number": _unique("QTN"),
            "enquiry_id": enquiry["id"],
            "contract_review_id": contract_review["id"],
            "customer_id": customer.id,
            "issue_date": date.today().isoformat(),
            "valid_until": date.today().isoformat(),
            "currency": "INR",
            "subtotal": "100.00",
            "total_amount": "118.00",
            "status": "issued",
        },
        headers=headers,
    )
    assert quotation_response.status_code == 201, quotation_response.text
    quotation = quotation_response.json()

    po_review_response = client.post(
        "/api/v1/sales/customer-po-review",
        json={
            "quotation_id": quotation["id"],
            "customer_po_number": _unique("CPO"),
            "customer_po_date": date.today().isoformat(),
            "accepted": True,
            "status": "accepted",
            "deviation_notes": None,
        },
        headers=headers,
    )
    assert po_review_response.status_code == 201, po_review_response.text
    po_review = po_review_response.json()

    sales_order_response = client.post(
        "/api/v1/sales/sales-order",
        json={
            "sales_order_number": _unique("SO"),
            "customer_id": customer.id,
            "enquiry_id": enquiry["id"],
            "contract_review_id": contract_review["id"],
            "quotation_id": quotation["id"],
            "customer_po_review_id": po_review["id"],
            "order_date": date.today().isoformat(),
            "currency": "INR",
            "total_amount": "118.00",
            "status": "released",
        },
        headers=headers,
    )
    assert sales_order_response.status_code == 201, sales_order_response.text
    sales_order = sales_order_response.json()

    drawing_response = client.post(
        "/api/v1/engineering/drawing",
        json={
            "drawing_number": _unique("DRW"),
            "part_name": "Flow Test Part",
            "customer_id": customer.id,
            "description": "Full flow drawing",
            "is_active": True,
        },
        headers=headers,
    )
    assert drawing_response.status_code == 201, drawing_response.text
    drawing = drawing_response.json()

    revision_response = client.post(
        f"/api/v1/engineering/drawing/{drawing['id']}/revision",
        json={
            "revision_code": "A",
            "revision_date": date.today().isoformat(),
            "file_path": f"/tmp/{uuid4().hex}.pdf",
            "is_current": True,
        },
        headers=headers,
    )
    assert revision_response.status_code == 201, revision_response.text
    revision = revision_response.json()

    route_card_response = client.post(
        "/api/v1/engineering/route-card",
        data={
            "route_number": _unique("RC"),
            "drawing_revision_id": str(revision["id"]),
            "sales_order_id": str(sales_order["id"]),
        },
        files={"file": ("route-card.pdf", b"%PDF-1.4\n%route-card\n", "application/pdf")},
        headers=headers,
    )
    assert route_card_response.status_code == 201, route_card_response.text
    route_card = route_card_response.json()

    route_operation_response = client.post(
        f"/api/v1/engineering/route-card/{route_card['id']}/operation",
        json={
            "operation_number": 10,
            "operation_name": "Turning",
            "work_center": "CNC",
            "inspection_required": True,
            "sequence_order": 1,
        },
        headers=headers,
    )
    assert route_operation_response.status_code == 201, route_operation_response.text

    route_release_response = client.post(
        f"/api/v1/engineering/route-card/{route_card['id']}/release",
        headers=headers,
    )
    assert route_release_response.status_code == 200, route_release_response.text

    supplier_response = client.post(
        "/api/v1/purchase/supplier",
        json={
            "supplier_code": _unique("SUP"),
            "supplier_name": "Flow Supplier",
            "contact_person": "Supplier QA",
            "phone": "8888888888",
            "email": f"supplier.{uuid4().hex[:8]}@example.com",
            "address": "Industrial Estate",
            "is_approved": False,
            "is_active": True,
        },
        headers=headers,
    )
    assert supplier_response.status_code == 201, supplier_response.text
    supplier = supplier_response.json()

    supplier_approval_response = client.post(
        f"/api/v1/purchase/supplier/{supplier['id']}/approve",
        json={
            "approved": True,
            "approval_remarks": "Approved for end-to-end procurement",
            "quality_acknowledged": True,
        },
        headers=headers,
    )
    assert supplier_approval_response.status_code == 200, supplier_approval_response.text

    purchase_order_response = client.post(
        "/api/v1/purchase/order",
        json={
            "supplier_id": supplier["id"],
            "sales_order_id": sales_order["id"],
            "po_date": date.today().isoformat(),
            "expected_delivery_date": date.today().isoformat(),
            "remarks": "Flow purchase order",
            "quality_notes": "Material certs required",
            "supplier_quality_requirements": "CoC and traceability required",
        },
        headers=headers,
    )
    assert purchase_order_response.status_code == 201, purchase_order_response.text
    purchase_order = purchase_order_response.json()

    purchase_item_response = client.post(
        f"/api/v1/purchase/order/{purchase_order['id']}/item",
        json={
            "description": "Aluminium round bar",
            "quantity": "10.000",
            "unit_price": "5.00",
        },
        headers=headers,
    )
    assert purchase_item_response.status_code == 201, purchase_item_response.text

    purchase_issue_response = client.put(
        f"/api/v1/purchase/order/{purchase_order['id']}/status",
        json={"status": "issued"},
        headers=headers,
    )
    assert purchase_issue_response.status_code == 200, purchase_issue_response.text

    location_response = client.post(
        "/api/v1/stores/location",
        json={
            "location_code": _unique("LOC"),
            "location_name": "Incoming Stores",
            "description": "Flow receiving location",
            "is_active": True,
        },
        headers=headers,
    )
    assert location_response.status_code == 201, location_response.text
    location = location_response.json()

    grn_response = client.post(
        "/api/v1/stores/grn",
        json={
            "grn_number": _unique("GRN"),
            "purchase_order_id": purchase_order["id"],
            "supplier_id": supplier["id"],
            "storage_location_id": location["id"],
            "grn_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert grn_response.status_code == 201, grn_response.text
    grn = grn_response.json()

    grn_item_response = client.post(
        f"/api/v1/stores/grn/{grn['id']}/item",
        json={
            "item_code": "RM-AL-001",
            "description": "Aluminium round bar",
            "heat_number": "HT-001",
            "batch_number": _unique("BATCH"),
            "received_quantity": "10.000",
            "accepted_quantity": "10.000",
            "rejected_quantity": "0.000",
        },
        headers=headers,
    )
    assert grn_item_response.status_code == 201, grn_item_response.text
    grn_item = grn_item_response.json()

    stores_inspection_response = client.post(
        f"/api/v1/stores/grn/{grn_item['id']}/inspect",
        json={
            "inspection_date": date.today().isoformat(),
            "inspection_status": "Accepted",
            "remarks": "Material accepted",
            "storage_location_id": location["id"],
        },
        headers=headers,
    )
    assert stores_inspection_response.status_code == 200, stores_inspection_response.text

    production_order_response = client.post(
        "/api/v1/production/order",
        json={
            "production_order_number": _unique("PROD"),
            "sales_order_id": sales_order["id"],
            "route_card_id": route_card["id"],
            "planned_quantity": "10.000",
            "due_date": date.today().isoformat(),
            "start_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert production_order_response.status_code == 201, production_order_response.text
    production_order = production_order_response.json()

    production_release_response = client.patch(
        f"/api/v1/production/order/{production_order['id']}/release",
        headers=headers,
    )
    assert production_release_response.status_code == 200, production_release_response.text

    db = SessionLocal()
    try:
        production_operation = _create_production_operation(
            db,
            production_order_id=production_order["id"],
            created_by=admin.id,
        )
    finally:
        db.close()

    operation_start_response = client.post(
        f"/api/v1/production/operation/{production_operation.id}/start",
        headers=headers,
    )
    assert operation_start_response.status_code == 200, operation_start_response.text

    inprocess_inspection_response = client.post(
        f"/api/v1/production/operation/{production_operation.id}/inspection",
        json={
            "inspection_result": "Pass",
            "remarks": "In-process inspection passed",
            "inspection_time": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert inprocess_inspection_response.status_code == 201, inprocess_inspection_response.text

    production_log_response = client.post(
        "/api/v1/production/log",
        json={
            "production_order_id": production_order["id"],
            "operation_id": production_operation.id,
            "produced_quantity": "10.000",
            "scrap_quantity": "0.000",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert production_log_response.status_code == 201, production_log_response.text

    operation_complete_response = client.post(
        f"/api/v1/production/operation/{production_operation.id}/complete",
        headers=headers,
    )
    assert operation_complete_response.status_code == 200, operation_complete_response.text

    final_inspection_create_response = client.post(
        "/api/v1/quality/final-inspection",
        json={
            "production_order_id": production_order["id"],
            "remarks": "Final inspection for full flow",
        },
        headers=headers,
    )
    assert final_inspection_create_response.status_code == 201, final_inspection_create_response.text
    final_inspection = final_inspection_create_response.json()

    final_inspection_complete_response = client.patch(
        f"/api/v1/quality/final-inspection/{final_inspection['id']}/complete",
        json={"result": "Pass"},
        headers=headers,
    )
    assert final_inspection_complete_response.status_code == 200, final_inspection_complete_response.text

    db = SessionLocal()
    try:
        coc = _create_coc(db, production_order_id=production_order["id"], issued_by=admin.id)
    finally:
        db.close()
    assert coc.id > 0

    dispatch_order_response = client.post(
        "/api/v1/dispatch/order",
        json={
            "dispatch_number": _unique("DSP"),
            "sales_order_id": sales_order["id"],
            "certificate_of_conformance_id": coc.id,
            "dispatch_date": date.today().isoformat(),
            "shipping_method": "Road",
            "destination": "Customer Site",
            "remarks": "Dispatch for full flow",
        },
        headers=headers,
    )
    assert dispatch_order_response.status_code == 201, dispatch_order_response.text
    dispatch_order = dispatch_order_response.json()

    dispatch_item_response = client.post(
        f"/api/v1/dispatch/order/{dispatch_order['id']}/item",
        json={
            "dispatch_order_id": dispatch_order["id"],
            "production_order_id": production_order["id"],
            "line_number": 1,
            "item_code": "FG-001",
            "description": "Finished component",
            "quantity": "10.000",
            "uom": "Nos",
            "lot_number": _unique("LOT"),
            "is_traceability_verified": True,
            "remarks": "Ready to dispatch",
        },
        headers=headers,
    )
    assert dispatch_item_response.status_code == 201, dispatch_item_response.text

    invoice_response = client.post(
        "/api/v1/dispatch/invoice",
        json={
            "invoice_number": _unique("INV"),
            "dispatch_order_id": dispatch_order["id"],
            "invoice_date": date.today().isoformat(),
            "currency": "INR",
            "subtotal": "100.00",
            "tax_amount": "18.00",
            "total_amount": "118.00",
            "remarks": "Invoice for full flow",
        },
        headers=headers,
    )
    assert invoice_response.status_code == 201, invoice_response.text

    challan_response = client.post(
        "/api/v1/dispatch/challan",
        json={
            "challan_number": _unique("DC"),
            "dispatch_order_id": dispatch_order["id"],
            "issue_date": date.today().isoformat(),
            "received_by": "Stores Receiver",
            "remarks": "Challan for full flow",
        },
        headers=headers,
    )
    assert challan_response.status_code == 201, challan_response.text