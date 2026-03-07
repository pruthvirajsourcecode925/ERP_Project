from __future__ import annotations

import sys
import types
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select


def _install_reportlab_stubs() -> None:
    if "reportlab" in sys.modules:
        return

    reportlab = types.ModuleType("reportlab")
    lib = types.ModuleType("reportlab.lib")
    colors = types.ModuleType("reportlab.lib.colors")
    colors.HexColor = lambda value: value
    colors.black = "black"

    pagesizes = types.ModuleType("reportlab.lib.pagesizes")
    pagesizes.A4 = (595.27, 841.89)

    styles = types.ModuleType("reportlab.lib.styles")
    styles.ParagraphStyle = type("ParagraphStyle", (), {})
    styles.getSampleStyleSheet = lambda: {
        "Title": types.SimpleNamespace(),
        "Heading3": types.SimpleNamespace(),
        "Heading4": types.SimpleNamespace(),
        "BodyText": types.SimpleNamespace(fontSize=9, leading=11),
    }

    units = types.ModuleType("reportlab.lib.units")
    units.mm = 1

    platypus = types.ModuleType("reportlab.platypus")
    dummy_class = type("Dummy", (), {"__init__": lambda self, *args, **kwargs: None})
    platypus.Image = dummy_class
    platypus.Paragraph = dummy_class
    platypus.SimpleDocTemplate = dummy_class
    platypus.Spacer = dummy_class
    platypus.Table = dummy_class
    platypus.TableStyle = dummy_class

    pdfbase = types.ModuleType("reportlab.pdfbase")
    pdfmetrics = types.ModuleType("reportlab.pdfbase.pdfmetrics")
    pdfmetrics.stringWidth = lambda *args, **kwargs: 0

    pdfgen = types.ModuleType("reportlab.pdfgen")
    canvas = types.ModuleType("reportlab.pdfgen.canvas")
    canvas.Canvas = dummy_class

    reportlab.lib = lib
    reportlab.platypus = platypus
    reportlab.pdfbase = pdfbase
    reportlab.pdfgen = pdfgen
    lib.colors = colors
    lib.pagesizes = pagesizes
    lib.styles = styles
    lib.units = units
    pdfbase.pdfmetrics = pdfmetrics
    pdfgen.canvas = canvas

    sys.modules["reportlab"] = reportlab
    sys.modules["reportlab.lib"] = lib
    sys.modules["reportlab.lib.colors"] = colors
    sys.modules["reportlab.lib.pagesizes"] = pagesizes
    sys.modules["reportlab.lib.styles"] = styles
    sys.modules["reportlab.lib.units"] = units
    sys.modules["reportlab.platypus"] = platypus
    sys.modules["reportlab.pdfbase"] = pdfbase
    sys.modules["reportlab.pdfbase.pdfmetrics"] = pdfmetrics
    sys.modules["reportlab.pdfgen"] = pdfgen
    sys.modules["reportlab.pdfgen.canvas"] = canvas


_install_reportlab_stubs()

from app.db.session import SessionLocal, create_db_and_tables
from app.models.role import Role
from app.models.user import User
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.production.models import (
    FAITrigger,
    InProcessInspection,
    InspectionResult,
    Machine,
    OperationOperator,
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
    ReworkOrder,
    ReworkOrderStatus,
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
from app.services.production_service import (
    ProductionBusinessRuleError,
    assign_operator_to_operation,
    close_rework_order,
    complete_operation,
    complete_production_order,
    create_production_order,
    record_inprocess_inspection,
    record_production_log,
    release_production_order,
    start_operation,
)


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


def _create_user(db, *, prefix: str, role_name: str = "Production") -> User:
    role = _ensure_role(db, role_name)
    token = uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{token}",
        email=f"{prefix}.{token}@example.com",
        password_hash="test-hash",
        role_id=role.id,
        auth_provider="local",
        is_active=True,
        is_locked=False,
        failed_attempts=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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


def _seed_route_card(db, *, sales_order_id: int, released: bool) -> RouteCard:
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
        status=RouteCardStatus.RELEASED if released else RouteCardStatus.DRAFT,
        released_date=datetime.now(timezone.utc) if released else None,
        route_card_file_name=f"route_{code.lower()}.pdf",
        route_card_file_path=f"/tmp/route_{code.lower()}.pdf",
        route_card_file_uploaded_at=datetime.now(timezone.utc),
        route_card_file_content_type="application/pdf",
    )
    db.add(route_card)
    db.commit()
    db.refresh(route_card)
    return route_card


