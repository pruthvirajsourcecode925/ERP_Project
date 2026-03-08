from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.sales.models import (
    ContractReview,
    ContractReviewStatus,
    CustomerPOReview,
    Quotation,
    QuotationStatus,
    SalesOrder,
    SalesOrderStatus,
)
from app.services.document_numbers import generate_sequential_document_number


class SalesBusinessRuleError(Exception):
    pass


def _generate_document_number(db: Session, prefix: str, model) -> str:
    year = datetime.now(ZoneInfo("UTC")).year
    return generate_sequential_document_number(
        db,
        field=model.document_number,
        prefix=prefix,
        year=year,
    )


def _ensure_all_feasibility_checks_true(contract_review: ContractReview) -> None:
    checkbox_state = {
        "Drawing availability": contract_review.scope_clarity_ok,
        "Special processes": contract_review.capability_ok,
        "Capacity & machine suitability": contract_review.capacity_ok,
        "Delivery feasibility": contract_review.delivery_commitment_ok,
        "Quality requirements (FAI, COC, Traceability)": contract_review.quality_requirements_ok,
    }
    failed_checks = [name for name, is_checked in checkbox_state.items() if is_checked is not True]
    if failed_checks:
        failed_list = "\n".join(f"• {item}" for item in failed_checks)
        raise SalesBusinessRuleError(
            "Quotation cannot be generated due to incomplete contract review.\n\n"
            "The following feasibility items are not approved:\n"
            f"{failed_list}\n\n"
            "Please resolve the above issues before generating quotation."
        )


def validate_contract_review_for_quotation(db: Session, contract_review_id: int) -> ContractReview:
    contract_review = db.scalar(select(ContractReview).where(ContractReview.id == contract_review_id))
    if not contract_review:
        raise SalesBusinessRuleError("ContractReview not found")

    _ensure_all_feasibility_checks_true(contract_review)
    return contract_review


def create_quotation(
    db: Session,
    *,
    quotation_number: str,
    enquiry_id: int,
    contract_review_id: int,
    customer_id: int,
    issue_date: date,
    valid_until: date,
    currency: str,
    subtotal: Decimal = Decimal("0.00"),
    tax_amount: Decimal = Decimal("0.00"),
    total_amount: Decimal = Decimal("0.00"),
    pdf_url: str | None = None,
    status: QuotationStatus = QuotationStatus.DRAFT,
    created_by: int | None = None,
) -> Quotation:
    contract_review = validate_contract_review_for_quotation(db, contract_review_id)

    quotation = Quotation(
        document_number=_generate_document_number(db, "QT", Quotation),
        revision=0,
        generated_at=datetime.now(ZoneInfo("UTC")),
        generated_by=created_by,
        quotation_number=quotation_number,
        enquiry_id=enquiry_id,
        contract_review_id=contract_review.id,
        customer_id=customer_id,
        issue_date=issue_date,
        valid_until=valid_until,
        currency=currency,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        pdf_url=pdf_url,
        status=status,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(quotation)
    db.commit()
    db.refresh(quotation)
    return quotation


def validate_sales_order_creation(
    db: Session,
    *,
    contract_review_id: int,
    customer_po_review_id: int,
) -> tuple[ContractReview, CustomerPOReview]:
    contract_review = db.scalar(select(ContractReview).where(ContractReview.id == contract_review_id))
    if not contract_review:
        raise SalesBusinessRuleError("ContractReview not found")

    if contract_review.status != ContractReviewStatus.APPROVED:
        raise SalesBusinessRuleError(
            "SalesOrder creation blocked: ContractReview.status must be approved"
        )

    _ensure_all_feasibility_checks_true(contract_review)

    po_review = db.scalar(select(CustomerPOReview).where(CustomerPOReview.id == customer_po_review_id))
    if not po_review:
        raise SalesBusinessRuleError("CustomerPOReview not found")

    if po_review.accepted is not True:
        raise SalesBusinessRuleError(
            "SalesOrder creation blocked: CustomerPOReview.accepted must be true"
        )

    return contract_review, po_review


def create_sales_order(
    db: Session,
    *,
    sales_order_number: str,
    customer_id: int,
    enquiry_id: int,
    contract_review_id: int,
    quotation_id: int,
    customer_po_review_id: int,
    order_date: date,
    currency: str,
    total_amount: Decimal,
    status: SalesOrderStatus = SalesOrderStatus.DRAFT,
    created_by: int | None = None,
) -> SalesOrder:
    contract_review, po_review = validate_sales_order_creation(
        db,
        contract_review_id=contract_review_id,
        customer_po_review_id=customer_po_review_id,
    )

    quotation = db.scalar(select(Quotation).where(Quotation.id == quotation_id))
    if not quotation:
        raise SalesBusinessRuleError("Quotation not found")

    if quotation.contract_review_id != contract_review.id:
        raise SalesBusinessRuleError("Quotation does not match ContractReview")

    if po_review.quotation_id != quotation.id:
        raise SalesBusinessRuleError("CustomerPOReview does not belong to Quotation")

    sales_order = SalesOrder(
        sales_order_number=sales_order_number,
        customer_id=customer_id,
        enquiry_id=enquiry_id,
        contract_review_id=contract_review.id,
        quotation_id=quotation.id,
        customer_po_review_id=po_review.id,
        order_date=order_date,
        currency=currency,
        total_amount=total_amount,
        status=status,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(sales_order)
    db.commit()
    db.refresh(sales_order)
    return sales_order
