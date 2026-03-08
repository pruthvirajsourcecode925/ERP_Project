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


class DispatchOrderStatus(str, PyEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    RELEASED = "released"
    HOLD = "hold"
    CANCELLED = "cancelled"


class DispatchChecklistStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    WAIVED = "waived"


class InvoiceStatus(str, PyEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    CANCELLED = "cancelled"
    PAID = "paid"


class DeliveryChallanStatus(str, PyEnum):
    ISSUED = "issued"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ShipmentTrackingStatus(str, PyEnum):
    BOOKED = "booked"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class DispatchAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class DispatchOrder(Base, DispatchAuditMixin):
    __tablename__ = "dispatch_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    dispatch_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False, index=True)
    certificate_of_conformance_id: Mapped[int | None] = mapped_column(
        ForeignKey("certificates_of_conformance.id"), nullable=True, index=True
    )
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[DispatchOrderStatus] = mapped_column(
        Enum(
            DispatchOrderStatus,
            name="dispatch_order_status",
            values_callable=enum_values,
        ),
        default=DispatchOrderStatus.DRAFT,
        nullable=False,
        index=True,
    )
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipping_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    sales_order: Mapped[object] = relationship("SalesOrder")
    certificate_of_conformance: Mapped[object | None] = relationship("CertificateOfConformance")
    releaser: Mapped[object | None] = relationship("User", foreign_keys=[released_by])
    items: Mapped[list[DispatchItem]] = relationship(
        back_populates="dispatch_order", cascade="all, delete-orphan"
    )
    checklists: Mapped[list[DispatchChecklist]] = relationship(
        back_populates="dispatch_order", cascade="all, delete-orphan"
    )
    packing_list: Mapped[PackingList | None] = relationship(
        back_populates="dispatch_order", uselist=False, cascade="all, delete-orphan"
    )
    invoice: Mapped[Invoice | None] = relationship(
        back_populates="dispatch_order", uselist=False, cascade="all, delete-orphan"
    )
    delivery_challan: Mapped[DeliveryChallan | None] = relationship(
        back_populates="dispatch_order", uselist=False, cascade="all, delete-orphan"
    )
    shipment_trackings: Mapped[list[ShipmentTracking]] = relationship(
        back_populates="dispatch_order", cascade="all, delete-orphan"
    )


class DispatchItem(Base, DispatchAuditMixin):
    __tablename__ = "dispatch_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_traceability_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("line_number > 0", name="ck_dispatch_items_line_number_gt_zero"),
        CheckConstraint("quantity > 0", name="ck_dispatch_items_quantity_gt_zero"),
        Index("uq_dispatch_items_order_line", "dispatch_order_id", "line_number", unique=True),
    )

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="items")
    production_order: Mapped[object] = relationship("ProductionOrder")


class DispatchChecklist(Base, DispatchAuditMixin):
    __tablename__ = "dispatch_checklists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checklist_item: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[DispatchChecklistStatus] = mapped_column(
        Enum(
            DispatchChecklistStatus,
            name="dispatch_checklist_status",
            values_callable=enum_values,
        ),
        default=DispatchChecklistStatus.PENDING,
        nullable=False,
        index=True,
    )
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="checklists")
    checker: Mapped[object | None] = relationship("User", foreign_keys=[checked_by])


class PackingList(Base, DispatchAuditMixin):
    __tablename__ = "packing_lists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    packing_list_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    packed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    package_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    gross_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    net_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    dimensions: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("package_count >= 0", name="ck_packing_lists_package_count_gte_zero"),
        CheckConstraint("gross_weight IS NULL OR gross_weight >= 0", name="ck_packing_lists_gross_weight_gte_zero"),
        CheckConstraint("net_weight IS NULL OR net_weight >= 0", name="ck_packing_lists_net_weight_gte_zero"),
    )

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="packing_list")


class Invoice(Base, DispatchAuditMixin):
    __tablename__ = "dispatch_invoices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(
            InvoiceStatus,
            name="dispatch_invoice_status",
            values_callable=enum_values,
        ),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_dispatch_invoices_subtotal_gte_zero"),
        CheckConstraint("tax_amount >= 0", name="ck_dispatch_invoices_tax_amount_gte_zero"),
        CheckConstraint("total_amount >= 0", name="ck_dispatch_invoices_total_amount_gte_zero"),
    )

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="invoice")


class DeliveryChallan(Base, DispatchAuditMixin):
    __tablename__ = "delivery_challans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    challan_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    received_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DeliveryChallanStatus] = mapped_column(
        Enum(
            DeliveryChallanStatus,
            name="delivery_challan_status",
            values_callable=enum_values,
        ),
        default=DeliveryChallanStatus.ISSUED,
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="delivery_challan")


class ShipmentTracking(Base, DispatchAuditMixin):
    __tablename__ = "shipment_trackings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tracking_number: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    carrier_name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ShipmentTrackingStatus] = mapped_column(
        Enum(
            ShipmentTrackingStatus,
            name="shipment_tracking_status",
            values_callable=enum_values,
        ),
        default=ShipmentTrackingStatus.BOOKED,
        nullable=False,
        index=True,
    )
    proof_of_delivery_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "expected_delivery_date IS NULL OR expected_delivery_date >= shipment_date",
            name="ck_shipment_trackings_expected_delivery_after_shipment",
        ),
        CheckConstraint(
            "actual_delivery_date IS NULL OR actual_delivery_date >= shipment_date",
            name="ck_shipment_trackings_actual_delivery_after_shipment",
        ),
    )

    dispatch_order: Mapped[DispatchOrder] = relationship(back_populates="shipment_trackings")