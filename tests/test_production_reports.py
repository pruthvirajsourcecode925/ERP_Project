from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from app.modules.production.models import InspectionResult, Machine, ProductionOperation, ProductionOperationStatus
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
from app.services.production_service import (
    complete_operation,
    create_production_order,
    record_inprocess_inspection,
    record_production_log,
    release_production_order,
    start_operation,
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


def _create_user(db, *, prefix: str, role_name: str = "Production") -> User:
    role = _ensure_role(db, role_name)
    token = uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{token}",
        email=f"{prefix}.{token}@example.com",
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
    return user


def _get_admin_token() -> str:
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


def _create_machine(db, *, actor_id: int, prefix: str) -> Machine:
    machine = Machine(
        machine_code=_unique(f"{prefix}-MC"),
        machine_name=f"{prefix} Machine",
        work_center=f"{prefix}-WC",
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


def _create_production_job(
    db,
    *,
    actor: User,
    planned_quantity: Decimal = Decimal("20.000"),
    machine_ids: tuple[int | None, ...] = (None, None),
) -> tuple[object, list[ProductionOperation]]:
    sales_order = _seed_sales_order(db)
    route_card = _seed_route_card(db, sales_order_id=sales_order.id)

    production_order = create_production_order(
        db,
        production_order_number=_unique("PROD"),
        sales_order_id=sales_order.id,
        route_card_id=route_card.id,
        planned_quantity=planned_quantity,
        due_date=date.today(),
        created_by=actor.id,
    )
    production_order = release_production_order(
        db,
        production_order_id=production_order.id,
        released_by=actor.id,
    )

    operations: list[ProductionOperation] = []
    for idx, machine_id in enumerate(machine_ids, start=1):
        operation = ProductionOperation(
            production_order_id=production_order.id,
            operation_number=idx * 10,
            operation_name=f"Operation {idx * 10}",
            machine_id=machine_id,
            status=ProductionOperationStatus.PENDING,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(operation)
        operations.append(operation)

    db.commit()
    for operation in operations:
        db.refresh(operation)

    return production_order, operations


def _complete_operation_with_pass(db, *, operation_id: int, actor_id: int) -> None:
    start_operation(db, production_operation_id=operation_id, started_by=actor_id)
    record_inprocess_inspection(
        db,
        production_operation_id=operation_id,
        inspection_result=InspectionResult.PASS,
        inspected_by=actor_id,
        remarks="Passed inspection",
        created_by=actor_id,
    )
    complete_operation(db, production_operation_id=operation_id, completed_by=actor_id)


def _record_log(
    db,
    *,
    production_order_id: int,
    operation_id: int,
    batch_number: str,
    operator_user_id: int,
    machine_id: int,
    produced_quantity: str,
    scrap_quantity: str,
    recorded_by: int,
    recorded_at: datetime,
) -> None:
    record_production_log(
        db,
        production_order_id=production_order_id,
        operation_id=operation_id,
        batch_number=batch_number,
        operator_user_id=operator_user_id,
        machine_id=machine_id,
        produced_quantity=Decimal(produced_quantity),
        scrap_quantity=Decimal(scrap_quantity),
        recorded_by=recorded_by,
        created_by=recorded_by,
        recorded_at=recorded_at,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_admin_token()}"}


def setup_module() -> None:
    create_db_and_tables()


def test_batch_report_returns_correct_aggregation():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="report_actor")
        operator_one = _create_user(db, prefix="report_operator_one")
        operator_two = _create_user(db, prefix="report_operator_two")
        machine_one = _create_machine(db, actor_id=actor.id, prefix="BATCH-A")
        machine_two = _create_machine(db, actor_id=actor.id, prefix="BATCH-B")
        production_order, operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("30.000"),
            machine_ids=(machine_one.id, machine_two.id),
        )

        batch_number = _unique("BATCH")
        recorded_at = datetime.now(timezone.utc)
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[0].id,
            batch_number=batch_number,
            operator_user_id=operator_one.id,
            machine_id=machine_one.id,
            produced_quantity="5.000",
            scrap_quantity="1.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[1].id,
            batch_number=batch_number,
            operator_user_id=operator_two.id,
            machine_id=machine_two.id,
            produced_quantity="3.000",
            scrap_quantity="0.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )

        response = client.get(
            "/api/v1/production/report/batch",
            params={
                "batch_number": batch_number,
                "start_date": recorded_at.date().isoformat(),
                "end_date": recorded_at.date().isoformat(),
            },
            headers=_headers(),
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        report = payload[0]
        assert report["batch_number"] == batch_number
        assert Decimal(str(report["total_produced_quantity"])) == Decimal("8.000")
        assert Decimal(str(report["total_scrap_quantity"])) == Decimal("1.000")
        assert {machine["id"] for machine in report["machines_used"]} == {machine_one.id, machine_two.id}
        assert {operator["id"] for operator in report["operators_involved"]} == {operator_one.id, operator_two.id}
    finally:
        db.close()


def test_operator_report_returns_correct_job_mapping():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="operator_report_actor")
        operator = _create_user(db, prefix="operator_report_user")
        machine = _create_machine(db, actor_id=actor.id, prefix="OP-REP")
        recorded_at = datetime.now(timezone.utc)

        first_order, first_operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("15.000"),
            machine_ids=(machine.id,),
        )
        second_order, second_operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("15.000"),
            machine_ids=(machine.id,),
        )

        _complete_operation_with_pass(db, operation_id=first_operations[0].id, actor_id=actor.id)
        _complete_operation_with_pass(db, operation_id=second_operations[0].id, actor_id=actor.id)

        _record_log(
            db,
            production_order_id=first_order.id,
            operation_id=first_operations[0].id,
            batch_number=_unique("OP-B1"),
            operator_user_id=operator.id,
            machine_id=machine.id,
            produced_quantity="4.000",
            scrap_quantity="1.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )
        _record_log(
            db,
            production_order_id=second_order.id,
            operation_id=second_operations[0].id,
            batch_number=_unique("OP-B2"),
            operator_user_id=operator.id,
            machine_id=machine.id,
            produced_quantity="5.000",
            scrap_quantity="0.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )

        response = client.get(
            "/api/v1/production/report/operator",
            params={
                "operator_id": operator.id,
                "start_date": recorded_at.date().isoformat(),
                "end_date": recorded_at.date().isoformat(),
            },
            headers=_headers(),
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        report = payload[0]
        assert report["operator"]["id"] == operator.id
        assert report["jobs_worked"] == 2
        assert report["operations_completed"] == 2
        assert Decimal(str(report["total_quantity_produced"])) == Decimal("9.000")
        assert Decimal(str(report["total_scrap"])) == Decimal("1.000")
    finally:
        db.close()


def test_machine_report_aggregates_production_logs():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="machine_report_actor")
        operator_one = _create_user(db, prefix="machine_report_op1")
        operator_two = _create_user(db, prefix="machine_report_op2")
        machine = _create_machine(db, actor_id=actor.id, prefix="MACH-REP")
        production_order, operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("25.000"),
            machine_ids=(machine.id, machine.id),
        )
        recorded_at = datetime.now(timezone.utc)

        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[0].id,
            batch_number=_unique("MC-B1"),
            operator_user_id=operator_one.id,
            machine_id=machine.id,
            produced_quantity="6.000",
            scrap_quantity="1.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[1].id,
            batch_number=_unique("MC-B2"),
            operator_user_id=operator_two.id,
            machine_id=machine.id,
            produced_quantity="4.000",
            scrap_quantity="2.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )

        response = client.get(
            "/api/v1/production/report/machine",
            params={
                "machine_id": machine.id,
                "start_date": recorded_at.date().isoformat(),
                "end_date": recorded_at.date().isoformat(),
            },
            headers=_headers(),
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        report = payload[0]
        assert report["machine"]["id"] == machine.id
        assert report["total_operations"] == 2
        assert Decimal(str(report["production_quantity"])) == Decimal("10.000")
        assert Decimal(str(report["scrap_quantity"])) == Decimal("3.000")
        assert {operator["id"] for operator in report["operators_used"]} == {operator_one.id, operator_two.id}
    finally:
        db.close()


def test_job_report_calculates_remaining_quantity():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="job_report_actor")
        operator = _create_user(db, prefix="job_report_operator")
        machine_one = _create_machine(db, actor_id=actor.id, prefix="JOB-A")
        machine_two = _create_machine(db, actor_id=actor.id, prefix="JOB-B")
        production_order, operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("20.000"),
            machine_ids=(machine_one.id, machine_two.id),
        )
        recorded_at = datetime.now(timezone.utc)

        _complete_operation_with_pass(db, operation_id=operations[0].id, actor_id=actor.id)
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[0].id,
            batch_number=_unique("JOB-B1"),
            operator_user_id=operator.id,
            machine_id=machine_one.id,
            produced_quantity="8.000",
            scrap_quantity="2.000",
            recorded_by=actor.id,
            recorded_at=recorded_at,
        )

        response = client.get(
            "/api/v1/production/report/job",
            params={"production_order_id": production_order.id},
            headers=_headers(),
        )

        assert response.status_code == 200, response.text
        report = response.json()
        assert report["job_number"] == production_order.production_order_number
        assert Decimal(str(report["planned_quantity"])) == Decimal("20.000")
        assert Decimal(str(report["produced_quantity"])) == Decimal("8.000")
        assert Decimal(str(report["scrap_quantity"])) == Decimal("2.000")
        assert Decimal(str(report["remaining_quantity"])) == Decimal("10.000")
        assert report["operations_completed"] == 1
        assert report["operations_pending"] == 1
    finally:
        db.close()