def _create_released_production_order_with_operations(
    db,
    *,
    planned_quantity: Decimal = Decimal("10.000"),
    operation_numbers: tuple[int, ...] = (10,),
) -> tuple[User, ProductionOrder, list[ProductionOperation]]:
    actor = _create_user(db, prefix="prod_actor", role_name="Production")
    sales_order = _seed_sales_order(db)
    route_card = _seed_route_card(db, sales_order_id=sales_order.id, released=True)

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
    for operation_number in operation_numbers:
        operation = ProductionOperation(
            production_order_id=production_order.id,
            operation_number=operation_number,
            operation_name=f"Operation {operation_number}",
            status=ProductionOperationStatus.PENDING,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(operation)
        operations.append(operation)

    db.commit()
    for operation in operations:
        db.refresh(operation)

    db.refresh(production_order)
    return actor, production_order, operations


def _create_machine(db, *, actor_id: int, prefix: str, is_active: bool = True) -> Machine:
    machine = Machine(
        machine_code=_unique(f"{prefix}-MC"),
        machine_name=f"{prefix} Machine",
        work_center=f"{prefix}-WC",
        is_active=is_active,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


def test_production_order_blocked_if_route_card_not_released():
    db = SessionLocal()
    try:
        actor = _create_user(db, prefix="prod_admin", role_name="Admin")
        sales_order = _seed_sales_order(db)
        route_card = _seed_route_card(db, sales_order_id=sales_order.id, released=False)

        with pytest.raises(ProductionBusinessRuleError, match="RouteCard status is Released"):
            create_production_order(
                db,
                production_order_number=_unique("PROD"),
                sales_order_id=sales_order.id,
                route_card_id=route_card.id,
                planned_quantity=Decimal("10.000"),
                due_date=date.today(),
                created_by=actor.id,
            )
    finally:
        db.close()


def test_operation_start_sets_status_and_started_at():
    db = SessionLocal()
    try:
        actor, production_order, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]

        started_operation = start_operation(
            db,
            production_operation_id=operation.id,
            started_by=actor.id,
        )

        db.refresh(production_order)
        assert started_operation.status == ProductionOperationStatus.IN_PROGRESS
        assert started_operation.started_at is not None
        assert production_order.status == ProductionOrderStatus.IN_PROGRESS
        assert production_order.start_date is not None
    finally:
        db.close()


def test_operation_sequence_must_follow_prior_completion():
    db = SessionLocal()
    try:
        actor, _, operations = _create_released_production_order_with_operations(
            db,
            operation_numbers=(10, 20),
        )
        second_operation = next(op for op in operations if op.operation_number == 20)

        with pytest.raises(ProductionBusinessRuleError, match="cannot start before operation 10 is completed"):
            start_operation(
                db,
                production_operation_id=second_operation.id,
                started_by=actor.id,
            )
    finally:
        db.close()


def test_inactive_machine_blocks_operation_start():
    db = SessionLocal()
    try:
        actor, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        inactive_machine = _create_machine(db, actor_id=actor.id, prefix="inactive-start", is_active=False)
        operation.machine_id = inactive_machine.id
        db.add(operation)
        db.commit()

        with pytest.raises(ProductionBusinessRuleError, match="machine must be active"):
            start_operation(
                db,
                production_operation_id=operation.id,
                started_by=actor.id,
            )
    finally:
        db.close()


def test_multiple_operators_can_be_assigned_to_same_operation():
    db = SessionLocal()
    try:
        _, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        operator_one = _create_user(db, prefix="operator_one")
        operator_two = _create_user(db, prefix="operator_two")

        first_assignment = assign_operator_to_operation(
            db,
            production_operation_id=operation.id,
            operator_user_id=operator_one.id,
            assigned_by=operator_one.id,
        )
        second_assignment = assign_operator_to_operation(
            db,
            production_operation_id=operation.id,
            operator_user_id=operator_two.id,
            assigned_by=operator_two.id,
        )

        assignments = db.scalars(
            select(OperationOperator).where(
                OperationOperator.production_operation_id == operation.id,
                OperationOperator.is_deleted.is_(False),
            )
        ).all()

        assert first_assignment.id != second_assignment.id
        assert len(assignments) == 2
    finally:
        db.close()


def test_operator_assignment_requires_production_role():
    db = SessionLocal()
    try:
        _, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        sales_user = _create_user(db, prefix="sales_user", role_name="Sales")

        with pytest.raises(ProductionBusinessRuleError, match="must have Production role"):
            assign_operator_to_operation(
                db,
                production_operation_id=operation.id,
                operator_user_id=sales_user.id,
                assigned_by=sales_user.id,
            )
    finally:
        db.close()


def test_operator_assignment_fails_when_operator_user_does_not_exist():
    db = SessionLocal()
    try:
        _, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]

        with pytest.raises(ProductionBusinessRuleError, match="Operator user not found"):
            assign_operator_to_operation(
                db,
                production_operation_id=operation.id,
                operator_user_id=999999999,
                assigned_by=None,
            )
    finally:
        db.close()


