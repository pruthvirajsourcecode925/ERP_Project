from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.sales.pdf.quotation_config import COMPANY_INFO, LOGO_PATH


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


@dataclass
class QuotationLineItem:
    sr_no: int
    description: str
    moq: Decimal
    uom: str
    unit_rate: Decimal
    line_total: Decimal | None = None


@dataclass
class QuotationPDFPayload:
    quotation_no: str
    quotation_date: date
    ref_no: str
    enquiry_ref: str
    prepared_by: str
    customer_info: dict[str, str]
    line_items: Iterable[QuotationLineItem]
    gst_amount: Decimal
    commercial_terms: list[str]
    fai_required: bool
    coc_required: bool
    traceability_required: bool
    terms_and_conditions: list[str]


def _as_money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _item_total(item: QuotationLineItem) -> Decimal:
    if item.line_total is not None:
        return item.line_total
    return item.moq * item.unit_rate


def _yes_no(flag: bool) -> str:
    return "Yes" if flag else "No"


def _prepared_by_name(prepared_by: str) -> str:
    if "@" not in prepared_by:
        return prepared_by
    local_part = prepared_by.split("@", 1)[0]
    name = " ".join(segment for segment in local_part.replace("_", ".").split(".") if segment)
    return name.title() if name else prepared_by


def generate_quotation_pdf(payload: QuotationPDFPayload) -> dict[str, str]:
    exports_dir = _project_root() / "exports" / "quotations"
    exports_dir.mkdir(parents=True, exist_ok=True)

    output_file = exports_dir / f"quotation_{payload.quotation_no}.pdf"

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Quotation {payload.quotation_no}",
    )

    styles = getSampleStyleSheet()
    normal = styles["BodyText"]
    normal.fontSize = 9
    normal.leading = 11

    company_title = ParagraphStyle(
        "CompanyTitle",
        parent=styles["Heading2"],
        alignment=1,
        fontSize=14,
        leading=16,
        textColor=colors.black,
        spaceAfter=2,
    )

    section_title = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading4"],
        fontSize=10,
        leading=12,
        textColor=colors.black,
        spaceBefore=5,
        spaceAfter=3,
    )

    story = []

    # 1-3) Header: logo left, company centered, document box right
    logo_cell = Paragraph("", normal)
    if LOGO_PATH.exists():
        logo_cell = Image(str(LOGO_PATH), width=120, height=48)

    company_name = COMPANY_INFO.get("name", "Company Name")
    website = COMPANY_INFO.get("website", "")
    company_lines = [company_name]
    if website:
        company_lines.append(f"Website: {website}")

    company_block = Paragraph(
        "<br/>".join([f"<b>{company_lines[0]}</b>"] + company_lines[1:]),
        ParagraphStyle("CompanyBlock", parent=normal, alignment=1, fontSize=11, leading=13),
    )

    document_box = Table(
        [
            [Paragraph("<b>QUOTATION</b>", normal)],
            [Paragraph(f"Quotation No: {payload.quotation_no}", normal)],
            [Paragraph(f"Date: {payload.quotation_date.isoformat()}", normal)],
            [Paragraph(f"Ref No: {payload.ref_no}", normal)],
            [Paragraph(f"Enquiry Ref: {payload.enquiry_ref}", normal)],
            [Paragraph(f"Prepared By: {_prepared_by_name(payload.prepared_by)}", normal)],
        ],
        colWidths=[58 * mm],
    )
    document_box.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    top_table = Table([[logo_cell, company_block, document_box]], colWidths=[34 * mm, 96 * mm, 58 * mm])
    top_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(top_table)
    story.append(Spacer(1, 4))

    # 4) Two-column company/customer section
    address_lines = COMPANY_INFO.get("address_lines", [])
    email = COMPANY_INFO.get("email", "")
    phone = COMPANY_INFO.get("phone", "")
    company_info_lines = [company_name]
    company_info_lines.extend(address_lines)
    if email:
        company_info_lines.append(f"Email: {email}")
    if phone:
        company_info_lines.append(f"Mobile: {phone}")
    company_info_block = Paragraph(
        "<b>Company Info</b><br/>" + "<br/>".join(company_info_lines),
        normal,
    )

    customer_lines = [
        payload.customer_info.get("name", ""),
        payload.customer_info.get("address_line_1", ""),
        payload.customer_info.get("address_line_2", ""),
        payload.customer_info.get("city_state_zip", ""),
        payload.customer_info.get("country", ""),
        f"Contact: {payload.customer_info.get('contact_person', '-')}",
        f"Email: {payload.customer_info.get('email', '-')}",
    ]
    customer_block = Paragraph(
        "<b>Customer Info</b><br/>" + "<br/>".join([line for line in customer_lines if line]),
        normal,
    )

    info_table = Table([[company_info_block, customer_block]], colWidths=[94 * mm, 94 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7F7F7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(info_table)

    # 5) Line item table
    story.append(Paragraph("Line Items", section_title))
    line_table = [["Sr No", "Description", "MOQ", "UOM", "Unit Rate", "Line Total"]]

    subtotal = Decimal("0.00")
    for item in payload.line_items:
        lt = _item_total(item)
        subtotal += lt
        line_table.append(
            [
                str(item.sr_no),
                item.description,
                str(item.moq),
                item.uom,
                _as_money(item.unit_rate),
                _as_money(lt),
            ]
        )

    grand_total = subtotal + payload.gst_amount
    line_table.append(["", "", "", "", "Subtotal", _as_money(subtotal)])
    line_table.append(["", "", "", "", "Grand Total", _as_money(grand_total)])

    items_table = Table(line_table, repeatRows=1, colWidths=[16 * mm, 86 * mm, 20 * mm, 16 * mm, 26 * mm, 30 * mm])
    items_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (4, -2), (5, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(items_table)

    # 6) Commercial terms
    story.append(Paragraph("Commercial Terms", section_title))
    if payload.commercial_terms:
        for idx, term in enumerate(payload.commercial_terms, start=1):
            story.append(Paragraph(f"{idx}. {term}", normal))
    else:
        story.append(Paragraph("No commercial terms provided.", normal))

    # 7) Quality clauses
    story.append(Paragraph("Quality Clauses", section_title))
    quality_table = Table(
        [
            ["FAI Required", _yes_no(payload.fai_required)],
            ["COC Required", _yes_no(payload.coc_required)],
            ["Traceability Required", _yes_no(payload.traceability_required)],
        ],
        colWidths=[60 * mm, 128 * mm],
    )
    quality_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFEFEF")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.append(quality_table)

    # 8) Editable T&C
    story.append(Paragraph("Terms & Conditions", section_title))
    if payload.terms_and_conditions:
        for idx, clause in enumerate(payload.terms_and_conditions, start=1):
            story.append(Paragraph(f"{idx}. {clause}", normal))
    else:
        story.append(Paragraph("No terms provided.", normal))

    # 9) Signature block bottom-right
    story.append(Spacer(1, 8))
    signature_table = Table(
        [["Prepared By", _prepared_by_name(payload.prepared_by)]],
        colWidths=[38 * mm, 55 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#EFEFEF")),
                ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    right_align_table = Table([["", signature_table]], colWidths=[95 * mm, 93 * mm])
    right_align_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(right_align_table)

    doc.build(story)
    return {"file_path": str(output_file)}
