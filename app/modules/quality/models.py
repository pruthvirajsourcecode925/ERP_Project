from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IncomingInspectionStatus(str, PyEnum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class QualityInspectionResult(str, PyEnum):
    PASS = "Pass"
    FAIL = "Fail"


class FAIReportStatus(str, PyEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class NCRStatus(str, PyEnum):
    OPEN = "Open"
    INVESTIGATING = "Investigating"
    CLOSED = "Closed"


class CAPAActionType(str, PyEnum):
    CORRECTIVE = "Corrective"
    PREVENTIVE = "Preventive"


class CAPAStatus(str, PyEnum):
    OPEN = "Open"
    CLOSED = "Closed"


class RootCauseMethod(str, PyEnum):
    WHY_5 = "5WHY"
    FISHBONE = "Fishbone"


class GaugeStatus(str, PyEnum):
    VALID = "Valid"
    EXPIRED = "Expired"


class InspectionMeasurementType(str, PyEnum):
    INCOMING = "incoming"
    INPROCESS = "inprocess"
    FINAL = "final"


class InspectionMeasurementResult(str, PyEnum):
    OK = "OK"
    NG = "NG"


class NCRDefectCategory(str, PyEnum):
    DIMENSIONAL = "Dimensional"
    MATERIAL = "Material"
    SURFACE = "Surface"
    ASSEMBLY = "Assembly"
    DOCUMENTATION = "Documentation"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class QualityAuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class IncomingInspection(Base, QualityAuditMixin):
    __tablename__ = "incoming_inspections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("grns.id", ondelete="CASCADE"), nullable=False, index=True)
    grn_item_id: Mapped[int] = mapped_column(
        ForeignKey("grn_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[IncomingInspectionStatus] = mapped_column(
        Enum(
            IncomingInspectionStatus,
            name="incoming_inspection_status",
            values_callable=enum_values,
        ),
        default=IncomingInspectionStatus.PENDING,
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    grn: Mapped[object] = relationship("GRN")
    grn_item: Mapped[object] = relationship("GRNItem")
    inspector: Mapped[object] = relationship("User", foreign_keys=[inspected_by])


class FinalInspection(Base, QualityAuditMixin):
    __tablename__ = "final_inspections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[QualityInspectionResult] = mapped_column(
        Enum(
            QualityInspectionResult,
            name="final_inspection_result",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    production_order: Mapped[object] = relationship("ProductionOrder")
    inspector: Mapped[object] = relationship("User", foreign_keys=[inspected_by])


class FAIReport(Base, QualityAuditMixin):
    __tablename__ = "fai_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    drawing_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    revision: Mapped[str] = mapped_column(String(50), nullable=False)
    part_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    inspected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[FAIReportStatus] = mapped_column(
        Enum(
            FAIReportStatus,
            name="fai_report_status",
            values_callable=enum_values,
        ),
        default=FAIReportStatus.PENDING,
        nullable=False,
        index=True,
    )
    attachment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    production_order: Mapped[object] = relationship("ProductionOrder")
    inspector: Mapped[object] = relationship("User", foreign_keys=[inspected_by])


class NCR(Base, QualityAuditMixin):
    __tablename__ = "ncrs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reported_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    defect_category: Mapped[NCRDefectCategory | None] = mapped_column(
        Enum(
            NCRDefectCategory,
            name="ncr_defect_category",
            values_callable=enum_values,
        ),
        nullable=True,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NCRStatus] = mapped_column(
        Enum(
            NCRStatus,
            name="ncr_status",
            values_callable=enum_values,
        ),
        default=NCRStatus.OPEN,
        nullable=False,
        index=True,
    )

    reporter: Mapped[object] = relationship("User", foreign_keys=[reported_by])
    capas: Mapped[list[CAPA]] = relationship(back_populates="ncr", cascade="all, delete-orphan")
    root_cause_analyses: Mapped[list[RootCauseAnalysis]] = relationship(
        back_populates="ncr", cascade="all, delete-orphan"
    )


class CAPA(Base, QualityAuditMixin):
    __tablename__ = "capas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    ncr_id: Mapped[int] = mapped_column(ForeignKey("ncrs.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type: Mapped[CAPAActionType] = mapped_column(
        Enum(
            CAPAActionType,
            name="capa_action_type",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    responsible_person: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CAPAStatus] = mapped_column(
        Enum(
            CAPAStatus,
            name="capa_status",
            values_callable=enum_values,
        ),
        default=CAPAStatus.OPEN,
        nullable=False,
        index=True,
    )

    ncr: Mapped[NCR] = relationship(back_populates="capas")
    responsible_user: Mapped[object] = relationship("User", foreign_keys=[responsible_person])


class RootCauseAnalysis(Base, QualityAuditMixin):
    __tablename__ = "root_cause_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    ncr_id: Mapped[int] = mapped_column(ForeignKey("ncrs.id", ondelete="CASCADE"), nullable=False, index=True)
    method: Mapped[RootCauseMethod] = mapped_column(
        Enum(
            RootCauseMethod,
            name="root_cause_method",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    analysis_text: Mapped[str] = mapped_column(Text, nullable=False)

    ncr: Mapped[NCR] = relationship(back_populates="root_cause_analyses")
    creator: Mapped[object | None] = relationship("User", foreign_keys=lambda: [RootCauseAnalysis.created_by])


class Gauge(Base, QualityAuditMixin):
    __tablename__ = "gauges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    gauge_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    gauge_name: Mapped[str] = mapped_column(String(200), nullable=False)
    last_calibration_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_calibration_due: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[GaugeStatus] = mapped_column(
        Enum(
            GaugeStatus,
            name="gauge_status",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )


class InspectionMeasurement(Base):
    __tablename__ = "inspection_measurements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    inspection_type: Mapped[InspectionMeasurementType] = mapped_column(
        Enum(
            InspectionMeasurementType,
            name="inspection_measurement_type",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    inspection_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    parameter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    specification: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measured_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[InspectionMeasurementResult] = mapped_column(
        Enum(
            InspectionMeasurementResult,
            name="inspection_measurement_result",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    gauge_id: Mapped[int | None] = mapped_column(ForeignKey("gauges.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    gauge: Mapped[Gauge | None] = relationship("Gauge")


class CertificateOfConformance(Base):
    __tablename__ = "certificates_of_conformance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    certificate_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    production_order: Mapped[object] = relationship("ProductionOrder")
    issuer: Mapped[object | None] = relationship("User", foreign_keys=[issued_by])


class QualityMetric(Base):
    __tablename__ = "quality_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)


class AuditPlan(Base, QualityAuditMixin):
    __tablename__ = "audit_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    audit_area: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    auditor: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    auditor_user: Mapped[object] = relationship("User", foreign_keys=[auditor])
    reports: Mapped[list[AuditReport]] = relationship(back_populates="audit_plan", cascade="all, delete-orphan")


class AuditReport(Base, QualityAuditMixin):
    __tablename__ = "audit_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    audit_plan_id: Mapped[int] = mapped_column(
        ForeignKey("audit_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    findings: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    audit_plan: Mapped[AuditPlan] = relationship(back_populates="reports")


class ManagementReviewMeeting(Base, QualityAuditMixin):
    __tablename__ = "management_review_meetings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    participants: Mapped[str] = mapped_column(Text, nullable=False)
    agenda: Mapped[str] = mapped_column(Text, nullable=False)
    minutes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions: Mapped[str | None] = mapped_column(Text, nullable=True)