def test_operation_cannot_close_without_inspection():
    db = SessionLocal()
    try:
        actor, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        start_operation(db, production_operation_id=operation.id, started_by=actor.id)

        with pytest.raises(ProductionBusinessRuleError, match="without in-process inspection"):
            complete_operation(
                db,
                production_operation_id=operation.id,
                completed_by=actor.id,
            )
    finally:
        db.close()


def test_failed_inspection_creates_rework_order():
    db = SessionLocal()
    try:
        actor, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        start_operation(db, production_operation_id=operation.id, started_by=actor.id)

        inspection, rework_order = record_inprocess_inspection(
            db,
            production_operation_id=operation.id,
            inspection_result=InspectionResult.FAIL,
            inspected_by=actor.id,
            remarks="Dimensional mismatch",
            created_by=actor.id,
        )

        db_rework_orders = db.scalars(
            select(ReworkOrder).where(
                ReworkOrder.production_operation_id == operation.id,
                ReworkOrder.is_deleted.is_(False),
            )
        ).all()

        assert inspection.inspection_result == InspectionResult.FAIL
        assert rework_order is not None
        assert rework_order.status == ReworkOrderStatus.OPEN
        assert len(db_rework_orders) == 1
    finally:
        db.close()


def test_production_log_cannot_exceed_planned_quantity():
    db = SessionLocal()
    try:
        actor, production_order, operations = _create_released_production_order_with_operations(
            db,
            planned_quantity=Decimal("10.000"),
        )
        operation = operations[0]

        first_log = record_production_log(
            db,
            production_order_id=production_order.id,
            operation_id=operation.id,
            produced_quantity=Decimal("6.000"),
            scrap_quantity=Decimal("2.000"),
            recorded_by=actor.id,
        )

        assert first_log.id is not None

        with pytest.raises(ProductionBusinessRuleError, match="exceeds planned quantity"):
            record_production_log(
                db,
                production_order_id=production_order.id,
                operation_id=operation.id,
                produced_quantity=Decimal("3.000"),
                scrap_quantity=Decimal("0.000"),
                recorded_by=actor.id,
            )
    finally:
        db.close()


def test_inactive_machine_blocks_production_log():
    db = SessionLocal()
    try:
        actor, production_order, operations = _create_released_production_order_with_operations(
            db,
            planned_quantity=Decimal("10.000"),
        )
        operation = operations[0]
        inactive_machine = _create_machine(db, actor_id=actor.id, prefix="inactive-log", is_active=False)
        operation.machine_id = inactive_machine.id
        db.add(operation)
        db.commit()

        with pytest.raises(ProductionBusinessRuleError, match="machine must be active"):
            record_production_log(
                db,
                production_order_id=production_order.id,
                operation_id=operation.id,
                produced_quantity=Decimal("1.000"),
                scrap_quantity=Decimal("0.000"),
                recorded_by=actor.id,
            )
    finally:
        db.close()


