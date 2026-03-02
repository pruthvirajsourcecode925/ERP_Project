from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EnquiryStatus(str, PyEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ContractReviewStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class QuotationStatus(str, PyEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CustomerPOReviewStatus(str, PyEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SalesOrderStatus(str, PyEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    CLOSED = "closed"
    CANCELLED = "cancelled"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SalesAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class Customer(Base, SalesAuditMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    customer_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    billing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    enquiries: Mapped[list[Enquiry]] = relationship(back_populates="customer")
    quotations: Mapped[list[Quotation]] = relationship(back_populates="customer")
    sales_orders: Mapped[list[SalesOrder]] = relationship(back_populates="customer")


class Enquiry(Base, SalesAuditMixin):
    __tablename__ = "enquiries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    enquiry_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    enquiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EnquiryStatus] = mapped_column(Enum(EnquiryStatus, name="enquiry_status"), default=EnquiryStatus.DRAFT, nullable=False, index=True)

    customer: Mapped[Customer] = relationship(back_populates="enquiries")
    contract_review: Mapped[ContractReview | None] = relationship(back_populates="enquiry", uselist=False)
    quotations: Mapped[list[Quotation]] = relationship(back_populates="enquiry")
    sales_orders: Mapped[list[SalesOrder]] = relationship(back_populates="enquiry")


Index("ix_enquiries_enquiry_number", Enquiry.enquiry_number)


class ContractReview(Base, SalesAuditMixin):
    __tablename__ = "contract_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    document_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    enquiry_id: Mapped[int] = mapped_column(ForeignKey("enquiries.id"), nullable=False, unique=True, index=True)
    status: Mapped[ContractReviewStatus] = mapped_column(
        Enum(ContractReviewStatus, name="contract_review_status"),
        default=ContractReviewStatus.PENDING,
        nullable=False,
        index=True,
    )

    scope_clarity_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capability_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capacity_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_commitment_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_requirements_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    review_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    enquiry: Mapped[Enquiry] = relationship(back_populates="contract_review")
    quotations: Mapped[list[Quotation]] = relationship(back_populates="contract_review")
    sales_orders: Mapped[list[SalesOrder]] = relationship(back_populates="contract_review")


class Quotation(Base, SalesAuditMixin):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    document_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    quotation_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    enquiry_id: Mapped[int] = mapped_column(ForeignKey("enquiries.id"), nullable=False, index=True)
    contract_review_id: Mapped[int] = mapped_column(ForeignKey("contract_reviews.id"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status"),
        default=QuotationStatus.DRAFT,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint("valid_until >= issue_date", name="ck_quotations_valid_until_after_issue"),
    )

    enquiry: Mapped[Enquiry] = relationship(back_populates="quotations")
    contract_review: Mapped[ContractReview] = relationship(back_populates="quotations")
    customer: Mapped[Customer] = relationship(back_populates="quotations")
    items: Mapped[list[QuotationItem]] = relationship(back_populates="quotation", cascade="all, delete-orphan")
    po_reviews: Mapped[list[CustomerPOReview]] = relationship(back_populates="quotation")
    sales_orders: Mapped[list[SalesOrder]] = relationship(back_populates="quotation")


Index("ix_quotations_quotation_number", Quotation.quotation_number)


class QuotationItem(Base, SalesAuditMixin):
    __tablename__ = "quotation_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quotation_items_quantity_gt_zero"),
        CheckConstraint("unit_price >= 0", name="ck_quotation_items_unit_price_gte_zero"),
        CheckConstraint("line_total >= 0", name="ck_quotation_items_line_total_gte_zero"),
        Index("uq_quotation_items_quotation_line", "quotation_id", "line_no", unique=True),
    )

    quotation: Mapped[Quotation] = relationship(back_populates="items")


class QuotationTermsSetting(Base, SalesAuditMixin):
    __tablename__ = "quotation_terms_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    terms_json: Mapped[str] = mapped_column(Text, nullable=False)


class CustomerPOReview(Base, SalesAuditMixin):
    __tablename__ = "customer_po_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    document_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id"), nullable=False, index=True)
    customer_po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_po_date: Mapped[date] = mapped_column(Date, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[CustomerPOReviewStatus] = mapped_column(
        Enum(CustomerPOReviewStatus, name="customer_po_review_status"),
        default=CustomerPOReviewStatus.PENDING,
        nullable=False,
        index=True,
    )
    deviation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_customer_po_reviews_quotation_po", "quotation_id", "customer_po_number", unique=True),
    )

    quotation: Mapped[Quotation] = relationship(back_populates="po_reviews")
    sales_orders: Mapped[list[SalesOrder]] = relationship(back_populates="customer_po_review")


class SalesOrder(Base, SalesAuditMixin):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    sales_order_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    enquiry_id: Mapped[int] = mapped_column(ForeignKey("enquiries.id"), nullable=False, index=True)
    contract_review_id: Mapped[int] = mapped_column(ForeignKey("contract_reviews.id"), nullable=False, index=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id"), nullable=False, index=True)
    customer_po_review_id: Mapped[int] = mapped_column(ForeignKey("customer_po_reviews.id"), nullable=False, index=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[SalesOrderStatus] = mapped_column(
        Enum(SalesOrderStatus, name="sales_order_status"),
        default=SalesOrderStatus.DRAFT,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_sales_orders_total_amount_gte_zero"),
    )

    customer: Mapped[Customer] = relationship(back_populates="sales_orders")
    enquiry: Mapped[Enquiry] = relationship(back_populates="sales_orders")
    contract_review: Mapped[ContractReview] = relationship(back_populates="sales_orders")
    quotation: Mapped[Quotation] = relationship(back_populates="sales_orders")
    customer_po_review: Mapped[CustomerPOReview] = relationship(back_populates="sales_orders")

