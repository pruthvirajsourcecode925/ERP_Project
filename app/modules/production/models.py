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


class ProductionOrderStatus(str, PyEnum):
    DRAFT = "Draft"
    RELEASED = "Released"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"


class ProductionOperationStatus(str, PyEnum):
    PENDING = "Pending"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"


class InspectionResult(str, PyEnum):
    PENDING = "Pending"
    PASS = "Pass"
    FAIL = "Fail"


class ReworkOrderStatus(str, PyEnum):
    OPEN = "Open"
    IN_PROGRESS = "InProgress"
    CLOSED = "Closed"


class FAITriggerStatus(str, PyEnum):
    PENDING = "Pending"
    COMPLETED = "Completed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class ProductionAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class ProductionOrder(Base, ProductionAuditMixin):
    __tablename__ = "production_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), nullable=False, index=True)
    route_card_id: Mapped[int] = mapped_column(ForeignKey("route_cards.id"), nullable=False, index=True)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    status: Mapped[ProductionOrderStatus] = mapped_column(
        Enum(
            ProductionOrderStatus,
            name="production_order_status",
            values_callable=enum_values,
        ),
        default=ProductionOrderStatus.DRAFT,
        nullable=False,
        index=True,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("planned_quantity > 0", name="ck_production_orders_planned_qty_gt_zero"),
        CheckConstraint("start_date IS NULL OR due_date >= start_date", name="ck_production_orders_due_after_start"),
    )

    sales_order: Mapped[object] = relationship("SalesOrder")
    route_card: Mapped[object] = relationship("RouteCard")
    operations: Mapped[list[ProductionOperation]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )
    logs: Mapped[list[ProductionLog]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )
    fai_triggers: Mapped[list[FAITrigger]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )


class Machine(Base, ProductionAuditMixin):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    machine_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    machine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    operations: Mapped[list[ProductionOperation]] = relationship(back_populates="machine")
    logs: Mapped[list[ProductionLog]] = relationship(back_populates="machine")


class ProductionOperation(Base, ProductionAuditMixin):
    __tablename__ = "production_operations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_number: Mapped[int] = mapped_column(nullable=False)
    operation_name: Mapped[str] = mapped_column(String(200), nullable=False)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True, index=True)
    status: Mapped[ProductionOperationStatus] = mapped_column(
        Enum(
            ProductionOperationStatus,
            name="production_operation_status",
            values_callable=enum_values,
        ),
        default=ProductionOperationStatus.PENDING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("operation_number > 0", name="ck_production_operations_op_no_gt_zero"),
        CheckConstraint("completed_at IS NULL OR started_at IS NOT NULL", name="ck_production_operations_complete_after_start"),
        Index(
            "uq_production_operations_order_operation_number",
            "production_order_id",
            "operation_number",
            unique=True,
        ),
    )

    production_order: Mapped[ProductionOrder] = relationship(back_populates="operations")
    machine: Mapped[Machine | None] = relationship(
        "Machine", back_populates="operations"
    )
    operators: Mapped[list[OperationOperator]] = relationship(
        back_populates="production_operation", cascade="all, delete-orphan"
    )
    inspections: Mapped[list[InProcessInspection]] = relationship(
        back_populates="production_operation", cascade="all, delete-orphan"
    )
    rework_orders: Mapped[list[ReworkOrder]] = relationship(
        back_populates="production_operation", cascade="all, delete-orphan"
    )
    logs: Mapped[list[ProductionLog]] = relationship(
        back_populates="operation", cascade="all, delete-orphan"
    )
    fai_triggers: Mapped[list[FAITrigger]] = relationship(
        back_populates="operation", cascade="all, delete-orphan"
    )


class OperationOperator(Base, ProductionAuditMixin):
    __tablename__ = "operation_operators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_operation_id: Mapped[int] = mapped_column(
        ForeignKey("production_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index(
            "uq_operation_operators_operation_user",
            "production_operation_id",
            "operator_user_id",
            unique=True,
        ),
    )

    production_operation: Mapped[ProductionOperation] = relationship(back_populates="operators")
    operator: Mapped[object] = relationship("User", foreign_keys=[operator_user_id])


class InProcessInspection(Base, ProductionAuditMixin):
    __tablename__ = "in_process_inspections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_operation_id: Mapped[int] = mapped_column(
        ForeignKey("production_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    inspection_result: Mapped[InspectionResult] = mapped_column(
        Enum(
            InspectionResult,
            name="production_inspection_result",
            values_callable=enum_values,
        ),
        default=InspectionResult.PENDING,
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspection_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    production_operation: Mapped[ProductionOperation] = relationship(back_populates="inspections")
    inspector: Mapped[object | None] = relationship("User", foreign_keys=[inspected_by])


class ReworkOrder(Base, ProductionAuditMixin):
    __tablename__ = "rework_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_operation_id: Mapped[int] = mapped_column(
        ForeignKey("production_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReworkOrderStatus] = mapped_column(
        Enum(
            ReworkOrderStatus,
            name="rework_order_status",
            values_callable=enum_values,
        ),
        default=ReworkOrderStatus.OPEN,
        nullable=False,
        index=True,
    )

    production_operation: Mapped[ProductionOperation] = relationship(back_populates="rework_orders")


class ProductionLog(Base, ProductionAuditMixin):
    __tablename__ = "production_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("production_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    operator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True, index=True)
    produced_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0.000"), nullable=False)
    scrap_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0.000"), nullable=False)
    scrap_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shift: Mapped[str | None] = mapped_column(String(50), nullable=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("produced_quantity >= 0", name="ck_production_logs_produced_qty_gte_zero"),
        CheckConstraint("scrap_quantity >= 0", name="ck_production_logs_scrap_qty_gte_zero"),
        CheckConstraint(
            "produced_quantity + scrap_quantity > 0",
            name="ck_production_logs_total_qty_gt_zero",
        ),
    )

    production_order: Mapped[ProductionOrder] = relationship(back_populates="logs")
    operation: Mapped[ProductionOperation] = relationship(back_populates="logs")
    recorder: Mapped[object] = relationship("User", foreign_keys=[recorded_by])
    operator_user: Mapped[object | None] = relationship("User", foreign_keys=[operator_user_id])
    machine: Mapped[Machine | None] = relationship(
        "Machine", back_populates="logs", foreign_keys=[machine_id]
    )


class FAITrigger(Base, ProductionAuditMixin):
    __tablename__ = "fai_triggers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("production_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    status: Mapped[FAITriggerStatus] = mapped_column(
        Enum(
            FAITriggerStatus,
            name="fai_trigger_status",
            values_callable=enum_values,
        ),
        default=FAITriggerStatus.PENDING,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("uq_fai_triggers_order_operation", "production_order_id", "operation_id", unique=True),
    )

    production_order: Mapped[ProductionOrder] = relationship(back_populates="fai_triggers")
    operation: Mapped[ProductionOperation] = relationship(back_populates="fai_triggers")
