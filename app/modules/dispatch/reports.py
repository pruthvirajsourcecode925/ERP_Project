from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.modules.dispatch.models import DeliveryChallan, DispatchChecklist, DispatchItem, DispatchOrder, Invoice, ShipmentTracking
from app.modules.sales.models import Customer, CustomerPOReview, Quotation, QuotationItem, QuotationTermsSetting, SalesOrder
from app.modules.sales.pdf.quotation_config import COMPANY_INFO, LOGO_PATH


class DispatchReportGenerationError(Exception):
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_filename_fragment(value: str) -> str:
    text = value.strip()
    safe = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("_")
    return "".join(safe).strip("_") or "unknown"


def _currency(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{Decimal(value):,.2f}"


def _text(value: object | None) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    return str(value)


def _storage_dir(folder_name: str) -> Path:
    target = _project_root() / "storage" / "dispatch_documents" / folder_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DispatchTitle",
            parent=styles["Title"],
            fontSize=13,
            leading=15,
            alignment=1,
            textColor=colors.HexColor("#111827"),
            spaceAfter=0,
        ),
        "company_name": ParagraphStyle(
            "DispatchCompanyName",
            parent=styles["Heading2"],
            fontSize=13,
            leading=15,
            alignment=1,
            textColor=colors.black,
            spaceAfter=2,
        ),
        "company_meta": ParagraphStyle(
            "DispatchCompanyMeta",
            parent=styles["BodyText"],
            fontSize=9,
            leading=11,
            alignment=1,
            textColor=colors.black,
        ),
        "company_meta_right": ParagraphStyle(
            "DispatchCompanyMetaRight",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=10.5,
            alignment=2,
            textColor=colors.black,
        ),
        "section": ParagraphStyle(
            "DispatchSection",
            parent=styles["Heading3"],
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#111827"),
            spaceBefore=6,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "DispatchBody",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=10.5,
            textColor=colors.black,
        ),
        "body_center": ParagraphStyle(
            "DispatchBodyCenter",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=10.5,
            alignment=1,
            textColor=colors.black,
        ),
        "small": ParagraphStyle(
            "DispatchSmall",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.black,
        ),
    }


def _get_dispatch_order(db: Session, dispatch_order_id: int) -> DispatchOrder:
    dispatch_order = db.scalar(
        select(DispatchOrder).where(
            DispatchOrder.id == dispatch_order_id,
            DispatchOrder.is_deleted.is_(False),
        )
    )
    if not dispatch_order:
        raise DispatchReportGenerationError("DispatchOrder not found")
    return dispatch_order


def _get_sales_order(db: Session, sales_order_id: int) -> SalesOrder:
    sales_order = db.scalar(
        select(SalesOrder).where(
            SalesOrder.id == sales_order_id,
            SalesOrder.is_deleted.is_(False),
        )
    )
    if not sales_order:
        raise DispatchReportGenerationError("SalesOrder not found")
    return sales_order


def _get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.is_deleted.is_(False),
        )
    )
    if not customer:
        raise DispatchReportGenerationError("Customer not found")
    return customer


def _get_invoice(db: Session, dispatch_order_id: int) -> Invoice:
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.dispatch_order_id == dispatch_order_id,
            Invoice.is_deleted.is_(False),
        )
    )
    if not invoice:
        raise DispatchReportGenerationError("Invoice not found")
    return invoice


def _get_delivery_challan(db: Session, dispatch_order_id: int) -> DeliveryChallan:
    challan = db.scalar(
        select(DeliveryChallan).where(
            DeliveryChallan.dispatch_order_id == dispatch_order_id,
            DeliveryChallan.is_deleted.is_(False),
        )
    )
    if not challan:
        raise DispatchReportGenerationError("DeliveryChallan not found")
    return challan


