from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

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
from app.modules.production.models import (
    InProcessInspection,
    InspectionResult,
    ProductionLog,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
    ProductionOrderStatus,
)
from app.modules.purchase.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, Supplier
from app.modules.quality.models import (
    AuditPlan,
    AuditReport,
    CAPA,
    CAPAActionType,
    CAPAStatus,
    CertificateOfConformance,
    FAIReport,
    FAIReportStatus,
    FinalInspection,
    IncomingInspection,
    IncomingInspectionStatus,
    NCR,
    NCRDefectCategory,
    NCRStatus,
    QualityInspectionResult,
)
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
from app.modules.stores.models import BatchInventory, GRN, GRNItem, GRNStatus, MTCVerification, StorageLocation


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def _traceable_batch_number() -> str:
    token = uuid4().hex.upper()
    return f"DRW-{token[:4]} / SO-{token[4:6]}-{token[6:9]} / CUST-{token[9:12]} / HEAT-{token[12:14]}"


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
        "operation_id": operation.id,
        "sales_order": sales_order,
        "production_order": production_order,
        "customer_name": sales_order.customer.name,
    }


def _seed_quality_report_context(db) -> dict[str, object]:
    seeded = _seed_dispatch_context(db)
    admin_id = seeded["admin_id"]
    sales_order = seeded["sales_order"]
    production_order = seeded["production_order"]
    operation_id = seeded["operation_id"]
    batch_number = _traceable_batch_number()

    supplier = Supplier(
        supplier_code=_unique("SUP"),
        supplier_name="Quality Report Supplier",
        contact_person="QA Contact",
        phone="9999999999",
        email=f"supplier.{uuid4().hex[:8]}@example.com",
        address="Industrial Estate",
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
        sales_order_id=sales_order.id,
        po_date=date.today(),
        expected_delivery_date=date.today(),
        status=PurchaseOrderStatus.ISSUED,
        total_amount=Decimal("50.00"),
        quality_notes="Traceability material",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(purchase_order)
    db.flush()

    purchase_order_item = PurchaseOrderItem(
        purchase_order_id=purchase_order.id,
        description="Quality report raw material",
        quantity=Decimal("25.000"),
        unit_price=Decimal("2.00"),
        line_total=Decimal("50.00"),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(purchase_order_item)

    location = StorageLocation(
        location_code=_unique("LOC"),
        location_name="Quality Report Stores",
        description="Storage for quality report validation",
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
        status=GRNStatus.ACCEPTED,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(grn)
    db.flush()

    grn_item = GRNItem(
        grn_id=grn.id,
        item_code="RM-QA-001",
        description="Quality report raw material",
        heat_number="HEAT-QA-01",
        batch_number=batch_number,
        received_quantity=Decimal("25.000"),
        accepted_quantity=Decimal("25.000"),
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

    batch_inventory = BatchInventory(
        batch_number=batch_number,
        storage_location_id=location.id,
        item_code=grn_item.item_code,
        current_quantity=Decimal("25.000"),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(batch_inventory)

    incoming_inspection = IncomingInspection(
        grn_id=grn.id,
        grn_item_id=grn_item.id,
        inspected_by=admin_id,
        inspection_date=date.today(),
        status=IncomingInspectionStatus.ACCEPTED,
        remarks="Accepted into stores",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(incoming_inspection)

    inprocess_inspection = InProcessInspection(
        production_operation_id=operation_id,
        inspected_by=admin_id,
        inspection_result=InspectionResult.PASS,
        remarks="In-process inspection passed",
        inspection_time=datetime.now(timezone.utc),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(inprocess_inspection)

    production_log = ProductionLog(
        production_order_id=production_order.id,
        operation_id=operation_id,
        batch_number=batch_number,
        operator_user_id=admin_id,
        produced_quantity=Decimal("25.000"),
        scrap_quantity=Decimal("0.000"),
        recorded_by=admin_id,
        recorded_at=datetime.now(timezone.utc),
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(production_log)

    final_inspection = db.scalar(
        select(FinalInspection).where(FinalInspection.production_order_id == production_order.id)
    )
    if final_inspection is None:
        final_inspection = FinalInspection(
            production_order_id=production_order.id,
            inspected_by=admin_id,
            inspection_date=date.today(),
            result=QualityInspectionResult.PASS,
            remarks="Final inspection passed",
            created_by=admin_id,
            updated_by=admin_id,
        )
        db.add(final_inspection)
        db.flush()
    final_inspection.result = QualityInspectionResult.PASS
    final_inspection.remarks = "Final inspection passed"
    db.add(final_inspection)

    fai = FAIReport(
        production_order_id=production_order.id,
        drawing_number=production_order.route_card.drawing_revision.drawing.drawing_number,
        revision=production_order.route_card.drawing_revision.revision_code,
        part_number=production_order.route_card.drawing_revision.drawing.part_name,
        inspected_by=admin_id,
        inspection_date=date.today(),
        status=FAIReportStatus.APPROVED,
        attachment_path="/tmp/fai-attachment.pdf",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(fai)
    db.flush()

    ncr = NCR(
        reference_type="FAIReport",
        reference_id=fai.id,
        reported_by=admin_id,
        reported_date=datetime.now(timezone.utc),
        defect_category=NCRDefectCategory.DOCUMENTATION,
        description="Documentation discrepancy resolved through CAPA",
        status=NCRStatus.CLOSED,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(ncr)
    db.flush()

    capa = CAPA(
        ncr_id=ncr.id,
        action_type=CAPAActionType.CORRECTIVE,
        responsible_person=admin_id,
        target_date=date.today(),
        status=CAPAStatus.CLOSED,
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(capa)

    audit_plan = AuditPlan(
        audit_area="Quality Assurance",
        planned_date=date.today(),
        auditor=admin_id,
        status="Completed",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(audit_plan)
    db.flush()

    audit_report = AuditReport(
        audit_plan_id=audit_plan.id,
        findings="Linked quality documents verified successfully",
        status="Closed",
        created_by=admin_id,
        updated_by=admin_id,
    )
    db.add(audit_report)

    db.commit()
    return {
        "inspection_id": final_inspection.id,
        "fai_id": fai.id,
        "ncr_id": ncr.id,
        "capa_id": capa.id,
        "audit_id": audit_report.id,
        "batch_number": batch_number,
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


def test_quality_reports_bundle_validation():
    create_db_and_tables()

    db = SessionLocal()
    try:
        context = _seed_quality_report_context(db)
    finally:
        db.close()

    report_paths = {
        "fir": quality_reports.generate_fir_report(context["inspection_id"]),
        "fai": quality_reports.generate_fai_report(context["fai_id"]),
        "ncr": quality_reports.generate_ncr_report(context["ncr_id"]),
        "capa": quality_reports.generate_capa_report(context["capa_id"]),
        "audit": quality_reports.generate_audit_report(context["audit_id"]),
        "traceability": quality_reports.generate_traceability_report(context["batch_number"]),
    }

    for report_type, file_path in report_paths.items():
        path = Path(file_path)
        assert path.exists(), report_type
        assert path.suffix.lower() == ".pdf"
        assert path.stat().st_size > 0
        assert path.read_bytes().startswith(b"%PDF")

    bundle_path = quality_reports.generate_quality_reports_bundle(
        inspection_id=context["inspection_id"],
        fai_id=context["fai_id"],
        ncr_id=context["ncr_id"],
        capa_id=context["capa_id"],
        audit_id=context["audit_id"],
        batch_number=context["batch_number"],
    )
    bundle = Path(bundle_path)
    assert bundle.exists()
    assert bundle.suffix.lower() == ".zip"

    with ZipFile(bundle) as archive:
        names = archive.namelist()

    assert len(names) == 6
    assert any(name.startswith("FIR_") for name in names)
    assert any(name.startswith("FAI_") for name in names)
    assert any(name.startswith("NCR_") for name in names)
    assert any(name.startswith("CAPA_") for name in names)
    assert any(name.startswith("AUDIT_") for name in names)
    assert any(name.startswith("TRACEABILITY_") for name in names)


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