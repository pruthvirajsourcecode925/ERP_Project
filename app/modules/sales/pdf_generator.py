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


@dataclass
class QuotationLineItem:
    line_no: int
    item_code: str
    description: str
    quantity: Decimal
    uom: str
    unit_price: Decimal
    line_total: Decimal | None = None


@dataclass
class QuotationPDFData:
    quotation_number: str
    quotation_date: date
    company_info: dict[str, str]
    customer_info: dict[str, str]
    enquiry_reference: str
    line_items: Iterable[QuotationLineItem]
    delivery_terms: str
    payment_terms: str
    gst_details: str
    validity: str
    fai_required: bool
    coc_required: bool
    traceability_required: bool
    terms_and_conditions: list[str]
    approved_by: str | None = None
    prepared_by: str | None = None


def _currency(value: Decimal) -> str:
    return f"{value:,.2f}"


def _line_total(item: QuotationLineItem) -> Decimal:
    if item.line_total is not None:
        return item.line_total
    return item.quantity * item.unit_price


def _checkbox_text(required: bool) -> str:
    return "Required" if required else "Not Required"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def generate_quotation_pdf(data: QuotationPDFData) -> dict[str, str]:
    exports_dir = _project_root() / "exports" / "quotations"
    exports_dir.mkdir(parents=True, exist_ok=True)

    output_file = exports_dir / f"quotation_{data.quotation_number}.pdf"

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Quotation {data.quotation_number}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleAS9100",
        parent=styles["Title"],
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionAS9100",
        parent=styles["Heading3"],
        fontSize=10.5,
        leading=12,
        textColor=colors.HexColor("#111827"),
        spaceBefore=6,
        spaceAfter=4,
    )
    normal = styles["BodyText"]
    normal.fontSize = 9
    normal.leading = 11

    story = []

    company_name = data.company_info.get("name", "Company Name")
    document_title = "Quotation"
    approved_by = data.approved_by or data.company_info.get("approved_by", "-")
    prepared_by = data.prepared_by or data.company_info.get("prepared_by", "-")

    logo_path = data.company_info.get("logo_path")
    header_left = []
    if logo_path and Path(logo_path).exists():
        header_left.append(Image(logo_path, width=24 * mm, height=24 * mm))
    else:
        header_left.append(Paragraph("", normal))

    header_right = Paragraph(
        f"<b>{company_name}</b><br/><b>Document Title:</b> {document_title}<br/><b>Approved By:</b> {approved_by}",
        normal,
    )
    header_table = Table([[header_left[0], header_right]], colWidths=[28 * mm, 161 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(header_table)
    story.append(Paragraph("Quotation", title_style))
    story.append(Paragraph(f"Quotation No: <b>{data.quotation_number}</b>", normal))
    story.append(Paragraph(f"Date: <b>{data.quotation_date.isoformat()}</b>", normal))
    story.append(Spacer(1, 4))

    company_lines = [
        data.company_info.get("name", ""),
        data.company_info.get("address_line_1", ""),
        data.company_info.get("address_line_2", ""),
        data.company_info.get("city_state_zip", ""),
        data.company_info.get("country", ""),
        f"Phone: {data.company_info.get('phone', '-')}",
        f"Email: {data.company_info.get('email', '-')}",
        f"GSTIN: {data.company_info.get('gstin', '-')}",
    ]
    company_block = "<br/>".join([line for line in company_lines if line])

    customer_lines = [
        data.customer_info.get("name", ""),
        data.customer_info.get("address_line_1", ""),
        data.customer_info.get("address_line_2", ""),
        data.customer_info.get("city_state_zip", ""),
        data.customer_info.get("country", ""),
        f"Contact: {data.customer_info.get('contact_person', '-')}",
        f"Email: {data.customer_info.get('email', '-')}",
    ]
    customer_block = "<br/>".join([line for line in customer_lines if line])

    info_table = Table(
        [
            [Paragraph("<b>Company Info</b>", normal), Paragraph("<b>Customer Info</b>", normal)],
            [Paragraph(company_block, normal), Paragraph(customer_block, normal)],
        ],
        colWidths=[94 * mm, 95 * mm],
    )
    info_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(info_table)

    story.append(Paragraph("Enquiry Ref", section_style))
    story.append(Paragraph(f"Reference: <b>{data.enquiry_reference}</b>", normal))

    story.append(Paragraph("Line Item Table", section_style))
    table_data = [["Line", "Item Code", "Description", "Qty", "UOM", "Unit Price", "Line Total"]]

    subtotal = Decimal("0.00")
    for item in data.line_items:
        total = _line_total(item)
        subtotal += total
        table_data.append(
            [
                str(item.line_no),
                item.item_code,
                item.description,
                str(item.quantity),
                item.uom,
                _currency(item.unit_price),
                _currency(total),
            ]
        )

    table_data.append(["", "", "", "", "", "Subtotal", _currency(subtotal)])

    item_table = Table(table_data, repeatRows=1, colWidths=[18 * mm, 26 * mm, 57 * mm, 16 * mm, 16 * mm, 28 * mm, 28 * mm])
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (5, -1), (6, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(item_table)

    story.append(Paragraph("Commercial Terms", section_style))
    terms_table = Table(
        [
            ["Delivery Terms", data.delivery_terms],
            ["Payment Terms", data.payment_terms],
            ["GST", data.gst_details],
            ["Validity", data.validity],
        ],
        colWidths=[40 * mm, 149 * mm],
    )
    terms_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(terms_table)

    story.append(Paragraph("Quality Clauses", section_style))
    quality_table = Table(
        [
            ["FAI Required", _checkbox_text(data.fai_required)],
            ["COC Required", _checkbox_text(data.coc_required)],
            ["Traceability Required", _checkbox_text(data.traceability_required)],
        ],
        colWidths=[70 * mm, 119 * mm],
    )
    quality_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.append(quality_table)

    story.append(Paragraph("Editable Terms & Conditions", section_style))
    if data.terms_and_conditions:
        for idx, clause in enumerate(data.terms_and_conditions, start=1):
            story.append(Paragraph(f"{idx}. {clause}", normal))
    else:
        story.append(Paragraph("No additional terms provided.", normal))

    story.append(Paragraph("Signature Block", section_style))
    signature_table = Table(
        [["Prepared By", prepared_by]],
        colWidths=[40 * mm, 149 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.append(signature_table)

    doc.build(story)

    return {"file_path": str(output_file)}
