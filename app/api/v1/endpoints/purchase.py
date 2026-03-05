from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import textwrap

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.api.deps import get_db, require_roles
from app.modules.purchase.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, Supplier
from app.modules.sales.pdf.quotation_config import COMPANY_INFO, LOGO_PATH
from app.services.auth_service import add_audit_log
from app.services.purchase_service import (
    PurchaseBusinessRuleError,
    add_po_item,
    approve_supplier,
    create_purchase_order,
    create_supplier,
    generate_purchase_order_pdf,
    get_purchase_summary,
    remove_po_item,
    soft_delete_po,
    soft_delete_supplier,
    update_po_status,
    update_supplier,
)

router = APIRouter(prefix="/purchase", tags=["purchase"])


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]



def _purchase_order_exports_dir() -> Path:
    return _project_root() / "exports" / "purchase_orders"



def _ensure_purchase_order_pdf_path_in_exports(file_path: str) -> Path:
    allowed_dir = _purchase_order_exports_dir().resolve()
    resolved_file = Path(file_path).resolve()
    if allowed_dir not in resolved_file.parents and resolved_file.parent != allowed_dir:
        raise HTTPException(status_code=500, detail="Stored purchase order PDF path is outside allowed export folder")
    return resolved_file


def _generate_purchase_order_pdf_file(
    *,
    po: PurchaseOrder,
    supplier_name: str,
    created_by_name: str,
    supplier_contact_person: str | None,
    supplier_address: str | None,
    supplier_email: str | None,
    supplier_phone: str | None,
    items: list[PurchaseOrderItem],
) -> str:
    exports_dir = _purchase_order_exports_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)

    output_file = (exports_dir / f"{po.po_number}.pdf").resolve()

    pdf = canvas.Canvas(str(output_file), pagesize=A4)
    page_width, page_height = A4
    margin_left = 40
    margin_right = 40
    content_width = page_width - margin_left - margin_right
    y = page_height - 40
    page_index = 1

    first_page_min_item_rows = 8
    first_page_max_item_rows = 10
    footer_reserved_height = 170
    minimum_quality_rows = 4

    def _draw_section_title(title: str) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margin_left, y, title)
        y -= 18

    def _ensure_space(min_y: int) -> None:
        nonlocal y, page_index
        if y < min_y:
            pdf.showPage()
            y = page_height - 40
            page_index += 1

    def _format_date(dt: date | datetime | str | None) -> str:
        if not dt:
            return "-"
        if isinstance(dt, str):
            return dt
        try:
            return dt.strftime("%d-%b-%Y")
        except Exception:
            return str(dt)

    def _truncate_text_for_width(
        value: str,
        max_width: float,
        *,
        font_name: str,
        font_size: int,
    ) -> str:
        text = str(value or "-")
        if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
            return text
        ellipsis = "..."
        if pdfmetrics.stringWidth(ellipsis, font_name, font_size) > max_width:
            return ""
        truncated = text
        while truncated and pdfmetrics.stringWidth(f"{truncated}{ellipsis}", font_name, font_size) > max_width:
            truncated = truncated[:-1]
        return f"{truncated}{ellipsis}"

    def _fit_text(value: str, max_width: float, *, font_name: str = "Helvetica", font_size: int = 8) -> str:
        return _truncate_text_for_width(value, max_width, font_name=font_name, font_size=font_size)

    def _fit_text_with_font(
        value: str,
        max_width: float,
        *,
        font_name: str = "Helvetica",
        start_font_size: int = 8,
        min_font_size: int = 6,
    ) -> tuple[str, int]:
        text = str(value or "-")
        for font_size in range(start_font_size, min_font_size - 1, -1):
            if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
                return text, font_size
        fitted = _truncate_text_for_width(
            text,
            max_width,
            font_name=font_name,
            font_size=min_font_size,
        )
        return fitted, min_font_size

    def _wrap_text_to_width(
        value: str,
        max_width: float,
        *,
        font_name: str = "Helvetica",
        font_size: int = 9,
    ) -> list[str]:
        raw_text = str(value or "-").strip()
        if not raw_text:
            return ["-"]
        wrapped_lines: list[str] = []
        for raw_line in raw_text.splitlines():
            words = raw_line.split()
            if not words:
                wrapped_lines.append("")
                continue
            current = _fit_text(words[0], max_width, font_name=font_name, font_size=font_size)
            for word in words[1:]:
                candidate = f"{current} {word}".strip()
                if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                    current = candidate
                else:
                    wrapped_lines.append(current)
                    current = _fit_text(word, max_width, font_name=font_name, font_size=font_size)
            wrapped_lines.append(current)
        return wrapped_lines or ["-"]

    def _company_field(new_key: str, legacy_key: str) -> str:
        value = COMPANY_INFO.get(new_key) or COMPANY_INFO.get(legacy_key)
        if value is None:
            return "-"
        value_str = str(value).strip()
        return value_str or "-"

    def _company_address_lines() -> list[str]:
        address = COMPANY_INFO.get("company_address")
        if address:
            wrapped = textwrap.wrap(str(address).strip(), width=72)
            return wrapped or ["-"]
        legacy_lines = COMPANY_INFO.get("address_lines", [])
        if isinstance(legacy_lines, list):
            cleaned_lines = [str(line).strip() for line in legacy_lines if str(line).strip()]
            if cleaned_lines:
                return cleaned_lines
        return ["-"]

    def _measure_panel_height(rows: list[tuple[str, str]]) -> float:
        heading_height = 18
        top_pad = 6
        bottom_pad = 6
        line_height = 11
        row_gap = 3
        total = heading_height + top_pad + bottom_pad
        for _, value in rows:
            wrapped = textwrap.wrap(value or "-", width=28) or ["-"]
            total += (len(wrapped) * line_height) + row_gap
        return max(total, 92)

    def _draw_label_value_rows(
        x: float,
        top_y: float,
        width: float,
        heading: str,
        rows: list[tuple[str, str]],
        *,
        panel_height: float,
    ) -> float:
        heading_height = 18
        value_x = x + 68
        label_x = x + 6
        inner_top = top_y - heading_height - 8
        line_height = 11
        row_gap = 3

        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.7)
        pdf.rect(x, top_y - panel_height, width, panel_height, fill=0, stroke=1)
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(x, top_y - heading_height, width, heading_height, fill=1, stroke=1)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 6, top_y - 12, heading)

        current_y = inner_top
        min_y = top_y - panel_height + 8
        for label, value in rows:
            wrapped = textwrap.wrap(value or "-", width=28) or ["-"]
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(label_x, current_y, f"{label}:")
            pdf.setFont("Helvetica", 8)
            pdf.drawString(value_x, current_y, wrapped[0])
            current_y -= line_height
            for line in wrapped[1:]:
                if current_y <= min_y:
                    break
                pdf.drawString(value_x, current_y, line)
                current_y -= line_height
            current_y -= row_gap

        return top_y - panel_height - 10

    def _draw_po_meta_table(top_y: float) -> float:
        row_height = 18
        table_width = content_width
        col_width = table_width / 4
        headers = ["PO Number", "PO Date", "Revision", "Date"]
        values = [
            po.po_number or "-",
            _format_date(po.po_date),
            str(getattr(po, "revision", None) or "00"),
            _format_date(datetime.now().date()),
        ]

        pdf.setLineWidth(0.7)
        pdf.setStrokeColor(colors.black)
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(margin_left, top_y - row_height, table_width, row_height, fill=1, stroke=1)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 8)

        for idx, header in enumerate(headers):
            x = margin_left + idx * col_width
            pdf.drawString(x + 3, top_y - 12, header)
            pdf.line(x, top_y - (2 * row_height), x, top_y)
        pdf.line(margin_left + table_width, top_y - (2 * row_height), margin_left + table_width, top_y)
        pdf.line(margin_left, top_y, margin_left + table_width, top_y)
        pdf.line(margin_left, top_y - row_height, margin_left + table_width, top_y - row_height)
        pdf.line(margin_left, top_y - (2 * row_height), margin_left + table_width, top_y - (2 * row_height))

        pdf.setFont("Helvetica", 8)
        for idx, value in enumerate(values):
            x = margin_left + idx * col_width
            pdf.drawString(x + 3, top_y - row_height - 12, value)

        return top_y - (2 * row_height) - 10

    def _draw_items_table_header(table_top_y: float) -> float:
        pdf.setLineWidth(0.7)
        pdf.setStrokeColor(colors.black)
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(margin_left, table_top_y - row_height, content_width, row_height, fill=1, stroke=1)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 8)
        col_x = margin_left
        text_y = table_top_y - 12
        for header, width in columns:
            fitted_header, _ = _fit_text_with_font(
                header,
                width - 6,
                font_name="Helvetica-Bold",
                start_font_size=8,
                min_font_size=7,
            )
            pdf.drawString(col_x + 2, text_y, fitted_header)
            pdf.line(col_x, table_top_y - row_height, col_x, table_top_y)
            col_x += width
        pdf.line(col_x, table_top_y - row_height, col_x, table_top_y)
        pdf.line(margin_left, table_top_y, col_x, table_top_y)
        pdf.line(margin_left, table_top_y - row_height, col_x, table_top_y - row_height)
        pdf.setFont("Helvetica", 8)
        return table_top_y - row_height

    def _draw_quality_requirements_table() -> None:
        nonlocal y
        title = "Supplier Quality Requirements"
        raw_quality_text = (po.supplier_quality_requirements or "-").strip()
        if "\n" in raw_quality_text:
            explicit_lines = [line.strip() for line in raw_quality_text.splitlines() if line.strip()]
            body_lines: list[str] = []
            body_line_sizes: list[int] = []
            for line in explicit_lines:
                fitted, font_size = _fit_text_with_font(
                    line,
                    content_width - 12,
                    font_name="Helvetica",
                    start_font_size=9,
                    min_font_size=6,
                )
                body_lines.append(fitted)
                body_line_sizes.append(font_size)
        else:
            body_lines = _wrap_text_to_width(
                raw_quality_text or "-",
                content_width - 12,
                font_name="Helvetica",
                font_size=9,
            )
            body_line_sizes = [9] * len(body_lines)

        while len(body_lines) < minimum_quality_rows:
            body_lines.append("")
            body_line_sizes.append(9)

        heading_height = 18
        line_height = 12
        body_pad = 6
        table_height = heading_height + (len(body_lines) * line_height) + (body_pad * 2)
        if y - table_height < footer_reserved_height:
            pdf.showPage()
            y = page_height - 40

        top_y = y
        pdf.setLineWidth(0.7)
        pdf.setStrokeColor(colors.black)
        pdf.rect(margin_left, top_y - table_height, content_width, table_height, fill=0, stroke=1)
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(margin_left, top_y - heading_height, content_width, heading_height, fill=1, stroke=1)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin_left + 4, top_y - 12, title)

        text_y = top_y - heading_height - body_pad - 2
        for line, font_size in zip(body_lines, body_line_sizes):
            pdf.setFont("Helvetica", font_size)
            pdf.drawString(margin_left + 4, text_y, line)
            text_y -= line_height
        y = top_y - table_height - 10

    def _draw_signature_table() -> None:
        nonlocal y
        table_height = 62
        heading_row_height = 20
        row_height = 21
        if y - table_height < 45:
            pdf.showPage()
            y = page_height - 40

        top_y = y
        mid_x = margin_left + (content_width / 2)
        bottom_y = top_y - table_height
        row1_y = top_y - heading_row_height
        row2_y = row1_y - row_height

        pdf.setLineWidth(0.7)
        pdf.setStrokeColor(colors.black)
        pdf.rect(margin_left, bottom_y, content_width, table_height, fill=0, stroke=1)
        pdf.line(mid_x, bottom_y, mid_x, top_y)
        pdf.line(margin_left, row1_y, margin_left + content_width, row1_y)
        pdf.line(margin_left, row2_y, margin_left + content_width, row2_y)

        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin_left + 6, top_y - 13, "Authorized By (Buyer)")
        pdf.drawString(mid_x + 6, top_y - 13, "Supplier Acknowledgement")

        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_left + 6, row1_y - 13, f"Name: {_fit_text(created_by_name or '-', (content_width / 2) - 38, font_size=9)}")
        pdf.drawString(mid_x + 6, row1_y - 13, "Name:")
        pdf.drawString(margin_left + 6, row2_y - 13, "Signature:")
        pdf.drawString(mid_x + 6, row2_y - 13, "Signature:")

        y = bottom_y - 8

    # --- Header with logo on top-left, centered company name and PO title (as in template) ---
    logo_path = LOGO_PATH
    logo_width, logo_height = 50, 50
    header_top = y
    if logo_path.exists():
        pdf.drawImage(
            str(logo_path),
            margin_left,
            header_top - logo_height,
            width=logo_width,
            height=logo_height,
            mask='auto',
        )

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(page_width / 2, header_top - 14, _company_field("company_name", "name"))
    pdf.drawCentredString(page_width / 2, header_top - 32, "PURCHASE ORDER")
    y = header_top - max(logo_height, 40) - 10

    panel_gap = 12
    panel_width = (content_width - panel_gap) / 2
    panel_top = y

    buyer_rows = [
        ("Company", _company_field("company_name", "name")),
        ("Address", ", ".join(_company_address_lines())),
        ("Contact Person", created_by_name or "-"),
        ("Email", _company_field("company_email", "email")),
        ("Phone", _company_field("company_phone", "phone")),
    ]
    supplier_rows = [
        ("Company", supplier_name or "-"),
        ("Address", (supplier_address or "-").strip() or "-"),
        ("Contact Person", (supplier_contact_person or "-").strip() or "-"),
        ("Email", (supplier_email or "-").strip() or "-"),
        ("Phone", (supplier_phone or "-").strip() or "-"),
    ]

    panel_height = max(_measure_panel_height(buyer_rows), _measure_panel_height(supplier_rows))
    _ensure_space(panel_height + 80)
    left_panel_bottom = _draw_label_value_rows(
        margin_left,
        panel_top,
        panel_width,
        "BUYER INFORMATION",
        buyer_rows,
        panel_height=panel_height,
    )
    right_panel_bottom = _draw_label_value_rows(
        margin_left + panel_width + panel_gap,
        panel_top,
        panel_width,
        "SUPPLIER INFORMATION",
        supplier_rows,
        panel_height=panel_height,
    )
    y = min(left_panel_bottom, right_panel_bottom)

    y = _draw_po_meta_table(y)
    _ensure_space(120)
    fixed_columns = [
        ("Item", 30),
        ("Part Number", 78),
        ("Description", 165),
        ("Rev", 28),
        ("Qty", 40),
        ("Unit Price", 70),
    ]
    fixed_width_total = sum(width for _, width in fixed_columns)
    columns = fixed_columns + [("Delivery Date", content_width - fixed_width_total)]
    table_x = margin_left
    table_y = y
    row_height = 18

    table_y = _draw_items_table_header(table_y)

    rows_drawn = 0
    current_page_row_count = 0
    if not items:
        col_x = table_x + sum(width for _, width in columns)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(table_x + 2, table_y - 12, "No items available")
        pdf.line(table_x, table_y, col_x, table_y)
        pdf.line(table_x, table_y - row_height, col_x, table_y - row_height)
        table_y -= row_height
        rows_drawn += 1
        current_page_row_count += 1
    else:
        delivery_date = _format_date(po.expected_delivery_date)
        for index, item in enumerate(items, start=1):
            if table_y < footer_reserved_height or (
                page_index == 1 and current_page_row_count >= first_page_max_item_rows
            ):
                pdf.showPage()
                y = page_height - 40
                page_index += 1
                table_x = margin_left
                table_y = y
                table_y = _draw_items_table_header(table_y)
                current_page_row_count = 0

            part_number = getattr(item, "part_number", None) or "-"
            description = item.description or "-"
            rev = getattr(item, "rev", None) or "-"
            qty = str(item.quantity)
            unit_price = f"{float(item.unit_price):.2f}"

            row_values = [
                str(index),
                part_number,
                description,
                rev,
                qty,
                unit_price,
                delivery_date,
            ]
            col_x = table_x
            row_text_y = table_y - 12
            for idx, (value, (col_name, width)) in enumerate(zip(row_values, columns)):
                max_width = width - (8 if col_name == "Unit Price" else 6)
                fitted_value, font_size = _fit_text_with_font(
                    value,
                    max_width,
                    font_name="Helvetica",
                    start_font_size=7,
                    min_font_size=6,
                )
                pdf.setFont("Helvetica", font_size)
                if col_name == "Qty":
                    pdf.drawCentredString(col_x + width / 2, row_text_y, fitted_value)
                elif col_name == "Unit Price":
                    pdf.drawRightString(col_x + width - 4, row_text_y, fitted_value)
                elif col_name == "Delivery Date":
                    pdf.drawCentredString(col_x + width / 2, row_text_y, fitted_value)
                else:
                    pdf.drawString(col_x + 2, row_text_y, fitted_value)
                pdf.line(col_x, table_y - row_height, col_x, table_y)
                col_x += width
            pdf.line(col_x, table_y - row_height, col_x, table_y)
            pdf.line(table_x, table_y, col_x, table_y)
            pdf.line(table_x, table_y - row_height, col_x, table_y - row_height)
            table_y -= row_height
            rows_drawn += 1
            current_page_row_count += 1

    if page_index == 1 and current_page_row_count < first_page_min_item_rows:
        col_x_final = table_x + sum(width for _, width in columns)
        for _ in range(first_page_min_item_rows - current_page_row_count):
            if table_y < footer_reserved_height:
                break
            col_x = table_x
            for _, width in columns:
                pdf.line(col_x, table_y - row_height, col_x, table_y)
                col_x += width
            pdf.line(col_x, table_y - row_height, col_x, table_y)
            pdf.line(table_x, table_y, col_x_final, table_y)
            pdf.line(table_x, table_y - row_height, col_x_final, table_y - row_height)
            table_y -= row_height

    # Add Total Amount row below items table
    y = table_y - 10
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin_left, y, f"Total Amount: {float(po.total_amount):.2f}")
    y -= 14

    _draw_quality_requirements_table()
    _draw_signature_table()

    pdf.save()
    return str(output_file)


