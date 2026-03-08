from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.maintenance.models import (
    BreakdownReport,
    MaintenanceMachine,
    MachineStatus as MaintenanceMachineStatus,
    MaintenanceWorkOrder,
)
from app.modules.production.models import (
    Machine as ProductionMachine,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
)
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
from app.services.production_service import ProductionBusinessRuleError, start_operation


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    create_db_and_tables()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _ensure_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role

    role = Role(name=name, description=f"{name} role", is_active=True)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _get_token_for_role(role_name: str) -> str:
    db = SessionLocal()
    try:
        role = _ensure_role(db, role_name)
        uid = uuid4().hex[:10]
        username = f"{role_name.lower()}_{uid}"
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


def _create_machine(token: str) -> dict:
    payload = {
        "machine_code": _unique("MCH"),
        "machine_name": "CNC Alpha",
        "work_center": "WC-10",
        "location": "Bay-A",
        "manufacturer": "OEM",
        "model": "X1",
        "serial_number": _unique("SN"),
        "status": "Active",
    }
    response = client.post(
        "/api/v1/maintenance/machine",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_released_operation_for_machine(machine_id: int) -> int:
    db = SessionLocal()
    try:
        code = uuid4().hex[:8].upper()
        actor_role = _ensure_role(db, "Production")

        actor = User(
            username=f"prod_actor_{code.lower()}",
            email=f"prod_actor_{code.lower()}@example.com",
            password_hash="test-hash",
            role_id=actor_role.id,
            auth_provider="local",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            is_deleted=False,
        )
        db.add(actor)
        db.flush()

        customer = Customer(
            customer_code=f"CUST{code}",
            name=f"Customer {code}",
            email=f"customer.{code.lower()}@example.com",
            is_active=True,
        )
        db.add(customer)
        db.flush()

        enquiry = Enquiry(
            enquiry_number=f"ENQ{code}",
            customer_id=customer.id,
            enquiry_date=date.today(),
            currency="INR",
            status=EnquiryStatus.DRAFT,
        )
        db.add(enquiry)
        db.flush()

        contract_review = ContractReview(
            document_number=f"CR-{date.today().year}-{code}",
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
            document_number=f"QT-{date.today().year}-{code}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_number=f"QTN{code}",
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
            document_number=f"POA-{date.today().year}-{code}",
            revision=0,
            generated_at=datetime.now(timezone.utc),
            quotation_id=quotation.id,
            customer_po_number=f"PO{code}",
            customer_po_date=date.today(),
            accepted=True,
            status=CustomerPOReviewStatus.ACCEPTED,
        )
        db.add(po_review)
        db.flush()

        sales_order = SalesOrder(
            sales_order_number=f"SO{code}",
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
        db.flush()

        drawing = Drawing(
            drawing_number=f"DRW-{code}",
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
            route_number=f"RC-{code}",
            drawing_revision_id=drawing_revision.id,
            sales_order_id=sales_order.id,
            status=RouteCardStatus.RELEASED,
            released_date=datetime.now(timezone.utc),
            route_card_file_name=f"route_{code.lower()}.pdf",
            route_card_file_path=f"/tmp/route_{code.lower()}.pdf",
            route_card_file_uploaded_at=datetime.now(timezone.utc),
            route_card_file_content_type="application/pdf",
        )
        db.add(route_card)
        db.flush()

        production_machine = ProductionMachine(
            machine_code=f"PM-{code}",
            machine_name=f"Prod Machine {code}",
            work_center="WC-PROD",
            is_active=True,
        )
        db.add(production_machine)
        db.flush()

        production_order = ProductionOrder(
            production_order_number=f"PROD-{code}",
            sales_order_id=sales_order.id,
            route_card_id=route_card.id,
            planned_quantity=Decimal("10.000"),
            status=ProductionOrderStatus.RELEASED,
            start_date=date.today(),
            due_date=date.today(),
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(production_order)
        db.flush()

        operation = ProductionOperation(
            production_order_id=production_order.id,
            operation_number=10,
            operation_name="Turning",
            machine_id=production_machine.id,
            status=ProductionOperationStatus.PENDING,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(operation)
        db.flush()

        # Force ID alignment so production validation checks the same machine ID in maintenance module.
        maintenance_machine = MaintenanceMachine(
            id=production_machine.id,
            machine_code=f"MM-{code}",
            machine_name=f"Maint Machine {code}",
            work_center="WC-MAINT",
            status=MaintenanceMachineStatus.UNDER_MAINTENANCE,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(maintenance_machine)
        db.commit()

        return operation.id
    finally:
        db.close()


def test_machine_creation() -> None:
    token = _get_token_for_role("Admin")
    machine = _create_machine(token)
    assert machine["machine_code"].startswith("MCH-")
    assert machine["status"] == "Active"


def test_preventive_maintenance_scheduling() -> None:
    token = _get_token_for_role("Maintenance")
    machine = _create_machine(token)

    payload = {
        "machine_id": machine["id"],
        "plan_code": _unique("PM-PLAN"),
        "frequency_type": "Weekly",
        "frequency_days": 7,
        "checklist_template": "Lubrication + calibration",
        "next_due_date": (date.today() + timedelta(days=7)).isoformat(),
        "is_active": True,
    }
    response = client.post(
        "/api/v1/maintenance/preventive-plan",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["machine_id"] == machine["id"]
    assert body["frequency_type"] == "Weekly"
    assert body["next_due_date"] is not None


def test_breakdown_report_creation_and_auto_work_order_generation() -> None:
    token = _get_token_for_role("Maintenance")
    machine = _create_machine(token)

    payload = {
        "machine_id": machine["id"],
        "breakdown_number": _unique("BD"),
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "symptom_description": "Spindle vibration detected",
        "probable_cause": "Bearing wear",
        "severity": "Major",
        "status": "Open",
    }
    response = client.post(
        "/api/v1/maintenance/breakdown",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    breakdown = response.json()

    db = SessionLocal()
    try:
        db_breakdown = db.scalar(select(BreakdownReport).where(BreakdownReport.id == breakdown["id"]))
        auto_work_order = db.scalar(
            select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.breakdown_id == breakdown["id"])
        )
    finally:
        db.close()

    assert db_breakdown is not None
    assert auto_work_order is not None
    assert auto_work_order.machine_id == machine["id"]


def test_work_order_generation() -> None:
    token = _get_token_for_role("Maintenance")
    machine = _create_machine(token)

    breakdown_payload = {
        "machine_id": machine["id"],
        "breakdown_number": _unique("BD"),
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "symptom_description": "Hydraulic pressure drop",
        "probable_cause": "Valve leakage",
        "severity": "Minor",
        "status": "Open",
    }
    breakdown_response = client.post(
        "/api/v1/maintenance/breakdown",
        json=breakdown_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert breakdown_response.status_code == 201, breakdown_response.text
    breakdown = breakdown_response.json()

    wo_payload = {
        "work_order_number": _unique("WO"),
        "breakdown_id": breakdown["id"],
        "machine_id": machine["id"],
        "status": "Created",
    }
    wo_response = client.post(
        "/api/v1/maintenance/work-order",
        json=wo_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert wo_response.status_code == 201, wo_response.text
    work_order = wo_response.json()
    assert work_order["breakdown_id"] == breakdown["id"]
    assert work_order["machine_id"] == machine["id"]


def test_downtime_logging() -> None:
    token = _get_token_for_role("Maintenance")
    machine = _create_machine(token)
    start_at = datetime.now(timezone.utc).replace(microsecond=0)
    end_at = start_at + timedelta(minutes=30)

    payload = {
        "machine_id": machine["id"],
        "source_type": "Breakdown",
        "source_id": 1,
        "downtime_start_at": start_at.isoformat(),
        "downtime_end_at": end_at.isoformat(),
        "is_planned": False,
        "reason_code": "BDN",
        "remarks": "Unexpected stop",
    }
    response = client.post(
        "/api/v1/maintenance/downtime",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["machine_id"] == machine["id"]
    assert body["duration_minutes"] == 30


def test_machine_status_validation_blocks_production_operation_start() -> None:
    operation_id = _seed_released_operation_for_machine(machine_id=0)

    db = SessionLocal()
    try:
        with pytest.raises(ProductionBusinessRuleError, match="UnderMaintenance"):
            start_operation(db, production_operation_id=operation_id, started_by=None)
    finally:
        db.close()


def test_admin_access_allowed() -> None:
    token = _get_token_for_role("Admin")
    response = client.get(
        "/api/v1/maintenance/machine",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_maintenance_access_allowed() -> None:
    token = _get_token_for_role("Maintenance")
    response = client.get(
        "/api/v1/maintenance/machine",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_production_write_access_blocked() -> None:
    token = _get_token_for_role("Production")
    payload = {
        "machine_code": _unique("MCH"),
        "machine_name": "Prod User Attempt",
        "work_center": "WC-XX",
        "status": "Active",
    }
    response = client.post(
        "/api/v1/maintenance/machine",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_traceability_machine_history_links_to_maintenance_logs() -> None:
    token = _get_token_for_role("Maintenance")
    machine = _create_machine(token)

    breakdown_payload = {
        "machine_id": machine["id"],
        "breakdown_number": _unique("BD"),
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "symptom_description": "Auto traceability check",
        "severity": "Major",
        "status": "Open",
    }
    breakdown_response = client.post(
        "/api/v1/maintenance/breakdown",
        json=breakdown_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert breakdown_response.status_code == 201, breakdown_response.text
    breakdown = breakdown_response.json()

    now = datetime.now(timezone.utc).replace(microsecond=0)
    downtime_payload = {
        "machine_id": machine["id"],
        "source_type": "Breakdown",
        "source_id": breakdown["id"],
        "downtime_start_at": now.isoformat(),
        "downtime_end_at": (now + timedelta(minutes=15)).isoformat(),
        "is_planned": False,
    }
    downtime_response = client.post(
        "/api/v1/maintenance/downtime",
        json=downtime_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert downtime_response.status_code == 201, downtime_response.text
    downtime = downtime_response.json()

    history_response = client.get(
        f"/api/v1/maintenance/history/{machine['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_response.status_code == 200, history_response.text
    history_body = history_response.json()

    assert history_body["machine_id"] == machine["id"]
    assert any(item["id"] == breakdown["id"] for item in history_body["breakdowns"])
    assert any(item["id"] == downtime["id"] for item in history_body["downtimes"])
    assert all(item["machine_id"] == machine["id"] for item in history_body["history"])
