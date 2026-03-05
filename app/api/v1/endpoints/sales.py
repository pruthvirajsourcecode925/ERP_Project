from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.sales.models import (
    ContractReview,
    ContractReviewStatus,
    CustomerPOReview,
    CustomerPOReviewStatus,
    Enquiry,
    EnquiryStatus,
    Quotation,
    QuotationStatus,
    QuotationTermsSetting,
    SalesOrder,
    SalesOrderStatus,
)
from app.modules.sales.pdf.quotation_pdf import (
    QuotationLineItem as QuotationPdfLineItem,
    QuotationPDFPayload,
    generate_quotation_pdf,
)
from app.modules.sales.pdf.po_review_pdf import (
    CustomerPOReviewPDFPayload,
    VerificationChecklistItem as POReviewChecklistItem,
    generate_customer_po_review_pdf,
)
from app.services.auth_service import add_audit_log
from app.services.sales_service import (
    SalesBusinessRuleError,
    validate_contract_review_for_quotation,
    create_quotation,
    create_sales_order,
    _generate_document_number,
)

router = APIRouter(prefix="/sales", tags=["sales"])

DEFAULT_QUOTATION_TERMS = [
    "Material and process certificates shall be supplied as required.",
    "Any deviation requires written customer approval.",
    "Lead time starts after PO acceptance and technical closure.",
]


def _ensure_pdf_path_in_exports(file_path: str, subfolder: str) -> str:
    project_root = Path(__file__).resolve().parents[4]
    allowed_dir = (project_root / "exports" / subfolder).resolve()
    resolved_file = Path(file_path).resolve()
    if allowed_dir not in resolved_file.parents:
        raise HTTPException(status_code=500, detail="Generated PDF path is outside allowed export folder")
    return str(resolved_file)


def _get_latest_terms_setting(db: Session) -> QuotationTermsSetting | None:
    return db.scalar(
        select(QuotationTermsSetting)
        .where(QuotationTermsSetting.is_deleted.is_(False))
        .order_by(QuotationTermsSetting.updated_at.desc(), QuotationTermsSetting.id.desc())
    )


def _load_terms(setting: QuotationTermsSetting | None) -> list[str]:
    if not setting:
        return list(DEFAULT_QUOTATION_TERMS)
    try:
        terms = json.loads(setting.terms_json)
    except (TypeError, json.JSONDecodeError):
        return list(DEFAULT_QUOTATION_TERMS)
    if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
        return list(DEFAULT_QUOTATION_TERMS)
    return terms


class EnquiryCreate(BaseModel):
    enquiry_number: str
    customer_id: int
    enquiry_date: date
    requested_delivery_date: date | None = None
    currency: str
    notes: str | None = None
    status: EnquiryStatus = EnquiryStatus.DRAFT


class EnquiryOut(BaseModel):
    id: int
    enquiry_number: str
    customer_id: int
    enquiry_date: date
    requested_delivery_date: date | None
    currency: str
    notes: str | None
    status: EnquiryStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ContractReviewCreate(BaseModel):
    enquiry_id: int
    status: ContractReviewStatus = ContractReviewStatus.PENDING
    scope_clarity_ok: bool = False
    capability_ok: bool = False
    capacity_ok: bool = False
    delivery_commitment_ok: bool = False
    quality_requirements_ok: bool = False
    review_comments: str | None = None


class ContractReviewOut(BaseModel):
    id: int
    document_number: str
    revision: int
    generated_at: datetime
    generated_by: int | None
    enquiry_id: int
    status: ContractReviewStatus
    scope_clarity_ok: bool
    capability_ok: bool
    capacity_ok: bool
    delivery_commitment_ok: bool
    quality_requirements_ok: bool
    review_comments: str | None

    model_config = {"from_attributes": True}


class QuotationCreate(BaseModel):
    quotation_number: str
    enquiry_id: int
    contract_review_id: int
    customer_id: int
    issue_date: date
    valid_until: date
    currency: str
    subtotal: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    pdf_url: str | None = None
    status: QuotationStatus = QuotationStatus.DRAFT

    model_config = {"extra": "forbid"}


class QuotationOut(BaseModel):
    id: int
    document_number: str
    revision: int
    generated_at: datetime
    generated_by: int | None
    quotation_number: str
    enquiry_id: int
    contract_review_id: int
    customer_id: int
    issue_date: date
    valid_until: date
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    pdf_url: str | None
    status: QuotationStatus

    model_config = {"from_attributes": True}


class CustomerPOReviewCreate(BaseModel):
    quotation_id: int
    customer_po_number: str
    customer_po_date: date
    accepted: bool = False
    status: CustomerPOReviewStatus = CustomerPOReviewStatus.PENDING
    deviation_notes: str | None = None