class SupplierCreate(BaseModel):
    supplier_code: str
    supplier_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_approved: bool = False
    is_active: bool = True


class SupplierApprove(BaseModel):
    approved: bool = True
    approval_remarks: str | None = None
    quality_acknowledged: bool | None = None


class SupplierUpdate(BaseModel):
    supplier_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None


class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    supplier_name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_approved: bool
    approval_date: datetime | None
    approved_by: int | None
    approval_remarks: str | None
    quality_acknowledged: bool
    last_evaluation_date: datetime | None
    evaluation_score: int | None
    evaluation_remarks: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    sales_order_id: int | None = None
    po_date: date
    expected_delivery_date: date | None = None
    remarks: str | None = None
    quality_notes: str | None = None
    supplier_quality_requirements: str | None = None


class PurchaseOrderItemCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrderStatusUpdate(BaseModel):
    status: PurchaseOrderStatus


class PurchaseOrderItemOut(BaseModel):
    id: int
    purchase_order_id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    sales_order_id: int | None
    po_date: date
    expected_delivery_date: date | None
    status: PurchaseOrderStatus
    total_amount: Decimal
    remarks: str | None
    quality_notes: str | None
    supplier_quality_requirements: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderDetailOut(PurchaseOrderOut):
    items: list[PurchaseOrderItemOut] = []