def test_rework_order_can_close_only_after_passed_inspection():
    db = SessionLocal()
    try:
        actor, _, operations = _create_released_production_order_with_operations(db)
        operation = operations[0]
        start_operation(db, production_operation_id=operation.id, started_by=actor.id)

        _, rework_order = record_inprocess_inspection(
            db,
            production_operation_id=operation.id,
            inspection_result=InspectionResult.FAIL,
            inspected_by=actor.id,
            remarks="Dimensional mismatch",
            created_by=actor.id,
        )
        assert rework_order is not None

        with pytest.raises(ProductionBusinessRuleError, match="latest inspection result is Pass"):
            close_rework_order(
                db,
                rework_order_id=rework_order.id,
                closed_by=actor.id,
            )

        record_inprocess_inspection(
            db,
            production_operation_id=operation.id,
            inspection_result=InspectionResult.PASS,
            inspected_by=actor.id,
            remarks="Rework accepted",
            created_by=actor.id,
        )

        closed_rework_order = close_rework_order(
            db,
            rework_order_id=rework_order.id,
            closed_by=actor.id,
        )

        assert closed_rework_order.status == ReworkOrderStatus.CLOSED
    finally:
        db.close()


def test_production_order_completion_requires_rework_closed_and_quantity_reconciled():
    db = SessionLocal()
    try:
        actor, production_order, operations = _create_released_production_order_with_operations(
            db,
            planned_quantity=Decimal("10.000"),
        )
        operation = operations[0]
        start_operation(db, production_operation_id=operation.id, started_by=actor.id)

        _, rework_order = record_inprocess_inspection(
            db,
            production_operation_id=operation.id,
            inspection_result=InspectionResult.FAIL,
            inspected_by=actor.id,
            remarks="Requires rework",
            created_by=actor.id,
        )
        assert rework_order is not None

        record_inprocess_inspection(
            db,
            production_operation_id=operation.id,
            inspection_result=InspectionResult.PASS,
            inspected_by=actor.id,
            remarks="Rework cleared",
            created_by=actor.id,
        )
        complete_operation(
            db,
            production_operation_id=operation.id,
            completed_by=actor.id,
        )

        with pytest.raises(ProductionBusinessRuleError, match="open ReworkOrder exists"):
            complete_production_order(
                db,
                production_order_id=production_order.id,
                completed_by=actor.id,
            )

        close_rework_order(
            db,
            rework_order_id=rework_order.id,
            closed_by=actor.id,
        )

        record_production_log(
            db,
            production_order_id=production_order.id,
            operation_id=operation.id,
            produced_quantity=Decimal("7.000"),
            scrap_quantity=Decimal("2.000"),
            recorded_by=actor.id,
        )

        with pytest.raises(ProductionBusinessRuleError, match="reconcile with planned quantity"):
            complete_production_order(
                db,
                production_order_id=production_order.id,
                completed_by=actor.id,
            )

        record_production_log(
            db,
            production_order_id=production_order.id,
            operation_id=operation.id,
            produced_quantity=Decimal("1.000"),
            scrap_quantity=Decimal("0.000"),
            recorded_by=actor.id,
        )

        completed_order = complete_production_order(
            db,
            production_order_id=production_order.id,
            completed_by=actor.id,
        )

        assert completed_order.status == ProductionOrderStatus.COMPLETED
    finally:
        db.close()


def test_fai_trigger_created_automatically_on_first_operation_completion():
    db = SessionLocal()
    try:
        actor, production_order, operations = _create_released_production_order_with_operations(
            db,
            operation_numbers=(10, 20),
        )
        first_operation = next(op for op in operations if op.operation_number == 10)

        start_operation(db, production_operation_id=first_operation.id, started_by=actor.id)
        inspection, _ = record_inprocess_inspection(
            db,
            production_operation_id=first_operation.id,
            inspection_result=InspectionResult.PASS,
            inspected_by=actor.id,
            remarks="Inspection passed",
            created_by=actor.id,
        )
        completed_operation, fai_trigger = complete_operation(
            db,
            production_operation_id=first_operation.id,
            completed_by=actor.id,
        )

        db_fai_triggers = db.scalars(
            select(FAITrigger).where(
                FAITrigger.production_order_id == production_order.id,
                FAITrigger.is_deleted.is_(False),
            )
        ).all()
        latest_inspection = db.scalar(
            select(InProcessInspection).where(InProcessInspection.id == inspection.id)
        )
        logged_rows = db.scalars(
            select(ProductionLog).where(ProductionLog.production_order_id == production_order.id)
        ).all()

        assert latest_inspection is not None
        assert completed_operation.status == ProductionOperationStatus.COMPLETED
        assert fai_trigger is not None
        assert fai_trigger.production_order_id == production_order.id
        assert fai_trigger.operation_id == first_operation.id
        assert len(db_fai_triggers) == 1
        assert logged_rows == []
    finally:
        db.close()
