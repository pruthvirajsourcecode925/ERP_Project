from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class VerificationChecklistItem:
    label: str
    passed: bool
    remarks: str | None = None


@dataclass
class CustomerPOReviewPDFData:
    po_review_number: str
    review_date: date
    company_info: dict[str, str]
    customer_info: dict[str, str]
    po_details: dict[str, str]
    verification_checklist: list[VerificationChecklistItem]
    accepted: bool
    acceptance_declaration: str
    signature_block: dict[str, str]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _status_text(value: bool) -> str:
    return "PASS" if value else "FAIL"


def generate_customer_po_review_pdf(data: CustomerPOReviewPDFData) -> dict[str, str]:
    exports_dir = _project_root() / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    output_file = exports_dir / f"po_review_{data.po_review_number}.pdf"

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Customer PO Review {data.po_review_number}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitlePOReview",
        parent=styles["Title"],
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionPOReview",
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
    document_title = "Customer PO Review"
    approved_by = data.signature_block.get("approved_by", "-")

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
    story.append(Paragraph("Customer PO Review", title_style))
    story.append(Paragraph(f"PO Review No: <b>{data.po_review_number}</b>", normal))
    story.append(Paragraph(f"Review Date: <b>{data.review_date.isoformat()}</b>", normal))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Header", section_style))
    company_lines = [
        data.company_info.get("name", ""),
        data.company_info.get("address_line_1", ""),
        data.company_info.get("address_line_2", ""),
        data.company_info.get("city_state_zip", ""),
        data.company_info.get("country", ""),
        f"Phone: {data.company_info.get('phone', '-')}",
        f"Email: {data.company_info.get('email', '-')}",
    ]
    story.append(Paragraph("<br/>".join([line for line in company_lines if line]), normal))

    story.append(Paragraph("Customer Info", section_style))
    customer_lines = [
        data.customer_info.get("name", ""),
        data.customer_info.get("address_line_1", ""),
        data.customer_info.get("address_line_2", ""),
        data.customer_info.get("city_state_zip", ""),
        data.customer_info.get("country", ""),
        f"Contact: {data.customer_info.get('contact_person', '-')}",
        f"Email: {data.customer_info.get('email', '-')}",
    ]
    story.append(Paragraph("<br/>".join([line for line in customer_lines if line]), normal))

    story.append(Paragraph("PO Details", section_style))
    po_table = Table(
        [
            ["PO Number", data.po_details.get("po_number", "-")],
            ["PO Date", data.po_details.get("po_date", "-")],
            ["Quotation Ref", data.po_details.get("quotation_ref", "-")],
            ["Enquiry Ref", data.po_details.get("enquiry_ref", "-")],
            ["Currency", data.po_details.get("currency", "-")],
            ["PO Value", data.po_details.get("po_value", "-")],
        ],
        colWidths=[45 * mm, 144 * mm],
    )
    po_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.append(po_table)

    story.append(Paragraph("Verification Checklist", section_style))
    checklist_rows = [["#", "Checkpoint", "Status", "Remarks"]]
    for idx, item in enumerate(data.verification_checklist, start=1):
        checklist_rows.append([str(idx), item.label, _status_text(item.passed), item.remarks or "-"])

    checklist_table = Table(checklist_rows, repeatRows=1, colWidths=[12 * mm, 95 * mm, 24 * mm, 58 * mm])
    checklist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.2),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(checklist_table)

    story.append(Paragraph("Acceptance Declaration", section_style))
    acceptance_text = "ACCEPTED" if data.accepted else "NOT ACCEPTED"
    story.append(Paragraph(f"Decision: <b>{acceptance_text}</b>", normal))
    story.append(Paragraph(data.acceptance_declaration, normal))

    story.append(Paragraph("Signature Block", section_style))
    signature_table = Table(
        [
            ["Prepared By", data.signature_block.get("prepared_by", "-")],
            ["Reviewed By", data.signature_block.get("reviewed_by", "-")],
            ["Approved By", data.signature_block.get("approved_by", "-")],
            ["Date", data.signature_block.get("date", data.review_date.isoformat())],
        ],
        colWidths=[45 * mm, 144 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.append(signature_table)

    doc.build(story)

    return {"file_path": str(output_file)}