class CustomerPOReviewOut(BaseModel):
    id: int
    document_number: str
    revision: int
    generated_at: datetime
    generated_by: int | None
    quotation_id: int
    customer_po_number: str
    customer_po_date: date
    accepted: bool
    status: CustomerPOReviewStatus
    deviation_notes: str | None

    model_config = {"from_attributes": True}


class SalesOrderCreate(BaseModel):
    sales_order_number: str
    customer_id: int
    enquiry_id: int
    contract_review_id: int
    quotation_id: int
    customer_po_review_id: int
    order_date: date
    currency: str
    total_amount: Decimal
    status: SalesOrderStatus = SalesOrderStatus.DRAFT


class SalesOrderOut(BaseModel):
    id: int
    sales_order_number: str
    customer_id: int
    enquiry_id: int
    contract_review_id: int
    quotation_id: int
    customer_po_review_id: int
    order_date: date
    currency: str
    total_amount: Decimal
    status: SalesOrderStatus

    model_config = {"from_attributes": True}


class QuotationDownloadResponse(BaseModel):
    file_path: str


class QuotationTermsPayload(BaseModel):
    terms: list[str]


class QuotationTermsOut(BaseModel):
    terms: list[str]
    updated_at: datetime | None = None
    updated_by: int | None = None


@router.get("/quotation-terms", response_model=QuotationTermsOut)
def get_quotation_terms(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    setting = _get_latest_terms_setting(db)
    return QuotationTermsOut(
        terms=_load_terms(setting),
        updated_at=setting.updated_at if setting else None,
        updated_by=setting.updated_by if setting else None,
    )


@router.put("/quotation-terms", response_model=QuotationTermsOut)
def update_quotation_terms(
    payload: QuotationTermsPayload,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    setting = QuotationTermsSetting(
        terms_json=json.dumps(payload.terms),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="QUOTATION_TERMS_UPDATED",
        table_name="quotation_terms_settings",
        record_id=setting.id,
        new_value={"terms": payload.terms},
    )

    return QuotationTermsOut(
        terms=_load_terms(setting),
        updated_at=setting.updated_at,
        updated_by=setting.updated_by,
    )


@router.post("/enquiry", response_model=EnquiryOut, status_code=status.HTTP_201_CREATED)
def create_enquiry(
    payload: EnquiryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    enquiry = Enquiry(
        enquiry_number=payload.enquiry_number,
        customer_id=payload.customer_id,
        enquiry_date=payload.enquiry_date,
        requested_delivery_date=payload.requested_delivery_date,
        currency=payload.currency,
        notes=payload.notes,
        status=payload.status,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SALES_ENQUIRY_CREATED",
        table_name="enquiries",
        record_id=enquiry.id,
        new_value={"enquiry_number": enquiry.enquiry_number, "customer_id": enquiry.customer_id},
    )
    return enquiry


@router.get("/enquiry", response_model=list[EnquiryOut])
def list_enquiries(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    stmt = select(Enquiry).where(Enquiry.is_deleted.is_(False))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Enquiry.enquiry_number.ilike(pattern),
                Enquiry.currency.ilike(pattern),
                Enquiry.notes.ilike(pattern),
            )
        )

    enquiries = db.scalars(stmt.order_by(Enquiry.id.desc()).offset(skip).limit(limit)).all()
    return enquiries


@router.post("/contract-review", response_model=ContractReviewOut, status_code=status.HTTP_201_CREATED)
def create_contract_review(
    payload: ContractReviewCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    existing = db.scalar(select(ContractReview).where(ContractReview.enquiry_id == payload.enquiry_id))
    if existing:
        raise HTTPException(status_code=400, detail="Contract review already exists for this enquiry")

    review = ContractReview(
        document_number=_generate_document_number(db, "CR", ContractReview),
        revision=0,
        generated_at=datetime.now(timezone.utc),
        generated_by=current_user.id,
        enquiry_id=payload.enquiry_id,
        status=payload.status,
        scope_clarity_ok=payload.scope_clarity_ok,
        capability_ok=payload.capability_ok,
        capacity_ok=payload.capacity_ok,
        delivery_commitment_ok=payload.delivery_commitment_ok,
        quality_requirements_ok=payload.quality_requirements_ok,
        review_comments=payload.review_comments,
        reviewed_by=current_user.id,
        reviewed_at=datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="CONTRACT_REVIEW_CREATED",
        table_name="contract_reviews",
        record_id=review.id,
        new_value={"enquiry_id": review.enquiry_id, "status": review.status.value},
    )
    return review


@router.post("/quotation", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
def create_quotation_endpoint(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    try:
        quotation = create_quotation(
            db,
            quotation_number=payload.quotation_number,
            enquiry_id=payload.enquiry_id,
            contract_review_id=payload.contract_review_id,
            customer_id=payload.customer_id,
            issue_date=payload.issue_date,
            valid_until=payload.valid_until,
            currency=payload.currency,
            subtotal=payload.subtotal,
            tax_amount=Decimal("0.00"),
            total_amount=payload.total_amount,
            pdf_url=payload.pdf_url,
            status=payload.status,
            created_by=current_user.id,
        )
    except SalesBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="QUOTATION_CREATED",
        table_name="quotations",
        record_id=quotation.id,
        new_value={"quotation_number": quotation.quotation_number, "enquiry_id": quotation.enquiry_id},
    )
    return quotation


@router.get("/quotation", response_model=list[QuotationOut])
def list_quotations(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    stmt = select(Quotation).where(Quotation.is_deleted.is_(False))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Quotation.quotation_number.ilike(pattern),
                Quotation.document_number.ilike(pattern),
                Quotation.currency.ilike(pattern),
            )
        )

    quotations = db.scalars(stmt.order_by(Quotation.id.desc()).offset(skip).limit(limit)).all()
    return quotations


@router.get("/quotation/{quotation_id}/download")
def download_quotation_pdf(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    quotation = db.scalar(select(Quotation).where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False)))
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    try:
        validate_contract_review_for_quotation(db, quotation.contract_review_id)
    except SalesBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    customer = quotation.customer
    enquiry = quotation.enquiry
    line_items = [
        QuotationPdfLineItem(
            sr_no=item.line_no,
            description=item.description,
            moq=item.quantity,
            uom=item.uom,
            unit_rate=item.unit_price,
            line_total=item.line_total,
        )
        for item in quotation.items
    ]

    terms = _load_terms(_get_latest_terms_setting(db))
    pdf_result = generate_quotation_pdf(
        QuotationPDFPayload(
            quotation_no=quotation.quotation_number,
            quotation_date=quotation.issue_date,
            ref_no=quotation.document_number,
            enquiry_ref=enquiry.enquiry_number,
            prepared_by=current_user.username,
            customer_info={
                "name": customer.name,
                "address_line_1": customer.billing_address or "",
                "address_line_2": customer.shipping_address or "",
                "city_state_zip": "",
                "country": "",
                "contact_person": "",
                "email": customer.email or "",
            },
            line_items=line_items,
            gst_amount=quotation.tax_amount,
            commercial_terms=[
                "Delivery: As agreed in contract review",
                "Payment: 30 days from invoice date",
                f"Validity: Valid until {quotation.valid_until.isoformat()}",
            ],
            fai_required=True,
            coc_required=True,
            traceability_required=True,
            terms_and_conditions=terms,
        )
    )

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="QUOTATION_PDF_GENERATED",
        table_name="quotations",
        record_id=quotation.id,
        new_value={"file_path": pdf_result["file_path"]},
    )

    safe_file_path = _ensure_pdf_path_in_exports(pdf_result["file_path"], "quotations")

    return FileResponse(
        path=safe_file_path,
        media_type="application/pdf",
        filename=f"quotation_{quotation.quotation_number}.pdf",
    )


@router.post("/customer-po-review", response_model=CustomerPOReviewOut, status_code=status.HTTP_201_CREATED)
def create_customer_po_review(
    payload: CustomerPOReviewCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    quotation = db.scalar(
        select(Quotation).where(
            Quotation.id == payload.quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    try:
        validate_contract_review_for_quotation(db, quotation.contract_review_id)
    except SalesBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    po_review = CustomerPOReview(
        document_number=_generate_document_number(db, "POA", CustomerPOReview),
        revision=0,
        generated_at=datetime.now(timezone.utc),
        generated_by=current_user.id,
        quotation_id=payload.quotation_id,
        customer_po_number=payload.customer_po_number,
        customer_po_date=payload.customer_po_date,
        accepted=payload.accepted,
        status=payload.status,
        deviation_notes=payload.deviation_notes,
        reviewed_by=current_user.id,
        reviewed_at=datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(po_review)
    db.commit()
    db.refresh(po_review)

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="CUSTOMER_PO_REVIEW_CREATED",
        table_name="customer_po_reviews",
        record_id=po_review.id,
        new_value={"quotation_id": po_review.quotation_id, "accepted": po_review.accepted},
    )
    return po_review


@router.get("/customer-po-review", response_model=list[CustomerPOReviewOut])
def list_customer_po_reviews(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    stmt = select(CustomerPOReview).where(CustomerPOReview.is_deleted.is_(False))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                CustomerPOReview.customer_po_number.ilike(pattern),
                CustomerPOReview.document_number.ilike(pattern),
            )
        )

    po_reviews = db.scalars(stmt.order_by(CustomerPOReview.id.desc()).offset(skip).limit(limit)).all()
    return po_reviews


@router.get("/customer-po-review/{po_review_id}/download")
def download_customer_po_review_pdf(
    po_review_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    po_review = db.scalar(
        select(CustomerPOReview).where(
            CustomerPOReview.id == po_review_id,
            CustomerPOReview.is_deleted.is_(False),
        )
    )
    if not po_review:
        raise HTTPException(status_code=404, detail="Customer PO review not found")

    quotation = po_review.quotation
    if not quotation:
        raise HTTPException(status_code=400, detail="Quotation not found for PO review")

    try:
        validate_contract_review_for_quotation(db, quotation.contract_review_id)
    except SalesBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    customer = quotation.customer
    enquiry = quotation.enquiry

    verification_checklist = [
        POReviewChecklistItem(
            sr_no=1,
            item="PO references valid quotation",
            status="OK" if quotation.id is not None else "Not OK",
            remarks=f"Quotation: {quotation.quotation_number}",
        ),
        POReviewChecklistItem(
            sr_no=2,
            item="PO date is on/after quotation issue date",
            status="OK" if po_review.customer_po_date >= quotation.issue_date else "Not OK",
            remarks=(
                f"PO Date: {po_review.customer_po_date.isoformat()}, "
                f"Quote Date: {quotation.issue_date.isoformat()}"
            ),
        ),
        POReviewChecklistItem(
            sr_no=3,
            item="Commercial terms reviewed",
            status="OK",
            remarks="Terms aligned with quotation unless deviation noted",
        ),
        POReviewChecklistItem(
            sr_no=4,
            item="Technical requirements reviewed",
            status="OK",
            remarks="Reviewed by sales/contract team",
        ),
        POReviewChecklistItem(
            sr_no=5,
            item="Quality and traceability requirements reviewed",
            status="OK",
            remarks="AS9100D quality clauses considered",
        ),
    ]

    pdf_result = generate_customer_po_review_pdf(
        CustomerPOReviewPDFPayload(
            po_review_no=po_review.customer_po_number,
            review_date=po_review.reviewed_at.date() if po_review.reviewed_at else po_review.customer_po_date,
            ref_no=quotation.quotation_number,
            mode="Enq. By Mail",
            customer_info={
                "name": customer.name,
                "address_line_1": customer.billing_address or "",
                "address_line_2": customer.shipping_address or "",
                "city_state_zip": "",
                "country": "",
                "contact_person": "",
                "email": customer.email or "",
            },
            po_info={
                "po_number": po_review.customer_po_number,
                "po_date": po_review.customer_po_date.isoformat(),
                "quotation_ref": quotation.quotation_number,
                "enquiry_ref": enquiry.enquiry_number,
                "currency": quotation.currency,
                "po_value": str(quotation.total_amount),
            },
            verification_items=verification_checklist,
            acceptance_declaration=(
                "Customer PO is accepted for order processing as per reviewed technical and commercial terms."
                if po_review.accepted
                else "Customer PO is not accepted. Deviations must be resolved before order processing."
            ),
            approved_by=current_user.username,
            approval_date=(
                po_review.reviewed_at.date().isoformat()
                if po_review.reviewed_at
                else po_review.customer_po_date.isoformat()
            ),
        )
    )

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="CUSTOMER_PO_REVIEW_PDF_GENERATED",
        table_name="customer_po_reviews",
        record_id=po_review.id,
        new_value={"file_path": pdf_result["file_path"]},
    )

    safe_file_path = _ensure_pdf_path_in_exports(pdf_result["file_path"], "po_reviews")

    return FileResponse(
        path=safe_file_path,
        media_type="application/pdf",
        filename=f"po_review_{po_review.customer_po_number}.pdf",
    )


@router.post("/sales-order", response_model=SalesOrderOut, status_code=status.HTTP_201_CREATED)
def create_sales_order_endpoint(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    try:
        sales_order = create_sales_order(
            db,
            sales_order_number=payload.sales_order_number,
            customer_id=payload.customer_id,
            enquiry_id=payload.enquiry_id,
            contract_review_id=payload.contract_review_id,
            quotation_id=payload.quotation_id,
            customer_po_review_id=payload.customer_po_review_id,
            order_date=payload.order_date,
            currency=payload.currency,
            total_amount=payload.total_amount,
            status=payload.status,
            created_by=current_user.id,
        )
    except SalesBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SALES_ORDER_CREATED",
        table_name="sales_orders",
        record_id=sales_order.id,
        new_value={"sales_order_number": sales_order.sales_order_number},
    )
    return sales_order


@router.get("/sales-order", response_model=list[SalesOrderOut])
def list_sales_orders(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Sales", "Admin")),
):
    stmt = select(SalesOrder).where(SalesOrder.is_deleted.is_(False))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                SalesOrder.sales_order_number.ilike(pattern),
                SalesOrder.currency.ilike(pattern),
            )
        )

    sales_orders = db.scalars(stmt.order_by(SalesOrder.id.desc()).offset(skip).limit(limit)).all()
    return sales_orders