def _get_dispatch_items(db: Session, dispatch_order_id: int) -> list[DispatchItem]:
    return list(
        db.scalars(
            select(DispatchItem)
            .where(
                DispatchItem.dispatch_order_id == dispatch_order_id,
                DispatchItem.is_deleted.is_(False),
            )
            .order_by(DispatchItem.line_number.asc(), DispatchItem.id.asc())
        )
    )


def _get_latest_tracking(db: Session, dispatch_order_id: int) -> ShipmentTracking | None:
    return db.scalars(
        select(ShipmentTracking)
        .where(
            ShipmentTracking.dispatch_order_id == dispatch_order_id,
            ShipmentTracking.is_deleted.is_(False),
        )
        .order_by(ShipmentTracking.shipment_date.desc(), ShipmentTracking.id.desc())
    ).first()


def _get_customer_po_review(db: Session, customer_po_review_id: int) -> CustomerPOReview | None:
    return db.scalar(
        select(CustomerPOReview).where(
            CustomerPOReview.id == customer_po_review_id,
            CustomerPOReview.is_deleted.is_(False),
        )
    )


def _get_quotation(db: Session, quotation_id: int) -> Quotation | None:
    return db.scalar(
        select(Quotation).where(
            Quotation.id == quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )


def _get_quotation_items(db: Session, quotation_id: int) -> list[QuotationItem]:
    return list(
        db.scalars(
            select(QuotationItem)
            .where(
                QuotationItem.quotation_id == quotation_id,
                QuotationItem.is_deleted.is_(False),
            )
            .order_by(QuotationItem.line_no.asc(), QuotationItem.id.asc())
        )
    )


def _get_latest_terms_setting(db: Session) -> dict[str, object]:
    setting = db.scalar(
        select(QuotationTermsSetting)
        .where(QuotationTermsSetting.is_deleted.is_(False))
        .order_by(QuotationTermsSetting.updated_at.desc(), QuotationTermsSetting.id.desc())
    )
    if not setting:
        return {}

    try:
        payload = json.loads(setting.terms_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _address_lines_from_company_info(company_info: dict[str, object]) -> list[str]:
    raw_lines = company_info.get("address_lines")
    if isinstance(raw_lines, list):
        lines = [str(line).strip() for line in raw_lines if str(line).strip()]
        if lines:
            return lines

    address = str(company_info.get("company_address") or "").strip()
    if address:
        return [part.strip() for part in address.split(",") if part.strip()]

    return [
        "Plot no. H3/1 Near AIMA Office",
        "MIDC Ambad Nashik-422009",
    ]


def _report_config(db: Session) -> dict[str, object]:
    payload = _get_latest_terms_setting(db)
    company = dict(COMPANY_INFO)
    company_overrides = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    company.update(company_overrides)

    website = str(company.get("website") or "").strip()
    if not website or "@" in website:
        website = "www.mauliind.com"

    return {
        "company_name": str(company.get("company_name") or company.get("name") or "MAULI INDUSTRIES").strip() or "MAULI INDUSTRIES",
        "address_lines": _address_lines_from_company_info(company),
        "email": str(company.get("company_email") or company.get("email") or "mauliind.mfg@gmail.com").strip() or "mauliind.mfg@gmail.com",
        "phone": str(company.get("company_phone") or company.get("phone") or "+91-9604091397").strip() or "+91-9604091397",
        "website": website,
        "logo_path": str(LOGO_PATH) if LOGO_PATH.exists() else None,
        "gst_rate": payload.get("gst_rate"),
        "invoice_admin_message": str(
            payload.get("invoice_admin_message") or payload.get("admin_message") or "Thank you for your business."
        ).strip(),
        "challan_receiving_instructions": payload.get("challan_receiving_instructions") or payload.get("receiving_instructions"),
        "vehicle_number": str(payload.get("vehicle_number") or "-").strip() or "-",
        "checked_by_name": str(payload.get("checked_by") or "").strip(),
        "authorized_signatory_name": str(payload.get("authorized_signatory") or "").strip(),
    }


def _logo_cell(styles: dict[str, ParagraphStyle]) -> object:
    logo_path = LOGO_PATH
    if logo_path.exists():
        # Increased logo size by 50% for dispatch invoice/challan documents.
        return Image(str(logo_path), width=87, height=63)
    return Paragraph("", styles["body"])


def _build_company_header(styles: dict[str, ParagraphStyle], config: dict[str, object], document_title: str) -> list[object]:
    company_lines = [
        *[str(line) for line in config["address_lines"]],
        f"Email: {config['email']}",
        f"Mobile: {config['phone']}",
        f"Website: {config['website']}",
    ]
    center_block = Paragraph(
        f"<b>{config['company_name']}</b><br/>{document_title}",
        styles["company_name"],
    )
    right_block = Paragraph("<br/>".join(company_lines), styles["company_meta_right"])
    header_table = Table(
        [[_logo_cell(styles), center_block, right_block]],
        colWidths=[110, 275, 150],
    )
    header_table.setStyle(
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
    return [header_table, Spacer(1, 8)]


def _paragraph(value: object | None, style: ParagraphStyle) -> Paragraph:
    text = _text(value)
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def _metadata_table(rows: list[tuple[str, object]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(f"<b>{label}</b>", styles["body"]), _paragraph(value, styles["body"])] for label, value in rows]
    table = Table(data, colWidths=[130, 405])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _customer_table(customer: Customer, styles: dict[str, ParagraphStyle], *, shipping: bool = False) -> Table:
    address = customer.shipping_address if shipping else customer.billing_address
    rows = [
        ("Customer", customer.name),
        ("Customer Code", customer.customer_code),
        ("Address", address or "-"),
        ("Email", customer.email or "-"),
        ("Phone", customer.phone or "-"),
    ]
    return _metadata_table(rows, styles)


def _get_unit_price_map(db: Session, sales_order: SalesOrder) -> tuple[dict[tuple[int, str], Decimal], dict[str, Decimal]]:
    exact_map: dict[tuple[int, str], Decimal] = {}
    fallback_map: dict[str, Decimal] = {}
    quotation = _get_quotation(db, sales_order.quotation_id)
    if not quotation:
        return exact_map, fallback_map

    for item in _get_quotation_items(db, quotation.id):
        exact_map[(item.line_no, item.item_code)] = Decimal(item.unit_price)
        fallback_map.setdefault(item.item_code, Decimal(item.unit_price))
    return exact_map, fallback_map


def _resolve_unit_price(exact_map: dict[tuple[int, str], Decimal], fallback_map: dict[str, Decimal], item: DispatchItem) -> Decimal | None:
    return exact_map.get((item.line_number, item.item_code)) or fallback_map.get(item.item_code)


def _fallback_price_map_from_invoice(items: list[DispatchItem], invoice: Invoice | None) -> dict[int, Decimal]:
    if invoice is None:
        return {}

    total_quantity = sum((Decimal(item.quantity) for item in items), Decimal("0.000"))
    if total_quantity <= 0:
        return {}

    subtotal = Decimal(invoice.subtotal)
    if subtotal <= 0:
        return {}

    unit_price = subtotal / total_quantity
    return {item.id: unit_price for item in items}


def _build_invoice_item_table(
    *,
    items: list[DispatchItem],
    exact_price_map: dict[tuple[int, str], Decimal],
    fallback_price_map: dict[str, Decimal],
    invoice_price_map: dict[int, Decimal] | None,
    styles: dict[str, ParagraphStyle],
) -> tuple[Table, Decimal]:
    data: list[list[object]] = [[
        Paragraph("<b>Item</b>", styles["small"]),
        Paragraph("<b>Description</b>", styles["small"]),
        Paragraph("<b>Batch No</b>", styles["small"]),
        Paragraph("<b>Quantity</b>", styles["small"]),
        Paragraph("<b>Unit Price</b>", styles["small"]),
        Paragraph("<b>Total</b>", styles["small"]),
    ]]
    subtotal = Decimal("0.00")
    for item in items:
        unit_price = _resolve_unit_price(exact_price_map, fallback_price_map, item)
        if unit_price is None and invoice_price_map:
            unit_price = invoice_price_map.get(item.id)
        line_total = (Decimal(item.quantity) * unit_price) if unit_price is not None else Decimal("0.00")
        subtotal += line_total
        data.append(
            [
                _paragraph(item.item_code, styles["small"]),
                _paragraph(item.description or "-", styles["small"]),
                _paragraph(item.lot_number or item.serial_number or "-", styles["small"]),
                Paragraph(f"{Decimal(item.quantity):,.3f} {item.uom}", styles["small"]),
                Paragraph(_currency(unit_price), styles["small"]),
                Paragraph(_currency(line_total), styles["small"]),
            ]
        )

    table = Table(data, repeatRows=1, colWidths=[80, 175, 70, 50, 70, 90])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table, subtotal


def _build_challan_item_table(
    *,
    items: list[DispatchItem],
    exact_price_map: dict[tuple[int, str], Decimal],
    fallback_price_map: dict[str, Decimal],
    invoice_price_map: dict[int, Decimal] | None,
    styles: dict[str, ParagraphStyle],
) -> Table:
    data: list[list[object]] = [[
        Paragraph("<b>Item</b>", styles["small"]),
        Paragraph("<b>Description</b>", styles["small"]),
        Paragraph("<b>Batch</b>", styles["small"]),
        Paragraph("<b>Quantity</b>", styles["small"]),
        Paragraph("<b>Amount</b>", styles["small"]),
    ]]
    for item in items:
        unit_price = _resolve_unit_price(exact_price_map, fallback_price_map, item)
        if unit_price is None and invoice_price_map:
            unit_price = invoice_price_map.get(item.id)
        amount = (Decimal(item.quantity) * unit_price) if unit_price is not None else None
        data.append(
            [
                _paragraph(item.item_code, styles["small"]),
                _paragraph(item.description or "-", styles["small"]),
                _paragraph(item.lot_number or item.serial_number or "-", styles["small"]),
                Paragraph(f"{Decimal(item.quantity):,.3f} {item.uom}", styles["small"]),
                Paragraph(_currency(amount), styles["small"]),
            ]
        )

    table = Table(data, repeatRows=1, colWidths=[90, 195, 70, 70, 110])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _summary_table(*, subtotal: Decimal, gst_amount: Decimal | None, grand_total: Decimal, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [[Paragraph("<b>Subtotal</b>", styles["body"]), Paragraph(_currency(subtotal), styles["body"] )]]
    if gst_amount is not None:
        rows.append([Paragraph("<b>GST</b>", styles["body"]), Paragraph(_currency(gst_amount), styles["body"])])
    rows.append([Paragraph("<b>Grand Total</b>", styles["body"]), Paragraph(_currency(grand_total), styles["body"])])
    table = Table(rows, colWidths=[120, 120], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _user_display(db: Session, user_id: int | None) -> str:
    if not user_id:
        return "-"
    user = db.scalar(select(User).where(User.id == user_id, User.is_deleted.is_(False)))
    if not user:
        return "-"
    role = db.scalar(select(Role).where(Role.id == user.role_id))
    if role:
        return f"{user.username} ({role.name})"
    return user.username


def _default_authorized_signatory(db: Session) -> str:
    user = db.scalar(
        select(User)
        .join(Role, Role.id == User.role_id)
        .where(
            User.is_deleted.is_(False),
            User.is_active.is_(True),
            Role.name.in_(["Admin", "Dispatch"]),
        )
        .order_by(User.id.asc())
    )
    if not user:
        return "-"
    return _user_display(db, user.id)


def _signatories(
    db: Session,
    *,
    dispatch_order: DispatchOrder,
    prepared_by_user_id: int | None,
    checked_by_override: str | None,
    config: dict[str, object],
) -> tuple[str, str, str]:
    prepared_by = _user_display(db, prepared_by_user_id or dispatch_order.updated_by or dispatch_order.created_by)
    checked_by = (checked_by_override or "").strip()
    if not checked_by:
        checked_by = str(config.get("checked_by_name") or "").strip() or "-"
    authorized = _user_display(db, dispatch_order.released_by)
    if authorized == "-" and config.get("authorized_signatory_name"):
        authorized = str(config["authorized_signatory_name"])
    if authorized == "-":
        authorized = _default_authorized_signatory(db)
    return prepared_by, checked_by, authorized


def _receiving_instructions(config: dict[str, object]) -> list[str]:
    payload = config.get("challan_receiving_instructions")
    if isinstance(payload, list):
        values = [str(item).strip() for item in payload if str(item).strip()]
        if values:
            return values
    if isinstance(payload, str) and payload.strip():
        return [line.strip() for line in payload.splitlines() if line.strip()]
    return [
        "Verify batch numbers",
        "Check quantity before signing",
        "Report damage immediately",
    ]


def _report_path_within_storage(file_path: Path) -> Path:
    storage_root = (_project_root() / "storage" / "dispatch_documents").resolve()
    resolved = file_path.resolve()
    if storage_root not in resolved.parents:
        raise DispatchReportGenerationError("Generated report path is outside allowed storage folder")
    return resolved


def generate_invoice(
    db: Session,
    dispatch_order_id: int,
    prepared_by_user_id: int | None = None,
    checked_by_name: str | None = None,
) -> str:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    sales_order = _get_sales_order(db, dispatch_order.sales_order_id)
    customer = _get_customer(db, sales_order.customer_id)
    invoice = _get_invoice(db, dispatch_order_id)
    items = _get_dispatch_items(db, dispatch_order_id)
    tracking = _get_latest_tracking(db, dispatch_order_id)
    po_review = _get_customer_po_review(db, sales_order.customer_po_review_id)
    config = _report_config(db)
    styles = _styles()
    exact_map, fallback_map = _get_unit_price_map(db, sales_order)
    invoice_price_map = _fallback_price_map_from_invoice(items, invoice)
    item_table, computed_subtotal = _build_invoice_item_table(
        items=items,
        exact_price_map=exact_map,
        fallback_price_map=fallback_map,
        invoice_price_map=invoice_price_map,
        styles=styles,
    )
    gst_rate = config.get("gst_rate")
    gst_amount: Decimal | None = None
    if gst_rate is not None:
        gst_amount = (computed_subtotal * Decimal(str(gst_rate))) / Decimal("100")
    elif Decimal(invoice.tax_amount) > 0:
        gst_amount = Decimal(invoice.tax_amount)

    if computed_subtotal == Decimal("0.00") and Decimal(invoice.subtotal) > 0:
        computed_subtotal = Decimal(invoice.subtotal)
    grand_total = computed_subtotal + (gst_amount or Decimal("0.00"))
    if grand_total == Decimal("0.00") and Decimal(invoice.total_amount) > 0:
        grand_total = Decimal(invoice.total_amount)
    prepared_by, checked_by, authorized = _signatories(
        db,
        dispatch_order=dispatch_order,
        prepared_by_user_id=prepared_by_user_id,
        checked_by_override=checked_by_name,
        config=config,
    )

    output_dir = _storage_dir("invoices")
    output_file = _report_path_within_storage(
        output_dir / f"{_safe_filename_fragment(invoice.invoice_number)}_{_safe_filename_fragment(customer.name)}.pdf"
    )
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        topMargin=30,
        bottomMargin=30,
        leftMargin=30,
        rightMargin=30,
        title=f"Invoice {invoice.invoice_number}",
    )

    story: list[object] = []
    story.extend(_build_company_header(styles, config, "INVOICE"))
    story.append(Paragraph("Invoice Metadata", styles["section"]))
    story.append(
        _metadata_table(
            [
                ("Invoice number", invoice.invoice_number),
                ("Date", invoice.invoice_date),
                ("Sales order", sales_order.sales_order_number),
                ("PO reference", po_review.customer_po_number if po_review else "-"),
                ("Tracking ID", tracking.tracking_number if tracking else "-"),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("Customer Details", styles["section"]))
    story.append(_customer_table(customer, styles))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Material Table", styles["section"]))
    story.append(item_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Total Summary", styles["section"]))
    story.append(_summary_table(subtotal=computed_subtotal, gst_amount=gst_amount, grand_total=grand_total, styles=styles))
    if gst_amount is not None:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Optional GST", styles["section"]))
        rate_text = f"{gst_rate}%" if gst_rate is not None else "As stored in invoice"
        story.append(Paragraph(f"GST Applied: {rate_text}", styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Regard and Notes", styles["section"]))
    story.append(Paragraph(str(config["invoice_admin_message"]), styles["body"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Signature", styles["section"]))
    signature_table = Table(
        [["Prepared By", "Checked By", "Authorized Signatory"], [prepared_by, checked_by, ""]],
        colWidths=[178, 178, 179],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    story.append(signature_table)

    doc.build(story)
    return str(output_file)


def generate_delivery_challan(
    db: Session,
    dispatch_order_id: int,
    prepared_by_user_id: int | None = None,
    checked_by_name: str | None = None,
) -> str:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    sales_order = _get_sales_order(db, dispatch_order.sales_order_id)
    customer = _get_customer(db, sales_order.customer_id)
    challan = _get_delivery_challan(db, dispatch_order_id)
    items = _get_dispatch_items(db, dispatch_order_id)
    tracking = _get_latest_tracking(db, dispatch_order_id)
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.dispatch_order_id == dispatch_order_id,
            Invoice.is_deleted.is_(False),
        )
    )
    config = _report_config(db)
    styles = _styles()
    exact_map, fallback_map = _get_unit_price_map(db, sales_order)
    invoice_price_map = _fallback_price_map_from_invoice(items, invoice)
    item_table = _build_challan_item_table(
        items=items,
        exact_price_map=exact_map,
        fallback_price_map=fallback_map,
        invoice_price_map=invoice_price_map,
        styles=styles,
    )
    prepared_by, checked_by, _ = _signatories(
        db,
        dispatch_order=dispatch_order,
        prepared_by_user_id=prepared_by_user_id,
        checked_by_override=checked_by_name,
        config=config,
    )

    output_dir = _storage_dir("challans")
    output_file = _report_path_within_storage(
        output_dir / f"CHALLAN_{_safe_filename_fragment(challan.challan_number)}_{_safe_filename_fragment(customer.name)}.pdf"
    )
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        topMargin=30,
        bottomMargin=30,
        leftMargin=30,
        rightMargin=30,
        title=f"Delivery Challan {challan.challan_number}",
    )

    story: list[object] = []
    story.extend(_build_company_header(styles, config, "DELIVERY CHALLAN"))
    story.append(Paragraph("Metadata", styles["section"]))
    story.append(
        _metadata_table(
            [
                ("Challan number", challan.challan_number),
                ("Date", challan.issue_date),
                ("Transporter", tracking.carrier_name if tracking and tracking.carrier_name else "-"),
                ("Vehicle number", config["vehicle_number"]),
                ("Tracking ID", tracking.tracking_number if tracking else "-"),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("Customer Details", styles["section"]))
    story.append(_customer_table(customer, styles, shipping=True))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Item Table", styles["section"]))
    story.append(item_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Receiving Instructions", styles["section"]))
    for index, instruction in enumerate(_receiving_instructions(config), start=1):
        story.append(Paragraph(f"{index}. {instruction}", styles["body"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Signature Section", styles["section"]))
    signature_table = Table(
        [["Prepared By", "Checked By", "Receiver Signature"], [prepared_by, checked_by, ""]],
        colWidths=[178, 178, 179],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    story.append(signature_table)

    doc.build(story)
    return str(output_file)