class PurchaseSummaryOut(BaseModel):
    total_suppliers: int
    total_approved_suppliers: int
    total_draft_pos: int
    total_issued_pos: int
    total_closed_pos: int


@router.post("/supplier", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier_endpoint(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = create_supplier(
            db,
            supplier_code=payload.supplier_code,
            supplier_name=payload.supplier_name,
            contact_person=payload.contact_person,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            is_approved=payload.is_approved,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_CREATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={"supplier_code": supplier.supplier_code, "supplier_name": supplier.supplier_name},
    )

    return supplier


@router.post("/supplier/{supplier_id}/approve", response_model=SupplierOut)
def approve_supplier_endpoint(
    supplier_id: int,
    payload: SupplierApprove,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = approve_supplier(
            db,
            supplier_id=supplier_id,
            approved=payload.approved,
            approval_remarks=payload.approval_remarks,
            quality_acknowledged=payload.quality_acknowledged,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_APPROVAL_UPDATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={
            "is_approved": supplier.is_approved,
            "approval_date": supplier.approval_date.isoformat() if supplier.approval_date else None,
            "approved_by": supplier.approved_by,
            "quality_acknowledged": supplier.quality_acknowledged,
        },
    )

    return supplier


@router.get("/supplier/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted.is_(False))
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.patch("/supplier/{supplier_id}", response_model=SupplierOut)
def update_supplier_endpoint(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = update_supplier(
            db,
            supplier_id=supplier_id,
            supplier_name=payload.supplier_name,
            contact_person=payload.contact_person,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            is_active=payload.is_active,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_UPDATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={"supplier_name": supplier.supplier_name, "is_active": supplier.is_active},
    )
    return supplier


@router.delete("/supplier/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_endpoint(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        soft_delete_supplier(db, supplier_id=supplier_id, updated_by=current_user.id)
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_DELETED",
        table_name="suppliers",
        record_id=supplier_id,
        new_value={"is_deleted": True},
    )


@router.get("/supplier", response_model=list[SupplierOut])
def list_suppliers(
    is_approved: bool | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    stmt = select(Supplier).where(Supplier.is_deleted.is_(False))
    if is_approved is not None:
        stmt = stmt.where(Supplier.is_approved.is_(is_approved))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active.is_(is_active))

    suppliers = db.scalars(stmt.order_by(Supplier.id.desc()).offset(skip).limit(limit)).all()
    return suppliers


@router.get("/summary", response_model=PurchaseSummaryOut)
def get_purchase_summary_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    return get_purchase_summary(db)


@router.post("/order", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order_endpoint(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        po = create_purchase_order(
            db,
            supplier_id=payload.supplier_id,
            sales_order_id=payload.sales_order_id,
            po_date=payload.po_date,
            expected_delivery_date=payload.expected_delivery_date,
            remarks=payload.remarks,
            quality_notes=payload.quality_notes,
            supplier_quality_requirements=payload.supplier_quality_requirements,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_CREATED",
        table_name="purchase_orders",
        record_id=po.id,
        new_value={"po_number": po.po_number, "status": po.status.value},
    )

    return po


@router.post("/order/{purchase_order_id}/item", response_model=PurchaseOrderItemOut, status_code=status.HTTP_201_CREATED)
def add_po_item_endpoint(
    purchase_order_id: int,
    payload: PurchaseOrderItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        item = add_po_item(
            db,
            purchase_order_id=purchase_order_id,
            description=payload.description,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return item


@router.put("/order/{purchase_order_id}/status", response_model=PurchaseOrderOut)
def update_po_status_endpoint(
    purchase_order_id: int,
    payload: PurchaseOrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        po = update_po_status(
            db,
            purchase_order_id=purchase_order_id,
            new_status=payload.status,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_STATUS_CHANGED",
        table_name="purchase_orders",
        record_id=po.id,
        new_value={"status": po.status.value},
    )

    return po


@router.get("/order", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    status: PurchaseOrderStatus | None = Query(None),
    supplier_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    stmt = select(PurchaseOrder).where(PurchaseOrder.is_deleted.is_(False))
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

    orders = db.scalars(stmt.order_by(PurchaseOrder.id.desc()).offset(skip).limit(limit)).all()
    return orders


@router.delete("/order/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order_endpoint(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        soft_delete_po(db, purchase_order_id=purchase_order_id, updated_by=current_user.id)
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_DELETED",
        table_name="purchase_orders",
        record_id=purchase_order_id,
        new_value={"is_deleted": True},
    )


@router.delete("/order/{purchase_order_id}/item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_po_item_endpoint(
    purchase_order_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        remove_po_item(
            db,
            purchase_order_id=purchase_order_id,
            item_id=item_id,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/order/{purchase_order_id}", response_model=PurchaseOrderDetailOut)
def get_purchase_order(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.is_deleted.is_(False),
        )
    )
    if not po:
        raise HTTPException(status_code=404, detail="PurchaseOrder not found")

    items = db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == purchase_order_id,
            PurchaseOrderItem.is_deleted.is_(False),
        )
    ).all()

    return PurchaseOrderDetailOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        sales_order_id=po.sales_order_id,
        po_date=po.po_date,
        expected_delivery_date=po.expected_delivery_date,
        status=po.status,
        total_amount=po.total_amount,
        remarks=po.remarks,
        quality_notes=po.quality_notes,
        supplier_quality_requirements=po.supplier_quality_requirements,
        created_at=po.created_at,
        items=[PurchaseOrderItemOut.model_validate(item) for item in items],
    )


@router.get("/order/{purchase_order_id}/download")
def download_purchase_order_pdf(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.is_deleted.is_(False),
        )
    )
    if not po:
        raise HTTPException(status_code=404, detail="PurchaseOrder not found")
    if po.status not in (PurchaseOrderStatus.ISSUED, PurchaseOrderStatus.CLOSED):
        raise HTTPException(
            status_code=400,
            detail="PurchaseOrder PDF can be downloaded only when status is Issued or Closed",
        )

    was_already_generated = bool(po.po_document_path)
    try:
        generated_file_path = generate_purchase_order_pdf(
            db,
            purchase_order=po,
            pdf_builder=_generate_purchase_order_pdf_file,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    file_path = _ensure_purchase_order_pdf_path_in_exports(generated_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored purchase order PDF file not found")

    if not was_already_generated:
        add_audit_log(
            db=db,
            user_id=current_user.id,
            action="PURCHASE_ORDER_PDF_GENERATED",
            table_name="purchase_orders",
            record_id=po.id,
            new_value={"po_document_path": str(file_path)},
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=f"{po.po_number}.pdf",
    )