def test_date_filters_work_correctly():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="date_filter_actor")
        operator = _create_user(db, prefix="date_filter_operator")
        machine = _create_machine(db, actor_id=actor.id, prefix="DATE-REP")
        production_order, operations = _create_production_job(
            db,
            actor=actor,
            planned_quantity=Decimal("30.000"),
            machine_ids=(machine.id, machine.id),
        )

        batch_number = _unique("DATE-BATCH")
        inside_date = datetime.now(timezone.utc)
        outside_date = inside_date - timedelta(days=10)
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[0].id,
            batch_number=batch_number,
            operator_user_id=operator.id,
            machine_id=machine.id,
            produced_quantity="7.000",
            scrap_quantity="1.000",
            recorded_by=actor.id,
            recorded_at=inside_date,
        )
        _record_log(
            db,
            production_order_id=production_order.id,
            operation_id=operations[1].id,
            batch_number=batch_number,
            operator_user_id=operator.id,
            machine_id=machine.id,
            produced_quantity="4.000",
            scrap_quantity="2.000",
            recorded_by=actor.id,
            recorded_at=outside_date,
        )

        response = client.get(
            "/api/v1/production/report/batch",
            params={
                "batch_number": batch_number,
                "start_date": inside_date.date().isoformat(),
                "end_date": inside_date.date().isoformat(),
            },
            headers=_headers(),
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        report = payload[0]
        assert Decimal(str(report["total_produced_quantity"])) == Decimal("7.000")
        assert Decimal(str(report["total_scrap_quantity"])) == Decimal("1.000")
    finally:
        db.close()
