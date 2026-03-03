from __future__ import annotations

from datetime import date, datetime, timezone
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
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RouteCardStatus(str, PyEnum):
    DRAFT = "draft"
    RELEASED = "released"
    OBSOLETE = "obsolete"


class EngineeringReleaseStatus(str, PyEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class SpecialProcessType(str, PyEnum):
    HT = "ht"
    PLATING = "plating"
    NDT = "ndt"
    WELDING = "welding"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class Drawing(Base, EngineeringAuditMixin):
    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    drawing_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    part_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    customer: Mapped[object | None] = relationship("Customer")
    revisions: Mapped[list[DrawingRevision]] = relationship(
        back_populates="drawing", cascade="all, delete-orphan"
    )


class DrawingRevision(Base, EngineeringAuditMixin):
    __tablename__ = "drawing_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    drawing_id: Mapped[int] = mapped_column(ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_code: Mapped[str] = mapped_column(String(10), nullable=False)
    revision_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_drawing_revisions_drawing_revision_code", "drawing_id", "revision_code", unique=True),
        Index(
            "uq_drawing_revisions_current_per_drawing",
            "drawing_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    drawing: Mapped[Drawing] = relationship(back_populates="revisions")
    approver: Mapped[object | None] = relationship("User", foreign_keys=[approved_by])
    route_cards: Mapped[list[RouteCard]] = relationship(back_populates="drawing_revision")


class RouteCard(Base, EngineeringAuditMixin):
    __tablename__ = "route_cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    route_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    drawing_revision_id: Mapped[int] = mapped_column(ForeignKey("drawing_revisions.id"), nullable=False, index=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False, index=True)
    status: Mapped[RouteCardStatus] = mapped_column(
        Enum(RouteCardStatus, name="route_card_status"),
        default=RouteCardStatus.DRAFT,
        nullable=False,
        index=True,
    )
    released_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    released_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(status != 'RELEASED') OR (released_date IS NOT NULL)",
            name="ck_route_cards_released_requires_released_date",
        ),
    )

    drawing_revision: Mapped[DrawingRevision] = relationship(back_populates="route_cards")
    sales_order: Mapped[object] = relationship("SalesOrder")
    releaser: Mapped[object | None] = relationship("User", foreign_keys=[released_by])
    operations: Mapped[list[RouteOperation]] = relationship(
        back_populates="route_card", cascade="all, delete-orphan"
    )
    release_records: Mapped[list[EngineeringReleaseRecord]] = relationship(
        back_populates="route_card", cascade="all, delete-orphan"
    )


class RouteOperation(Base, EngineeringAuditMixin):
    __tablename__ = "route_operations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    route_card_id: Mapped[int] = mapped_column(ForeignKey("route_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center: Mapped[str] = mapped_column(String(100), nullable=False)
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("uq_route_operations_card_operation_number", "route_card_id", "operation_number", unique=True),
        Index("uq_route_operations_card_sequence_order", "route_card_id", "sequence_order", unique=True),
    )

    route_card: Mapped[RouteCard] = relationship(back_populates="operations")
    special_process_links: Mapped[list[RouteOperationSpecialProcess]] = relationship(
        back_populates="route_operation", cascade="all, delete-orphan"
    )


class SpecialProcess(Base, EngineeringAuditMixin):
    __tablename__ = "special_processes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    process_name: Mapped[str] = mapped_column(String(120), nullable=False)
    process_type: Mapped[SpecialProcessType] = mapped_column(
        Enum(SpecialProcessType, name="special_process_type"),
        nullable=False,
        index=True,
    )
    is_outsourced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("uq_special_processes_name_type", "process_name", "process_type", unique=True),
    )

    route_operation_links: Mapped[list[RouteOperationSpecialProcess]] = relationship(
        back_populates="special_process", cascade="all, delete-orphan"
    )


class RouteOperationSpecialProcess(Base, EngineeringAuditMixin):
    __tablename__ = "route_operation_special_processes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    route_operation_id: Mapped[int] = mapped_column(
        ForeignKey("route_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    special_process_id: Mapped[int] = mapped_column(
        ForeignKey("special_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        Index(
            "uq_route_operation_special_process",
            "route_operation_id",
            "special_process_id",
            unique=True,
        ),
    )

    route_operation: Mapped[RouteOperation] = relationship(back_populates="special_process_links")
    special_process: Mapped[SpecialProcess] = relationship(back_populates="route_operation_links")


class EngineeringReleaseRecord(Base, EngineeringAuditMixin):
    __tablename__ = "engineering_release_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    route_card_id: Mapped[int] = mapped_column(ForeignKey("route_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    release_status: Mapped[EngineeringReleaseStatus] = mapped_column(
        Enum(EngineeringReleaseStatus, name="engineering_release_status"),
        nullable=False,
        index=True,
    )
    release_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    route_card: Mapped[RouteCard] = relationship(back_populates="release_records")

