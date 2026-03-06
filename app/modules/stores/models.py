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
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GRNStatus(str, PyEnum):
    DRAFT = "Draft"
    UNDER_INSPECTION = "UnderInspection"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class InspectionStatus(str, PyEnum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class StockTransactionType(str, PyEnum):
    GRN = "GRN"
    ISSUE = "ISSUE"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StoresAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class StorageLocation(Base, StoresAuditMixin):
    __tablename__ = "storage_locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    location_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    batch_inventories: Mapped[list[BatchInventory]] = relationship(back_populates="storage_location")
    stock_ledger_entries: Mapped[list[StockLedger]] = relationship(back_populates="storage_location")


class GRN(Base, StoresAuditMixin):
    __tablename__ = "grns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    grn_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    received_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    received_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    grn_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[GRNStatus] = mapped_column(
        Enum(
            GRNStatus,
            name="grn_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=GRNStatus.DRAFT,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_grns_grn_number", "grn_number"),
    )

    purchase_order: Mapped[object] = relationship("PurchaseOrder")
    supplier: Mapped[object] = relationship("Supplier")
    items: Mapped[list[GRNItem]] = relationship(back_populates="grn", cascade="all, delete-orphan")


class GRNItem(Base, StoresAuditMixin):
    __tablename__ = "grn_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("grns.id", ondelete="CASCADE"), nullable=False, index=True)
    item_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    heat_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    batch_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0.000"))
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0.000"))

    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="ck_grn_items_received_qty_gt_zero"),
        CheckConstraint("accepted_quantity >= 0", name="ck_grn_items_accepted_qty_gte_zero"),
        CheckConstraint("rejected_quantity >= 0", name="ck_grn_items_rejected_qty_gte_zero"),
        CheckConstraint(
            "accepted_quantity + rejected_quantity = received_quantity",
            name="ck_grn_items_qty_balance",
        ),
        Index("ix_grn_items_batch_number", "batch_number"),
    )

    grn: Mapped[GRN] = relationship(back_populates="items")
    rmir: Mapped[RMIR | None] = relationship(back_populates="grn_item", uselist=False, cascade="all, delete-orphan")
    mtc_verification: Mapped[MTCVerification | None] = relationship(
        back_populates="grn_item", uselist=False, cascade="all, delete-orphan"
    )
    batch_inventory: Mapped[BatchInventory | None] = relationship(
        back_populates="grn_item", uselist=False, cascade="all, delete-orphan"
    )


class RMIR(Base, StoresAuditMixin):
    __tablename__ = "rmir_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    grn_item_id: Mapped[int] = mapped_column(
        ForeignKey("grn_items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    inspected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    inspection_status: Mapped[InspectionStatus] = mapped_column(
        Enum(
            InspectionStatus,
            name="rmir_inspection_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=InspectionStatus.PENDING,
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    grn_item: Mapped[GRNItem] = relationship(back_populates="rmir")


class MTCVerification(Base, StoresAuditMixin):
    __tablename__ = "mtc_verifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    grn_item_id: Mapped[int] = mapped_column(
        ForeignKey("grn_items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    mtc_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    chemical_composition_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mechanical_properties_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    standard_compliance_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    verification_date: Mapped[date] = mapped_column(Date, nullable=False)

    grn_item: Mapped[GRNItem] = relationship(back_populates="mtc_verification")


class BatchInventory(Base, StoresAuditMixin):
    __tablename__ = "batch_inventories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    batch_number: Mapped[str] = mapped_column(
        ForeignKey("grn_items.batch_number", ondelete="CASCADE"), nullable=False, unique=True
    )
    storage_location_id: Mapped[int] = mapped_column(ForeignKey("storage_locations.id"), nullable=False)
    item_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0.000"))

    __table_args__ = (
        CheckConstraint("current_quantity >= 0", name="ck_batch_inventories_current_qty_gte_zero"),
        Index("ix_batch_inventories_batch_number", "batch_number"),
        Index("ix_batch_inventories_storage_location_id", "storage_location_id"),
    )

    grn_item: Mapped[GRNItem] = relationship(back_populates="batch_inventory")
    storage_location: Mapped[StorageLocation] = relationship(back_populates="batch_inventories")
    stock_ledger_entries: Mapped[list[StockLedger]] = relationship(
        back_populates="batch_inventory", cascade="all, delete-orphan"
    )


class StockLedger(Base, StoresAuditMixin):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    batch_number: Mapped[str] = mapped_column(
        ForeignKey("batch_inventories.batch_number", ondelete="RESTRICT"), nullable=False
    )
    storage_location_id: Mapped[int] = mapped_column(ForeignKey("storage_locations.id"), nullable=False)
    transaction_type: Mapped[StockTransactionType] = mapped_column(
        Enum(
            StockTransactionType,
            name="stock_transaction_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    reference_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    quantity_in: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0.000"))
    quantity_out: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0.000"))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("quantity_in >= 0", name="ck_stock_ledger_qty_in_gte_zero"),
        CheckConstraint("quantity_out >= 0", name="ck_stock_ledger_qty_out_gte_zero"),
        CheckConstraint("balance_after >= 0", name="ck_stock_ledger_balance_after_gte_zero"),
        CheckConstraint(
            "(transaction_type = 'GRN' AND quantity_in > 0 AND quantity_out = 0) "
            "OR (transaction_type = 'ISSUE' AND quantity_out > 0 AND quantity_in = 0)",
            name="ck_stock_ledger_direction_by_txn_type",
        ),
        Index("ix_stock_ledger_batch_number", "batch_number"),
        Index("ix_stock_ledger_storage_location_id", "storage_location_id"),
    )

    batch_inventory: Mapped[BatchInventory] = relationship(back_populates="stock_ledger_entries")
    storage_location: Mapped[StorageLocation] = relationship(back_populates="stock_ledger_entries")
