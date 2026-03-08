from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.models.role import Role
from app.models.user import User
from app.modules.dispatch.models import Invoice
from app.modules.dispatch.services import create_dispatch_order, add_dispatch_item, generate_invoice
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.production.models import (
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
)
from app.modules.production.services import ProductionBusinessRuleError, record_production_log
from app.modules.purchase.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, Supplier
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
from app.modules.stores.models import (
    BatchInventory,
    GRN,
    GRNItem,
    GRNStatus,
    InspectionStatus,
    MTCVerification,
    StorageLocation,
    StockLedger,
)
from app.services.stores_service import perform_rmir_inspection


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    create_db_and_tables()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _traceable_batch_number() -> str:
    token = uuid4().hex.upper()
    return f"DRW-{token[:4]} / SO-{token[4:6]}-{token[6:9]} / CUST-{token[9:12]} / HEAT-{token[12:14]}"


def _ensure_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role

    role = Role(name=name, description=f"{name} role", is_active=True)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def _ensure_user(db, *, username: str, email: str, role_name: str) -> User:
    role = _ensure_role(db, role_name)
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(
            username=username,
            email=email,
            password_hash=get_password_hash("Password@123"),
            role_id=role.id,
            auth_provider="local",
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            is_deleted=False,
        )
    else:
        user.email = email
        user.password_hash = get_password_hash("Password@123")
        user.role_id = role.id
        user.is_active = True
        user.is_locked = False
        user.failed_attempts = 0
        user.is_deleted = False

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_sales_order(db, *, admin_id: int) -> SalesOrder:
    code = uuid4().hex[:10].upper()

    customer = Customer(
        customer_code=f"CUST{code[:8]}",
        name=f"Customer {code}",
        email=f"customer.{code.lower()}@example.com",
        is_active=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(customer)
    db.flush()

    enquiry = Enquiry(
        enquiry_number=f"ENQ{code[:8]}",
        customer_id=customer.id,
        enquiry_date=date.today(),
        currency="INR",
        status=EnquiryStatus.DRAFT,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(enquiry)
    db.flush()

    contract_review = ContractReview(
        document_number=f"CR-{date.today().year}-{code[:8]}",
        revision=0,
        generated_at=datetime.now(timezone.utc),
        generated_by=admin_id,
        enquiry_id=enquiry.id,
        status=ContractReviewStatus.APPROVED,
        scope_clarity_ok=True,
        capability_ok=True,
        capacity_ok=True,
        delivery_commitment_ok=True,
        quality_requirements_ok=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(contract_review)
    db.flush()

    quotation = Quotation(
        document_number=f"QT-{date.today().year}-{code[:8]}",
        revision=0,
        generated_at=datetime.now(timezone.utc),
        generated_by=admin_id,
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
        status=QuotationStatus.ISSUED,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(quotation)
    db.flush()

    po_review = CustomerPOReview(
        document_number=f"POA-{date.today().year}-{code[:8]}",
        revision=0,
        generated_at=datetime.now(timezone.utc),
        generated_by=admin_id,
        quotation_id=quotation.id,
        customer_po_number=f"PO{code[:8]}",
        customer_po_date=date.today(),
        accepted=True,
        status=CustomerPOReviewStatus.ACCEPTED,
        created_by=admin_id,
        updated_by=admin_id,
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
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(sales_order)
    db.commit()
    db.refresh(sales_order)
    return sales_order


def _seed_route_card(db, *, sales_order_id: int, admin_id: int) -> RouteCard:
    code = uuid4().hex[:10].upper()

    drawing = Drawing(
        drawing_number=f"DRW-{code[:8]}",
        part_name=f"Part {code}",
        is_active=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(drawing)
    db.flush()

    drawing_revision = DrawingRevision(
        drawing_id=drawing.id,
        revision_code="A",
        revision_date=date.today(),
        file_path=f"/tmp/{code.lower()}.pdf",
        is_current=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(drawing_revision)
    db.flush()

    route_card = RouteCard(
        route_number=f"RC-{code[:8]}",
        drawing_revision_id=drawing_revision.id,
        sales_order_id=sales_order_id,
        status=RouteCardStatus.RELEASED,
        released_by=admin_id,
        released_date=datetime.now(timezone.utc),
        route_card_file_name=f"route_{code.lower()}.pdf",
        route_card_file_path=f"/tmp/route_{code.lower()}.pdf",
        route_card_file_uploaded_at=datetime.now(timezone.utc),
        route_card_file_content_type="application/pdf",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(route_card)
    db.commit()
    db.refresh(route_card)
    return route_card


def _seed_production_context(db, *, admin_id: int, planned_quantity: Decimal) -> dict[str, object]:
    sales_order = _seed_sales_order(db, admin_id=admin_id)
    route_card = _seed_route_card(db, sales_order_id=sales_order.id, admin_id=admin_id)

    production_order = ProductionOrder(
        production_order_number=_unique("PROD"),
        sales_order_id=sales_order.id,
        route_card_id=route_card.id,
        planned_quantity=planned_quantity,
        status=ProductionOrderStatus.RELEASED,
        start_date=date.today(),
        due_date=date.today(),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(production_order)
    db.flush()

    operation = ProductionOperation(
        production_order_id=production_order.id,
        operation_number=10,
        operation_name="Concurrent Operation",
        status=ProductionOperationStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(operation)
    db.commit()
    db.refresh(production_order)
    db.refresh(operation)
    return {"sales_order": sales_order, "production_order": production_order, "operation": operation}


def _seed_receiving_context(db, *, admin_id: int, sales_order_id: int, accepted_quantity: Decimal) -> dict[str, object]:
    supplier = Supplier(
        supplier_code=_unique("SUP"),
        supplier_name="Concurrent Supplier",
        is_approved=True,
        quality_acknowledged=True,
        is_active=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(supplier)
    db.flush()

    purchase_order = PurchaseOrder(
        po_number=_unique("PO"),
        supplier_id=supplier.id,
        sales_order_id=sales_order_id,
        po_date=date.today(),
        status=PurchaseOrderStatus.ISSUED,
        total_amount=Decimal("50.00"),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(purchase_order)
    db.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=purchase_order.id,
        description="Concurrent Raw Material",
        quantity=accepted_quantity,
        unit_price=Decimal("10.00"),
        line_total=Decimal("50.00"),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(po_item)
    db.flush()

    location = StorageLocation(
        location_code=_unique("LOC"),
        location_name="Concurrent Stores",
        is_active=True,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(location)
    db.flush()

    grn = GRN(
        grn_number=_unique("GRN"),
        purchase_order_id=purchase_order.id,
        supplier_id=supplier.id,
        received_by=admin_id,
        received_datetime=datetime.now(timezone.utc),
        grn_date=date.today(),
        status=GRNStatus.DRAFT,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(grn)
    db.flush()

    batch_number = _traceable_batch_number()
    grn_item = GRNItem(
        grn_id=grn.id,
        item_code="RM-CONCURRENT-001",
        description="Concurrent Raw Material",
        heat_number="HEAT-01",
        batch_number=batch_number,
        received_quantity=accepted_quantity,
        accepted_quantity=accepted_quantity,
        rejected_quantity=Decimal("0.000"),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(grn_item)
    db.flush()

    mtc = MTCVerification(
        grn_item_id=grn_item.id,
        mtc_number=_unique("MTC"),
        chemical_composition_verified=True,
        mechanical_properties_verified=True,
        standard_compliance_verified=True,
        verified_by=admin_id,
        verification_date=date.today(),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(mtc)
    db.commit()
    db.refresh(grn_item)
    db.refresh(location)
    return {
        "supplier": supplier,
        "purchase_order": purchase_order,
        "location": location,
        "grn_item": grn_item,
        "batch_number": batch_number,
    }


def _concurrent_call(workers: int, func):
    barrier = Barrier(workers)
    outcomes: list[tuple[str, object]] = []

    def wrapped(index: int) -> None:
        barrier.wait()
        try:
            outcomes.append(("ok", func(index)))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(("error", exc))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(wrapped, range(workers)))
    return outcomes


def test_concurrent_rmir_acceptance_creates_single_batch_inventory():
    accepted_quantity = Decimal("5.000")
    db = SessionLocal()
    try:
        admin = _ensure_user(db, username="concurrent_admin", email="concurrent_admin@example.com", role_name="Admin")
        inspector_one = _ensure_user(db, username="stores_inspector_1", email="stores_inspector_1@example.com", role_name="Admin")
        inspector_two = _ensure_user(db, username="stores_inspector_2", email="stores_inspector_2@example.com", role_name="Admin")
        production_context = _seed_production_context(db, admin_id=admin.id, planned_quantity=accepted_quantity)
        receiving_context = _seed_receiving_context(
            db,
            admin_id=admin.id,
            sales_order_id=production_context["sales_order"].id,
            accepted_quantity=accepted_quantity,
        )
    finally:
        db.close()

    user_ids = [inspector_one.id, inspector_two.id]

    def accept_rmir(index: int):
        thread_db = SessionLocal()
        try:
            return perform_rmir_inspection(
                thread_db,
                grn_item_id=receiving_context["grn_item"].id,
                inspection_date=date.today(),
                inspected_by=user_ids[index],
                inspection_status=InspectionStatus.ACCEPTED,
                remarks="Concurrent accept",
                storage_location_id=receiving_context["location"].id,
                updated_by=user_ids[index],
            )
        finally:
            thread_db.close()

    outcomes = _concurrent_call(2, accept_rmir)
    assert any(status == "ok" for status, _ in outcomes)

    db = SessionLocal()
    try:
        inventories = db.scalars(
            select(BatchInventory).where(
                BatchInventory.batch_number == receiving_context["batch_number"],
                BatchInventory.is_deleted.is_(False),
            )
        ).all()
        assert len(inventories) == 1
        assert Decimal(str(inventories[0].current_quantity)) == accepted_quantity

        ledger_entries = db.scalars(
            select(StockLedger).where(StockLedger.batch_number == receiving_context["batch_number"])
        ).all()
        net_quantity = sum(Decimal(str(entry.quantity_in)) - Decimal(str(entry.quantity_out)) for entry in ledger_entries)
        assert net_quantity == accepted_quantity
    finally:
        db.close()


def test_concurrent_production_logs_do_not_exceed_planned_quantity():
    planned_quantity = Decimal("5.000")
    db = SessionLocal()
    try:
        admin = _ensure_user(db, username="concurrent_prod_admin", email="concurrent_prod_admin@example.com", role_name="Admin")
        operator_one = _ensure_user(db, username="prod_operator_1", email="prod_operator_1@example.com", role_name="Production")
        operator_two = _ensure_user(db, username="prod_operator_2", email="prod_operator_2@example.com", role_name="Production")
        production_context = _seed_production_context(db, admin_id=admin.id, planned_quantity=planned_quantity)
    finally:
        db.close()

    operator_ids = [operator_one.id, operator_two.id]
    quantities = [Decimal("3.000"), Decimal("3.000")]
    batch_number = _traceable_batch_number()

    def create_log(index: int):
        thread_db = SessionLocal()
        try:
            return record_production_log(
                thread_db,
                production_order_id=production_context["production_order"].id,
                operation_id=production_context["operation"].id,
                batch_number=batch_number,
                produced_quantity=quantities[index],
                scrap_quantity=Decimal("0.000"),
                recorded_by=operator_ids[index],
                created_by=operator_ids[index],
                recorded_at=datetime.now(timezone.utc),
            )
        finally:
            thread_db.close()

    outcomes = _concurrent_call(2, create_log)
    assert any(status == "ok" for status, _ in outcomes)

    db = SessionLocal()
    try:
        logs = db.scalars(
            select(ProductionLog).where(
                ProductionLog.production_order_id == production_context["production_order"].id,
                ProductionLog.is_deleted.is_(False),
            )
        ).all()
        total_logged = sum(Decimal(str(log.produced_quantity)) + Decimal(str(log.scrap_quantity)) for log in logs)
        assert total_logged <= planned_quantity
    finally:
        db.close()


def test_concurrent_dispatch_invoice_generation_keeps_single_invoice_and_preserves_stock():
    accepted_quantity = Decimal("5.000")
    db = SessionLocal()
    try:
        admin = _ensure_user(db, username="concurrent_dispatch_admin", email="concurrent_dispatch_admin@example.com", role_name="Admin")
        production_context = _seed_production_context(db, admin_id=admin.id, planned_quantity=accepted_quantity)
        receiving_context = _seed_receiving_context(
            db,
            admin_id=admin.id,
            sales_order_id=production_context["sales_order"].id,
            accepted_quantity=accepted_quantity,
        )
        inventory = BatchInventory(
            batch_number=receiving_context["batch_number"],
            storage_location_id=receiving_context["location"].id,
            item_code=receiving_context["grn_item"].item_code,
            current_quantity=accepted_quantity,
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(inventory)
        db.flush()

        dispatch_order = create_dispatch_order(
            db,
            dispatch_number=_unique("DSP"),
            sales_order_id=production_context["sales_order"].id,
            dispatch_date=date.today(),
            shipping_method="Road",
            destination="Customer Site",
            remarks="Concurrent dispatch",
            created_by=admin.id,
        )
        add_dispatch_item(
            db,
            dispatch_order_id=dispatch_order.id,
            production_order_id=production_context["production_order"].id,
            line_number=1,
            item_code="FG-CONCURRENT-001",
            quantity=accepted_quantity,
            uom="Nos",
            lot_number=_unique("LOT"),
            is_traceability_verified=True,
            created_by=admin.id,
        )
        db.commit()
        db.refresh(dispatch_order)
    finally:
        db.close()

    def create_invoice(_index: int):
        thread_db = SessionLocal()
        try:
            return generate_invoice(
                thread_db,
                dispatch_order_id=dispatch_order.id,
                invoice_date=date.today(),
                currency="INR",
                subtotal=Decimal("100.00"),
                tax_amount=Decimal("18.00"),
                total_amount=Decimal("118.00"),
                remarks="Concurrent invoice",
                created_by=admin.id,
            )
        finally:
            thread_db.close()

    outcomes = _concurrent_call(2, create_invoice)
    assert any(status == "ok" for status, _ in outcomes)

    db = SessionLocal()
    try:
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.dispatch_order_id == dispatch_order.id,
                Invoice.is_deleted.is_(False),
            )
        ).all()
        assert len(invoices) == 1

        inventory = db.scalar(
            select(BatchInventory).where(
                BatchInventory.batch_number == receiving_context["batch_number"],
                BatchInventory.is_deleted.is_(False),
            )
        )
        assert inventory is not None
        assert Decimal(str(inventory.current_quantity)) == accepted_quantity
    finally:
        db.close()