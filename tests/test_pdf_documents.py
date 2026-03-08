from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import SessionLocal, create_db_and_tables
from app.models.role import Role
from app.models.user import User
from app.modules.dispatch.reports import generate_delivery_challan as generate_delivery_challan_pdf
from app.modules.dispatch.reports import generate_invoice as generate_invoice_pdf
from app.modules.dispatch.services import add_dispatch_item, create_dispatch_order
from app.modules.dispatch.services import generate_delivery_challan as create_delivery_challan_document
from app.modules.dispatch.services import generate_invoice as create_invoice_document
from app.modules.engineering.models import Drawing, DrawingRevision, RouteCard, RouteCardStatus
from app.modules.production.models import ProductionOperation, ProductionOperationStatus, ProductionOrder, ProductionOrderStatus
from app.modules.quality.models import CertificateOfConformance
from app.modules.quality import reports as quality_reports
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


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _safe_filename_fragment(value: str) -> str:
    safe = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("_")
    sanitized = "".join(safe).strip("_")
    return sanitized or "unknown"


def _ensure_role(db, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is not None:
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


def _seed_dispatch_context(db) -> dict[str, object]:
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
        operation_name="PDF Validation Operation",
        status=ProductionOperationStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(operation)
    db.commit()
    db.refresh(production_order)
    db.refresh(sales_order)
    return {
        "admin_id": admin.id,
        "sales_order": sales_order,
        "production_order": production_order,
        "customer_name": sales_order.customer.name,
    }


def _create_dispatch_documents(db):
    seeded = _seed_dispatch_context(db)
    dispatch_order = create_dispatch_order(
        db,
        dispatch_number=_unique("DSP"),
        sales_order_id=seeded["sales_order"].id,
        dispatch_date=date.today(),
        shipping_method="Road",
        destination="Customer Site",
        remarks="PDF validation dispatch",
        created_by=seeded["admin_id"],
    )
    add_dispatch_item(
        db,
        dispatch_order_id=dispatch_order.id,
        production_order_id=seeded["production_order"].id,
        line_number=1,
        item_code=_unique("ITEM"),
        description="PDF validation item",
        quantity=Decimal("5.000"),
        uom="Nos",
        lot_number=_unique("LOT"),
        is_traceability_verified=True,
        remarks="PDF validation",
        created_by=seeded["admin_id"],
    )
    invoice = create_invoice_document(
        db,
        dispatch_order_id=dispatch_order.id,
        invoice_date=date.today(),
        currency="INR",
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        total_amount=Decimal("118.00"),
        remarks="Invoice for PDF validation",
        created_by=seeded["admin_id"],
    )
    challan = create_delivery_challan_document(
        db,
        dispatch_order_id=dispatch_order.id,
        issue_date=date.today(),
        received_by="Receiver",
        remarks="Challan for PDF validation",
        created_by=seeded["admin_id"],
    )
    return {
        "admin_id": seeded["admin_id"],
        "customer_name": seeded["customer_name"],
        "production_order_id": seeded["production_order"].id,
        "dispatch_order_id": dispatch_order.id,
        "invoice_number": invoice.invoice_number,
        "challan_number": challan.challan_number,
    }


def _assert_pdf_file(file_path: str, *, expected_filename: str) -> Path:
    path = Path(file_path)
    assert path.suffix.lower() == ".pdf"
    assert path.name == expected_filename
    assert path.exists()
    assert path.stat().st_size > 0
    assert path.read_bytes().startswith(b"%PDF")
    return path


def test_invoice_pdf_document_validation():
    create_db_and_tables()

    db = SessionLocal()
    try:
        context = _create_dispatch_documents(db)
        file_path = generate_invoice_pdf(
            db,
            dispatch_order_id=context["dispatch_order_id"],
            prepared_by_user_id=context["admin_id"],
        )
    finally:
        db.close()

    expected_filename = (
        f"{_safe_filename_fragment(context['invoice_number'])}_"
        f"{_safe_filename_fragment(context['customer_name'])}.pdf"
    )
    _assert_pdf_file(file_path, expected_filename=expected_filename)


def test_challan_pdf_document_validation():
    create_db_and_tables()

    db = SessionLocal()
    try:
        context = _create_dispatch_documents(db)
        file_path = generate_delivery_challan_pdf(
            db,
            dispatch_order_id=context["dispatch_order_id"],
            prepared_by_user_id=context["admin_id"],
        )
    finally:
        db.close()

    expected_filename = (
        f"CHALLAN_{_safe_filename_fragment(context['challan_number'])}_"
        f"{_safe_filename_fragment(context['customer_name'])}.pdf"
    )
    _assert_pdf_file(file_path, expected_filename=expected_filename)


@pytest.mark.xfail(reason="COC PDF generator is not implemented in app.modules.quality.reports", strict=False)
def test_coc_pdf_document_validation():
    create_db_and_tables()
    generator = getattr(quality_reports, "generate_coc_report", None)
    if generator is None:
        pytest.xfail("COC PDF generator is not implemented in app.modules.quality.reports")

    db = SessionLocal()
    try:
        context = _create_dispatch_documents(db)
        coc = CertificateOfConformance(
            production_order_id=context["production_order_id"],
            certificate_number=_unique("COC"),
            issued_by=context["admin_id"],
            issued_date=date.today(),
            remarks="COC for PDF validation",
        )
        db.add(coc)
        db.commit()
        db.refresh(coc)

        file_path = generator(coc.id)
    finally:
        db.close()

    expected_filename = f"{_safe_filename_fragment(coc.certificate_number)}.pdf"
    _assert_pdf_file(file_path, expected_filename=expected_filename)