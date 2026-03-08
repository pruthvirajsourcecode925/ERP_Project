from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.modules.production.models import ProductionOrder
from app.modules.quality.models import AuditReport, CAPA, FAIReport, FinalInspection, NCR
from app.modules.quality.traceability import BatchTraceabilityError, get_batch_traceability
from app.modules.sales.models import CustomerPOReview, Quotation, SalesOrder
from app.modules.sales.pdf.quotation_config import COMPANY_INFO, LOGO_PATH


class QualityReportGenerationError(Exception):
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def create_quality_report_directory(report_type: str | None = None) -> Path:
    base_dir = _project_root() / "storage" / "quality_reports"
    target_dir = base_dir if report_type is None else base_dir / report_type
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def ensure_quality_report_directories() -> dict[str, Path]:
    directory_names = ("fir", "fai", "ncr", "capa", "audit", "traceability")
    directories = {"root": create_quality_report_directory()}
    for directory_name in directory_names:
        directories[directory_name] = create_quality_report_directory(directory_name)
    return directories


def _safe_filename_fragment(value: str) -> str:
    safe = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("_")
    sanitized = "".join(safe).strip("_")
    return sanitized or "unknown"


def _dated_report_filename(prefix: str, suffix: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d")
    safe_suffix = _safe_filename_fragment(suffix)
    safe_prefix = _safe_filename_fragment(prefix)
    return f"{safe_prefix}_{safe_suffix}_{stamp}.pdf"


def _linked_report_filename(document_code: str, **parts: object) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d")
    tokens = [_safe_filename_fragment(document_code)]
    for key, value in parts.items():
        if value in (None, ""):
            continue
        tokens.append(f"{_safe_filename_fragment(str(key)).upper()}{_safe_filename_fragment(str(value))}")
    tokens.append(stamp)
    return f"{'_'.join(tokens)}.pdf"


def _styles() -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QualityReportTitle",
        parent=styles["Title"],
        fontSize=15,
        leading=18,
        alignment=1,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "QualityReportSubtitle",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        alignment=1,
        textColor=colors.HexColor("#1F2937"),
    )
    section_style = ParagraphStyle(
        "QualityReportSection",
        parent=styles["Heading3"],
        fontSize=10.5,
        leading=12,
        textColor=colors.HexColor("#111827"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = styles["BodyText"]
    body_style.fontSize = 9
    body_style.leading = 11
    return title_style, subtitle_style, section_style, body_style


def _company_name() -> str:
    value = COMPANY_INFO.get("company_name") or COMPANY_INFO.get("name")
    if value is None:
        return "Company Name"
    text = str(value).strip()
    return text or "Company Name"


def _company_contact_line() -> str:
    email = str(COMPANY_INFO.get("company_email") or COMPANY_INFO.get("email") or "").strip()
    phone = str(COMPANY_INFO.get("company_phone") or COMPANY_INFO.get("phone") or "").strip()
    if email and phone:
        return f"{email} | {phone}"
    if email:
        return email
    if phone:
        return phone
    return ""


def _build_document_header(*, body_style: ParagraphStyle) -> Table:
    logo_cell: object = Paragraph("", body_style)
    if LOGO_PATH.exists():
        logo_cell = Image(str(LOGO_PATH), width=30 * mm, height=12 * mm)

    company_lines = [f"<b>{_company_name()}</b>"]
    company_contact = _company_contact_line()
    if company_contact:
        company_lines.append(company_contact)

    company_block = Paragraph(
        "<br/>".join(company_lines),
        ParagraphStyle(
            "QualityCompanyHeader",
            parent=body_style,
            alignment=1,
            fontSize=10,
            leading=12,
        ),
    )

    spacer_cell = Paragraph("", body_style)
    # Keep left and right columns symmetrical so center block is visually centered.
    header = Table([[logo_cell, company_block, spacer_cell]], colWidths=[32 * mm, 118 * mm, 32 * mm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return header


def _text(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    return str(value)


def _build_key_value_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[48 * mm, 135 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _render_report(
    output_file: Path,
    *,
    title: str,
    subtitle: str,
    rows: list[tuple[str, str]],
) -> str:
    title_style, subtitle_style, section_style, body_style = _styles()
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )

    story = [
        _build_document_header(body_style=body_style),
        Spacer(1, 5),
        Paragraph(title, title_style),
        Paragraph(subtitle, subtitle_style),
        Spacer(1, 4),
        Paragraph("Report Details", section_style),
        _build_key_value_table(rows),
        Spacer(1, 8),
        Paragraph(f"Generated At: {_text(datetime.utcnow())}", body_style),
    ]

    doc.build(story)
    return str(output_file)


def _render_traceability_report(output_file: Path, *, batch_number: str, traceability: dict[str, object]) -> str:
    title_style, subtitle_style, section_style, body_style = _styles()
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Traceability Report {batch_number}",
    )

    def append_section(story: list[object], heading: str, rows: list[tuple[str, str]]) -> None:
        story.append(Paragraph(heading, section_style))
        if rows:
            story.append(_build_key_value_table(rows))
        else:
            story.append(Paragraph("No records found.", body_style))
        story.append(Spacer(1, 6))

    supplier = traceability.get("supplier") or {}
    purchase_order = traceability.get("purchase_order") or {}
    grn = traceability.get("grn") or {}
    production_orders = traceability.get("production_orders") or []
    inspections = traceability.get("inspections") or []
    ncr_records = traceability.get("ncr_records") or []
    customers = traceability.get("customers") or []

    story: list[object] = [
        _build_document_header(body_style=body_style),
        Spacer(1, 5),
        Paragraph("Batch Traceability Report", title_style),
        Paragraph("AS9100D genealogy traceability summary", subtitle_style),
        Spacer(1, 6),
    ]

    append_section(story, "Batch Details", [("Batch Number", _text(traceability.get("batch_number")))])
    append_section(
        story,
        "Supplier Information",
        [
            ("Supplier Name", _text(supplier.get("supplier_name"))),
            ("Supplier Code", _text(supplier.get("supplier_code"))),
            ("Email", _text(supplier.get("email"))),
            ("Phone", _text(supplier.get("phone"))),
        ],
    )
    append_section(
        story,
        "Purchase Order",
        [
            ("PO Number", _text(purchase_order.get("po_number"))),
            ("Status", _text(purchase_order.get("status"))),
            ("PO Date", _text(purchase_order.get("po_date"))),
            ("Sales Order ID", _text(purchase_order.get("sales_order_id"))),
        ],
    )
    append_section(
        story,
        "GRN",
        [
            ("GRN Number", _text(grn.get("grn_number"))),
            ("GRN Date", _text(grn.get("grn_date"))),
            ("Status", _text(grn.get("status"))),
            ("GRN Item ID", _text(grn.get("grn_item_id"))),
            ("Item Code", _text(grn.get("item_code"))),
            ("Heat Number", _text(grn.get("heat_number"))),
        ],
    )

    production_rows = [
        (
            f"Production Order {index + 1}",
            ", ".join(
                [
                    f"Number: {_text(item.get('production_order_number'))}",
                    f"Status: {_text(item.get('status'))}",
                    f"Route Card ID: {_text(item.get('route_card_id'))}",
                ]
            ),
        )
        for index, item in enumerate(production_orders)
    ]
    append_section(story, "Production Orders", production_rows)

    inspection_rows = [
        (
            f"Inspection {index + 1}",
            ", ".join(
                [
                    f"Type: {_text(item.get('inspection_type'))}",
                    f"ID: {_text(item.get('id'))}",
                    f"Status: {_text(item.get('status') or item.get('inspection_result') or item.get('result'))}",
                    f"Date: {_text(item.get('inspection_date') or item.get('inspection_time'))}",
                ]
            ),
        )
        for index, item in enumerate(inspections)
    ]
    append_section(story, "Inspection Results", inspection_rows)

    ncr_rows = [
        (
            f"NCR {index + 1}",
            ", ".join(
                [
                    f"ID: {_text(item.get('id'))}",
                    f"Reference: {_text(item.get('reference_type'))}#{_text(item.get('reference_id'))}",
                    f"Status: {_text(item.get('status'))}",
                    f"Description: {_text(item.get('description'))}",
                ]
            ),
        )
        for index, item in enumerate(ncr_records)
    ]
    append_section(story, "NCR Records", ncr_rows)

    customer_rows = [
        (
            f"Customer {index + 1}",
            ", ".join(
                [
                    f"Name: {_text(item.get('name'))}",
                    f"Code: {_text(item.get('customer_code'))}",
                    f"Email: {_text(item.get('email'))}",
                ]
            ),
        )
        for index, item in enumerate(customers)
    ]
    append_section(story, "Customers Delivered", customer_rows)

    story.append(Paragraph(f"Generated At: {_text(datetime.utcnow())}", body_style))
    doc.build(story)
    return str(output_file)


def _get_entity_or_raise(db: Session, model: type, entity_id: int, label: str):
    entity = db.scalar(select(model).where(model.id == entity_id))
    if entity is None:
        raise QualityReportGenerationError(f"{label} {entity_id} not found")
    return entity


def _resolve_sales_document_linkage(db: Session, *, production_order_id: int) -> dict[str, str]:
    production_order = _get_entity_or_raise(db, ProductionOrder, production_order_id, "Production order")

    sales_order = db.scalar(
        select(SalesOrder).where(
            SalesOrder.id == production_order.sales_order_id,
            SalesOrder.is_deleted.is_(False),
        )
    )
    if sales_order is None:
        raise QualityReportGenerationError("Sales order linkage is required for this report")

    quotation = db.scalar(
        select(Quotation).where(
            Quotation.id == sales_order.quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )
    if quotation is None:
        raise QualityReportGenerationError("Quotation linkage is required for this report")

    po_review = db.scalar(
        select(CustomerPOReview).where(
            CustomerPOReview.id == sales_order.customer_po_review_id,
            CustomerPOReview.is_deleted.is_(False),
        )
    )
    if po_review is None:
        raise QualityReportGenerationError("Customer PO review linkage is required for this report")

    if po_review.quotation_id != quotation.id:
        raise QualityReportGenerationError("Quotation and customer PO review linkage mismatch")

    return {
        "sales_order_number": _text(sales_order.sales_order_number),
        "quotation_number": _text(quotation.quotation_number),
        "quotation_document_number": _text(quotation.document_number),
        "customer_po_number": _text(po_review.customer_po_number),
        "customer_po_document_number": _text(po_review.document_number),
    }


def _resolve_fai_linkage_for_ncr(db: Session, ncr: NCR) -> tuple[FAIReport, dict[str, str]]:
    if ncr.reference_type != "FAIReport":
        raise QualityReportGenerationError("NCR report requires NCR to be linked to an FAI report")

    fai_report = _get_entity_or_raise(db, FAIReport, ncr.reference_id, "FAI report")
    sales_linkage = _resolve_sales_document_linkage(db, production_order_id=fai_report.production_order_id)
    return fai_report, sales_linkage


def _resolve_quality_chain_for_production_order(db: Session, *, production_order_id: int) -> tuple[FAIReport, NCR, CAPA]:
    fai_report = db.scalars(
        select(FAIReport)
        .where(
            FAIReport.production_order_id == production_order_id,
            FAIReport.is_deleted.is_(False),
        )
        .order_by(FAIReport.id.desc())
    ).first()
    if fai_report is None:
        raise QualityReportGenerationError("FAI linkage is mandatory for this report")

    ncr = db.scalars(
        select(NCR)
        .where(
            NCR.reference_type == "FAIReport",
            NCR.reference_id == fai_report.id,
            NCR.is_deleted.is_(False),
        )
        .order_by(NCR.id.desc())
    ).first()
    if ncr is None:
        raise QualityReportGenerationError("NCR linkage is mandatory for this report")

    capa = db.scalars(
        select(CAPA)
        .where(
            CAPA.ncr_id == ncr.id,
            CAPA.is_deleted.is_(False),
        )
        .order_by(CAPA.id.desc())
    ).first()
    if capa is None:
        raise QualityReportGenerationError("CAPA linkage is mandatory for this report")

    return fai_report, ncr, capa


def _resolve_prepared_by_username(db: Session, *, candidate_user_ids: list[int | None]) -> str:
    for user_id in candidate_user_ids:
        if user_id is None:
            continue
        user = db.scalar(
            select(User).where(
                User.id == int(user_id),
                User.is_deleted.is_(False),
            )
        )
        if user is None:
            continue
        if user.username:
            return user.username
        if user.email:
            return user.email
        return f"User#{user.id}"
    return "-"


def _validate_bundle_linkage(
    *,
    fir: FinalInspection,
    fai: FAIReport,
    ncr: NCR,
    capa: CAPA,
) -> None:
    if fir.production_order_id != fai.production_order_id:
        raise QualityReportGenerationError("FIR and FAI must reference the same production order")

    if ncr.reference_type != "FAIReport" or ncr.reference_id != fai.id:
        raise QualityReportGenerationError("NCR must be linked to the provided FAI report")

    if capa.ncr_id != ncr.id:
        raise QualityReportGenerationError("CAPA must be linked to the provided NCR")


def generate_fir_report(inspection_id: int) -> str:
    db = SessionLocal()
    try:
        inspection = _get_entity_or_raise(db, FinalInspection, inspection_id, "Final inspection")
        sales_linkage = _resolve_sales_document_linkage(db, production_order_id=inspection.production_order_id)
        fai, ncr, capa = _resolve_quality_chain_for_production_order(db, production_order_id=inspection.production_order_id)
        prepared_by = _resolve_prepared_by_username(
            db,
            candidate_user_ids=[inspection.created_by, inspection.inspected_by, inspection.updated_by],
        )
        output_dir = create_quality_report_directory("fir")
        output_file = output_dir / _linked_report_filename(
            "FIR",
            po=inspection.production_order_id,
            fai=fai.id,
            ncr=ncr.id,
            capa=capa.id,
        )
        rows = [
            ("Inspection ID", _text(inspection.id)),
            ("Production Order ID", _text(inspection.production_order_id)),
            ("Linked FAI ID", _text(fai.id)),
            ("Linked NCR ID", _text(ncr.id)),
            ("Linked CAPA ID", _text(capa.id)),
            ("Sales Order", sales_linkage["sales_order_number"]),
            ("Quotation", sales_linkage["quotation_number"]),
            ("Quotation Document", sales_linkage["quotation_document_number"]),
            ("Customer PO", sales_linkage["customer_po_number"]),
            ("Customer PO Document", sales_linkage["customer_po_document_number"]),
            ("Inspected By", _text(inspection.inspected_by)),
            ("Prepared By", prepared_by),
            ("Inspection Date", _text(inspection.inspection_date)),
            ("Result", _text(inspection.result.value if inspection.result else None)),
            ("Remarks", _text(inspection.remarks)),
            ("Created At", _text(inspection.created_at)),
        ]
        return _render_report(
            output_file,
            title="Final Inspection Report",
            subtitle="AS9100D Final Inspection Report",
            rows=rows,
        )
    finally:
        db.close()


def generate_fai_report(fai_id: int) -> str:
    db = SessionLocal()
    try:
        fai = _get_entity_or_raise(db, FAIReport, fai_id, "FAI report")
        ncr = db.scalars(
            select(NCR)
            .where(
                NCR.reference_type == "FAIReport",
                NCR.reference_id == fai.id,
                NCR.is_deleted.is_(False),
            )
            .order_by(NCR.id.desc())
        ).first()
        if ncr is None:
            raise QualityReportGenerationError("NCR linkage is mandatory for FAI report generation")

        capa = db.scalars(
            select(CAPA)
            .where(
                CAPA.ncr_id == ncr.id,
                CAPA.is_deleted.is_(False),
            )
            .order_by(CAPA.id.desc())
        ).first()
        if capa is None:
            raise QualityReportGenerationError("CAPA linkage is mandatory for FAI report generation")

        prepared_by = _resolve_prepared_by_username(
            db,
            candidate_user_ids=[fai.created_by, fai.inspected_by, fai.updated_by],
        )
        output_dir = create_quality_report_directory("fai")
        output_file = output_dir / _linked_report_filename(
            "FAI",
            po=fai.production_order_id,
            fai=fai.id,
            ncr=ncr.id,
            capa=capa.id,
        )
        sales_linkage = _resolve_sales_document_linkage(db, production_order_id=fai.production_order_id)
        rows = [
            ("FAI ID", _text(fai.id)),
            ("Production Order ID", _text(fai.production_order_id)),
            ("Linked NCR ID", _text(ncr.id)),
            ("Linked CAPA ID", _text(capa.id)),
            ("Sales Order", sales_linkage["sales_order_number"]),
            ("Quotation", sales_linkage["quotation_number"]),
            ("Quotation Document", sales_linkage["quotation_document_number"]),
            ("Customer PO", sales_linkage["customer_po_number"]),
            ("Customer PO Document", sales_linkage["customer_po_document_number"]),
            ("Drawing Number", _text(fai.drawing_number)),
            ("Revision", _text(fai.revision)),
            ("Part Number", _text(fai.part_number)),
            ("Inspected By", _text(fai.inspected_by)),
            ("Prepared By", prepared_by),
            ("Inspection Date", _text(fai.inspection_date)),
            ("Status", _text(fai.status.value if fai.status else None)),
            ("Attachment Path", _text(fai.attachment_path)),
        ]
        return _render_report(
            output_file,
            title="AS9102 FAI Report",
            subtitle="First Article Inspection Report",
            rows=rows,
        )
    finally:
        db.close()


def generate_ncr_report(ncr_id: int) -> str:
    db = SessionLocal()
    try:
        ncr = _get_entity_or_raise(db, NCR, ncr_id, "NCR")
        fai_report, sales_linkage = _resolve_fai_linkage_for_ncr(db, ncr)
        capa = db.scalars(
            select(CAPA)
            .where(
                CAPA.ncr_id == ncr.id,
                CAPA.is_deleted.is_(False),
            )
            .order_by(CAPA.id.desc())
        ).first()
        if capa is None:
            raise QualityReportGenerationError("CAPA linkage is mandatory for NCR report generation")

        prepared_by = _resolve_prepared_by_username(
            db,
            candidate_user_ids=[ncr.created_by, ncr.reported_by, ncr.updated_by],
        )
        output_dir = create_quality_report_directory("ncr")
        output_file = output_dir / _linked_report_filename(
            "NCR",
            po=fai_report.production_order_id,
            fai=fai_report.id,
            ncr=ncr.id,
            capa=capa.id,
        )
        rows = [
            ("NCR ID", _text(ncr.id)),
            ("Linked FAI ID", _text(fai_report.id)),
            ("Linked CAPA ID", _text(capa.id)),
            ("Production Order ID", _text(fai_report.production_order_id)),
            ("Sales Order", sales_linkage["sales_order_number"]),
            ("Quotation", sales_linkage["quotation_number"]),
            ("Customer PO", sales_linkage["customer_po_number"]),
            ("Reference Type", _text(ncr.reference_type)),
            ("Reference ID", _text(ncr.reference_id)),
            ("Defect Category", _text(ncr.defect_category.value if ncr.defect_category else None)),
            ("Reported By", _text(ncr.reported_by)),
            ("Prepared By", prepared_by),
            ("Reported Date", _text(ncr.reported_date)),
            ("Status", _text(ncr.status.value if ncr.status else None)),
            ("Description", _text(ncr.description)),
        ]
        return _render_report(
            output_file,
            title="NCR Report",
            subtitle="Non-Conformance Report",
            rows=rows,
        )
    finally:
        db.close()


def generate_capa_report(capa_id: int) -> str:
    db = SessionLocal()
    try:
        capa = _get_entity_or_raise(db, CAPA, capa_id, "CAPA")
        ncr = _get_entity_or_raise(db, NCR, capa.ncr_id, "NCR")
        fai_report, sales_linkage = _resolve_fai_linkage_for_ncr(db, ncr)
        prepared_by = _resolve_prepared_by_username(
            db,
            candidate_user_ids=[capa.created_by, capa.responsible_person, capa.updated_by],
        )
        output_dir = create_quality_report_directory("capa")
        output_file = output_dir / _linked_report_filename(
            "CAPA",
            po=fai_report.production_order_id,
            fai=fai_report.id,
            ncr=ncr.id,
            capa=capa.id,
        )
        rows = [
            ("CAPA ID", _text(capa.id)),
            ("NCR ID", _text(capa.ncr_id)),
            ("Linked FAI ID", _text(fai_report.id)),
            ("Production Order ID", _text(fai_report.production_order_id)),
            ("Sales Order", sales_linkage["sales_order_number"]),
            ("Quotation", sales_linkage["quotation_number"]),
            ("Customer PO", sales_linkage["customer_po_number"]),
            ("Action Type", _text(capa.action_type.value if capa.action_type else None)),
            ("Responsible Person", _text(capa.responsible_person)),
            ("Prepared By", prepared_by),
            ("Target Date", _text(capa.target_date)),
            ("Status", _text(capa.status.value if capa.status else None)),
            ("Created At", _text(capa.created_at)),
            ("Updated At", _text(capa.updated_at)),
        ]
        return _render_report(
            output_file,
            title="CAPA Report",
            subtitle="Corrective and Preventive Action Report",
            rows=rows,
        )
    finally:
        db.close()


def generate_audit_report(audit_id: int) -> str:
    db = SessionLocal()
    try:
        audit = _get_entity_or_raise(db, AuditReport, audit_id, "Audit report")
        prepared_by = _resolve_prepared_by_username(
            db,
            candidate_user_ids=[audit.created_by, audit.updated_by, audit.audit_plan.auditor if audit.audit_plan else None],
        )
        output_dir = create_quality_report_directory("audit")
        output_file = output_dir / _linked_report_filename(
            "AUDIT",
            ap=audit.audit_plan_id,
            ar=audit.id,
        )
        rows = [
            ("Audit Report ID", _text(audit.id)),
            ("Audit Plan ID", _text(audit.audit_plan_id)),
            ("Audit Area", _text(audit.audit_plan.audit_area if audit.audit_plan else None)),
            ("Planned Date", _text(audit.audit_plan.planned_date if audit.audit_plan else None)),
            ("Auditor", _text(audit.audit_plan.auditor if audit.audit_plan else None)),
            ("Prepared By", prepared_by),
            ("Status", _text(audit.status)),
            ("Findings", _text(audit.findings)),
            ("Created At", _text(audit.created_at)),
        ]
        return _render_report(
            output_file,
            title="Audit Report",
            subtitle="Quality Audit Report",
            rows=rows,
        )
    finally:
        db.close()


def generate_traceability_report(batch_number: str) -> str:
    output_dir = create_quality_report_directory("traceability")
    safe_batch_number = _safe_filename_fragment(batch_number)
    output_file = output_dir / _linked_report_filename("TRACEABILITY", batch=safe_batch_number)

    db = SessionLocal()
    try:
        try:
            traceability = get_batch_traceability(db, batch_number)
        except BatchTraceabilityError as exc:
            raise QualityReportGenerationError(str(exc)) from exc

        return _render_traceability_report(
            output_file,
            batch_number=batch_number,
            traceability=traceability,
        )
    finally:
        db.close()


def generate_quality_reports_bundle(
    *,
    inspection_id: int,
    fai_id: int,
    ncr_id: int,
    capa_id: int,
    audit_id: int,
    batch_number: str,
) -> str:
    bundle_dir = create_quality_report_directory("bundles")
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_batch_number = _safe_filename_fragment(batch_number)
    bundle_file = bundle_dir / f"quality_reports_bundle_{safe_batch_number}_{stamp}.zip"

    db = SessionLocal()
    try:
        fir = _get_entity_or_raise(db, FinalInspection, inspection_id, "Final inspection")
        fai = _get_entity_or_raise(db, FAIReport, fai_id, "FAI report")
        ncr = _get_entity_or_raise(db, NCR, ncr_id, "NCR")
        capa = _get_entity_or_raise(db, CAPA, capa_id, "CAPA")
        _validate_bundle_linkage(fir=fir, fai=fai, ncr=ncr, capa=capa)
        _resolve_sales_document_linkage(db, production_order_id=fai.production_order_id)

        traceability = get_batch_traceability(db, batch_number)
        linked_production_order_ids = {
            int(item.get("id"))
            for item in (traceability.get("production_orders") or [])
            if item.get("id") is not None
        }
        if fai.production_order_id not in linked_production_order_ids:
            raise QualityReportGenerationError(
                "Traceability batch is not linked to the same production order as FAI/NCR/CAPA"
            )
    finally:
        db.close()

    report_files = [
        generate_fir_report(inspection_id),
        generate_fai_report(fai_id),
        generate_ncr_report(ncr_id),
        generate_capa_report(capa_id),
        generate_audit_report(audit_id),
        generate_traceability_report(batch_number),
    ]

    with ZipFile(bundle_file, "w", compression=ZIP_DEFLATED) as archive:
        for report_path in report_files:
            report_file = Path(report_path)
            archive.write(report_file, arcname=report_file.name)

    return str(bundle_file)


__all__ = [
    "QualityReportGenerationError",
    "create_quality_report_directory",
    "ensure_quality_report_directories",
    "generate_fir_report",
    "generate_fai_report",
    "generate_ncr_report",
    "generate_capa_report",
    "generate_audit_report",
    "generate_traceability_report",
    "generate_quality_reports_bundle",
]