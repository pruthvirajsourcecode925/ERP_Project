from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class VerificationChecklistItem:
    sr_no: int
    item: str
    status: str
    remarks: str


@dataclass
class CustomerPOReviewPDFPayload:
    po_review_no: str
    review_date: date
    ref_no: str
    mode: str
    customer_info: dict[str, str]
    po_info: dict[str, str]
    verification_items: Iterable[VerificationChecklistItem]
    acceptance_declaration: str
    approved_by: str
    approval_date: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _logo_path() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "logo.png"


def generate_customer_po_review_pdf(payload: CustomerPOReviewPDFPayload) -> dict[str, str]:
    exports_dir = _project_root() / "exports" / "po_reviews"
    exports_dir.mkdir(parents=True, exist_ok=True)

    output_file = exports_dir / f"po_review_{payload.po_review_no}.pdf"

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Customer PO Review {payload.po_review_no}",
    )

    styles = getSampleStyleSheet()
    normal = styles["BodyText"]
    normal.fontSize = 9
    normal.leading = 11

    section_title = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading4"],
        fontSize=10,
        leading=12,
        textColor=colors.black,
        spaceBefore=6,
        spaceAfter=4,
    )

    story = []

    logo_cell = Paragraph("", normal)
    logo = _logo_path()
    if logo.exists():
        logo_cell = Image(str(logo), width=120, height=48)

    company_block = Paragraph(
        "<b>MAULI INDUSTRIES</b>",
        ParagraphStyle("CompanyBlock", parent=normal, alignment=1, fontSize=13, leading=15),
    )

    info_box = Table(
        [
            [Paragraph("<b>CUSTOMER PO REVIEW &amp; ACCEPTANCE</b>", normal)],
            [Paragraph(f"PO Review No: {payload.po_review_no}", normal)],
            [Paragraph(f"Review Date: {payload.review_date.isoformat()}", normal)],
            [Paragraph(f"Ref No: {payload.ref_no}", normal)],
            [Paragraph(f"Mode: {payload.mode}", normal)],
        ],
        colWidths=[70 * mm],
    )
    info_box.setStyle(
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

    top_table = Table(
        [[logo_cell, company_block, info_box]],
        colWidths=[34 * mm, 84 * mm, 70 * mm],
    )
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

    company_address = Paragraph(
        "Plot no. H3/1<br/>"
        "NEARS AIMA OFFICE<br/>"
        "MIDC Ambad<br/>"
        "Nashik-422009<br/>"
        "Email: mauliind.mfg@gmail.com<br/>"
        "Mobile: +91-9604091397<br/>"
        "Website: www.mauliind.com",
        ParagraphStyle("CompanyAddress", parent=normal, alignment=1, fontSize=9, leading=11),
    )
    story.append(Spacer(1, 4))
    story.append(company_address)
    story.append(Spacer(1, 6))

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
        "<b>Customer Information</b><br/>" + "<br/>".join([line for line in customer_lines if line]),
        normal,
    )

    po_lines = [
        f"PO Number: {payload.po_info.get('po_number', '')}",
        f"PO Date: {payload.po_info.get('po_date', '')}",
        f"Quotation Ref: {payload.po_info.get('quotation_ref', '')}",
        f"Enquiry Ref: {payload.po_info.get('enquiry_ref', '')}",
        f"Currency: {payload.po_info.get('currency', '')}",
        f"PO Value: {payload.po_info.get('po_value', '')}",
    ]
    po_block = Paragraph(
        "<b>PO Information</b><br/>" + "<br/>".join([line for line in po_lines if line]),
        normal,
    )

    info_table = Table([[customer_block, po_block]], colWidths=[94 * mm, 94 * mm])
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

    story.append(Paragraph("Verification Checklist", section_title))
    checklist_rows = [["Sr No", "Verification Item", "Status", "Remarks"]]
    for item in payload.verification_items:
        checklist_rows.append(
            [
                str(item.sr_no),
                item.item,
                item.status,
                item.remarks,
            ]
        )

    checklist_table = Table(
        checklist_rows,
        repeatRows=1,
        colWidths=[16 * mm, 88 * mm, 28 * mm, 56 * mm],
    )
    checklist_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(checklist_table)

    story.append(Paragraph("Acceptance Declaration", section_title))
    story.append(Paragraph(payload.acceptance_declaration, normal))

    story.append(Spacer(1, 10))
    signature_table = Table(
        [
            ["Approved By:", payload.approved_by],
            ["Date:", payload.approval_date],
            ["For MAULI INDUSTRIES", ""],
        ],
        colWidths=[40 * mm, 60 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -2), 0.5, colors.black),
                ("GRID", (0, -1), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFEFEF")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    right_align_table = Table([['', signature_table]], colWidths=[88 * mm, 100 * mm])
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
