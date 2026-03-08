from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.modules.production.models import (
    InProcessInspection,
    InspectionResult,
    ProductionOperation,
    ProductionOperationStatus,
    ProductionOrder,
)
from app.modules.quality.models import (
    AuditPlan,
    AuditReport,
    CAPA,
    CAPAActionType,
    CAPAStatus,
    FAIReport,
    FAIReportStatus,
    FinalInspection,
    Gauge,
    GaugeStatus,
    IncomingInspection,
    IncomingInspectionStatus,
    ManagementReviewMeeting,
    NCR,
    NCRStatus,
    QualityInspectionResult,
    RootCauseAnalysis,
    RootCauseMethod,
)
from app.modules.sales.models import CustomerPOReview, Quotation, SalesOrder
from app.modules.stores.models import GRN, GRNItem


class QualityBusinessRuleError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utc_now().date()


def _field_value(data: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(field_name, default)
    return getattr(data, field_name, default)


def _require_user_id(current_user: Any) -> int:
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        raise QualityBusinessRuleError("Current user is required")
    return int(user_id)


def _coerce_enum(value: Any, enum_cls: type, field_name: str):
    if isinstance(value, enum_cls):
        return value

    if isinstance(value, str):
        for member in enum_cls:
            if value == member.value or value == member.name:
                return member

    allowed = ", ".join(member.value for member in enum_cls)
    raise QualityBusinessRuleError(f"{field_name} must be one of: {allowed}")


def _add_trace_log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    table_name: str,
    record_id: int,
    reference_module: str,
    reference_id: int,
    new_value: dict[str, Any] | None = None,
) -> None:
    payload = {
        "reference_module": reference_module,
        "reference_id": reference_id,
        "logged_at": _utc_now().isoformat(),
    }
    if new_value:
        payload.update(new_value)

    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            new_value=payload,
        )
    )


def _reference_module_for_type(reference_type: str) -> str:
    reference_map = {
        "IncomingInspection": "stores",
        "InProcessInspection": "production",
        "FinalInspection": "dispatch",
        "FAIReport": "production",
    }
    return reference_map.get(reference_type, "quality")


def _get_grn(db: Session, grn_id: int) -> GRN:
    grn = db.scalar(
        select(GRN).where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
        )
    )
    if not grn:
        raise QualityBusinessRuleError("GRN not found")
    return grn


def _get_grn_item(db: Session, grn_item_id: int) -> GRNItem:
    grn_item = db.scalar(
        select(GRNItem).where(
            GRNItem.id == grn_item_id,
            GRNItem.is_deleted.is_(False),
        )
    )
    if not grn_item:
        raise QualityBusinessRuleError("GRNItem not found")
    return grn_item


def _get_production_operation(db: Session, production_operation_id: int) -> ProductionOperation:
    operation = db.scalar(
        select(ProductionOperation).where(
            ProductionOperation.id == production_operation_id,
            ProductionOperation.is_deleted.is_(False),
        )
    )
    if not operation:
        raise QualityBusinessRuleError("ProductionOperation not found")
    return operation


def _get_production_order(db: Session, production_order_id: int) -> ProductionOrder:
    production_order = db.scalar(
        select(ProductionOrder).where(
            ProductionOrder.id == production_order_id,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if not production_order:
        raise QualityBusinessRuleError("ProductionOrder not found")
    return production_order


def _get_sales_order_for_production_order(db: Session, production_order_id: int) -> SalesOrder:
    production_order = _get_production_order(db, production_order_id)
    sales_order = db.scalar(
        select(SalesOrder).where(
            SalesOrder.id == production_order.sales_order_id,
            SalesOrder.is_deleted.is_(False),
        )
    )
    if not sales_order:
        raise QualityBusinessRuleError("SalesOrder not found for the production order")
    return sales_order


def _validate_sales_document_linkage_for_production_order(db: Session, production_order_id: int) -> None:
    sales_order = _get_sales_order_for_production_order(db, production_order_id)

    quotation = db.scalar(
        select(Quotation).where(
            Quotation.id == sales_order.quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )
    if not quotation:
        raise QualityBusinessRuleError("Quotation linkage is required for quality records")

    po_review = db.scalar(
        select(CustomerPOReview).where(
            CustomerPOReview.id == sales_order.customer_po_review_id,
            CustomerPOReview.is_deleted.is_(False),
        )
    )
    if not po_review:
        raise QualityBusinessRuleError("Customer PO review linkage is required for quality records")

    if po_review.quotation_id != quotation.id:
        raise QualityBusinessRuleError("SalesOrder linkage mismatch: Customer PO review is not linked to the same quotation")


def _get_user(db: Session, user_id: int) -> User:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise QualityBusinessRuleError("User not found")
    return user


def _get_incoming_inspection(db: Session, inspection_id: int) -> IncomingInspection:
    inspection = db.scalar(
        select(IncomingInspection).where(
            IncomingInspection.id == inspection_id,
            IncomingInspection.is_deleted.is_(False),
        )
    )
    if not inspection:
        raise QualityBusinessRuleError("IncomingInspection not found")
    return inspection


def _get_inprocess_inspection(db: Session, inspection_id: int) -> InProcessInspection:
    inspection = db.scalar(
        select(InProcessInspection).where(
            InProcessInspection.id == inspection_id,
            InProcessInspection.is_deleted.is_(False),
        )
    )
    if not inspection:
        raise QualityBusinessRuleError("InProcessInspection not found")
    return inspection


def _get_final_inspection(db: Session, inspection_id: int) -> FinalInspection:
    inspection = db.scalar(
        select(FinalInspection).where(
            FinalInspection.id == inspection_id,
            FinalInspection.is_deleted.is_(False),
        )
    )
    if not inspection:
        raise QualityBusinessRuleError("FinalInspection not found")
    return inspection


def _get_ncr(db: Session, ncr_id: int) -> NCR:
    ncr = db.scalar(
        select(NCR).where(
            NCR.id == ncr_id,
            NCR.is_deleted.is_(False),
        )
    )
    if not ncr:
        raise QualityBusinessRuleError("NCR not found")
    return ncr


def _get_fai_report(db: Session, fai_report_id: int) -> FAIReport:
    fai_report = db.scalar(
        select(FAIReport).where(
            FAIReport.id == fai_report_id,
            FAIReport.is_deleted.is_(False),
        )
    )
    if not fai_report:
        raise QualityBusinessRuleError("FAIReport not found")
    return fai_report


def _get_gauge(db: Session, gauge_id: int) -> Gauge:
    gauge = db.scalar(
        select(Gauge).where(
            Gauge.id == gauge_id,
            Gauge.is_deleted.is_(False),
        )
    )
    if not gauge:
        raise QualityBusinessRuleError("Gauge not found")
    return gauge


def _get_audit_plan(db: Session, audit_plan_id: int) -> AuditPlan:
    audit_plan = db.scalar(
        select(AuditPlan).where(
            AuditPlan.id == audit_plan_id,
            AuditPlan.is_deleted.is_(False),
        )
    )
    if not audit_plan:
        raise QualityBusinessRuleError("AuditPlan not found")
    return audit_plan


def _get_latest_incoming_inspection(db: Session, grn_id: int, grn_item_id: int) -> IncomingInspection | None:
    return db.scalars(
        select(IncomingInspection)
        .where(
            IncomingInspection.grn_id == grn_id,
            IncomingInspection.grn_item_id == grn_item_id,
            IncomingInspection.is_deleted.is_(False),
        )
        .order_by(IncomingInspection.inspection_date.desc(), IncomingInspection.id.desc())
    ).first()


def _get_latest_operation_inspection(db: Session, production_operation_id: int) -> InProcessInspection | None:
    return db.scalars(
        select(InProcessInspection)
        .where(
            InProcessInspection.production_operation_id == production_operation_id,
            InProcessInspection.is_deleted.is_(False),
        )
        .order_by(
            func.coalesce(InProcessInspection.inspection_time, InProcessInspection.created_at).desc(),
            InProcessInspection.id.desc(),
        )
    ).first()


def _get_latest_final_inspection(db: Session, production_order_id: int) -> FinalInspection | None:
    return db.scalars(
        select(FinalInspection)
        .where(
            FinalInspection.production_order_id == production_order_id,
            FinalInspection.is_deleted.is_(False),
        )
        .order_by(FinalInspection.inspection_date.desc(), FinalInspection.id.desc())
    ).first()


def _create_ncr_record(
    db: Session,
    *,
    reference_type: str,
    reference_id: int,
    description: str,
    reported_by: int,
) -> NCR:
    _get_user(db, reported_by)

    ncr = NCR(
        reference_type=reference_type,
        reference_id=reference_id,
        reported_by=reported_by,
        reported_date=_utc_now(),
        description=description,
        status=NCRStatus.OPEN,
        created_by=reported_by,
        updated_by=reported_by,
    )
    db.add(ncr)
    db.flush()

    _add_trace_log(
        db,
        user_id=reported_by,
        action="NCR_CREATED",
        table_name="ncrs",
        record_id=ncr.id,
        reference_module=_reference_module_for_type(reference_type),
        reference_id=reference_id,
        new_value={
            "reference_type": reference_type,
            "description": description,
            "status": NCRStatus.OPEN.value,
        },
    )

    if check_repeated_ncr(db, reference_type, reference_id):
        _add_trace_log(
            db,
            user_id=reported_by,
            action="CAPA_RECOMMENDED",
            table_name="ncrs",
            record_id=ncr.id,
            reference_module=_reference_module_for_type(reference_type),
            reference_id=reference_id,
            new_value={"message": "Repeated defect detected more than 3 times. CAPA recommended."},
        )

    return ncr


def create_incoming_inspection(db: Session, data: Any, current_user: Any) -> IncomingInspection:
    grn_id = int(_field_value(data, "grn_id"))
    grn_item_id = int(_field_value(data, "grn_item_id"))
    remarks = _field_value(data, "remarks")
    user_id = _require_user_id(current_user)

    _get_user(db, user_id)
    _get_grn(db, grn_id)
    grn_item = _get_grn_item(db, grn_item_id)

    if grn_item.grn_id != grn_id:
        raise QualityBusinessRuleError("GRNItem does not belong to the selected GRN")

    inspection = IncomingInspection(
        grn_id=grn_id,
        grn_item_id=grn_item_id,
        inspected_by=user_id,
        inspection_date=_today(),
        status=IncomingInspectionStatus.PENDING,
        remarks=remarks,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(inspection)
    db.flush()
    _add_trace_log(
        db,
        user_id=user_id,
        action="INCOMING_INSPECTION_CREATED",
        table_name="incoming_inspections",
        record_id=inspection.id,
        reference_module="stores",
        reference_id=grn_item_id,
        new_value={"status": IncomingInspectionStatus.PENDING.value},
    )
    db.commit()
    db.refresh(inspection)
    return inspection


def update_incoming_inspection_result(db: Session, inspection_id: int, result: Any) -> IncomingInspection:
    inspection = _get_incoming_inspection(db, inspection_id)
    status_value = _coerce_enum(result, IncomingInspectionStatus, "result")

    if status_value == IncomingInspectionStatus.PENDING:
        raise QualityBusinessRuleError("result must be Accepted or Rejected")

    inspection.status = status_value
    inspection.updated_by = inspection.inspected_by
    db.add(inspection)
    _add_trace_log(
        db,
        user_id=inspection.inspected_by,
        action="INCOMING_INSPECTION_UPDATED",
        table_name="incoming_inspections",
        record_id=inspection.id,
        reference_module="stores",
        reference_id=inspection.grn_item_id,
        new_value={"status": status_value.value},
    )

    if status_value == IncomingInspectionStatus.REJECTED:
        _create_ncr_record(
            db,
            reference_type="IncomingInspection",
            reference_id=inspection.id,
            description=inspection.remarks or "Incoming inspection rejected",
            reported_by=inspection.inspected_by,
        )

    db.commit()
    db.refresh(inspection)
    return inspection


def create_inprocess_inspection(db: Session, data: Any, current_user: Any) -> InProcessInspection:
    production_operation_id = int(_field_value(data, "production_operation_id"))
    remarks = _field_value(data, "remarks")
    user_id = _require_user_id(current_user)

    _get_user(db, user_id)
    _get_production_operation(db, production_operation_id)

    inspection = InProcessInspection(
        production_operation_id=production_operation_id,
        inspected_by=user_id,
        inspection_time=_utc_now(),
        inspection_result=InspectionResult.PENDING,
        remarks=remarks,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(inspection)
    db.flush()
    _add_trace_log(
        db,
        user_id=user_id,
        action="INPROCESS_INSPECTION_CREATED",
        table_name="in_process_inspections",
        record_id=inspection.id,
        reference_module="production",
        reference_id=production_operation_id,
        new_value={"result": InspectionResult.PENDING.value},
    )
    db.commit()
    db.refresh(inspection)
    return inspection


def complete_inprocess_inspection(db: Session, inspection_id: int, result: Any) -> InProcessInspection:
    inspection = _get_inprocess_inspection(db, inspection_id)
    operation = _get_production_operation(db, inspection.production_operation_id)
    result_value = _coerce_enum(result, InspectionResult, "result")

    if result_value == InspectionResult.PENDING:
        raise QualityBusinessRuleError("result must be Pass or Fail")

    if operation.status == ProductionOperationStatus.COMPLETED and result_value != InspectionResult.PASS:
        raise QualityBusinessRuleError("Production operation cannot close without Pass inspection")

    inspection.inspection_result = result_value
    inspection.inspection_time = inspection.inspection_time or _utc_now()
    inspection.updated_by = inspection.inspected_by
    db.add(inspection)
    _add_trace_log(
        db,
        user_id=inspection.inspected_by,
        action="INPROCESS_INSPECTION_COMPLETED",
        table_name="in_process_inspections",
        record_id=inspection.id,
        reference_module="production",
        reference_id=inspection.production_operation_id,
        new_value={"result": result_value.value},
    )

    if result_value == InspectionResult.FAIL:
        _create_ncr_record(
            db,
            reference_type="InProcessInspection",
            reference_id=inspection.id,
            description=inspection.remarks or "In-process inspection failed",
            reported_by=inspection.inspected_by or inspection.created_by or inspection.updated_by or 0,
        )

    db.commit()
    db.refresh(inspection)
    return inspection


def create_final_inspection(db: Session, data: Any, current_user: Any) -> FinalInspection:
    production_order_id = int(_field_value(data, "production_order_id"))
    remarks = _field_value(data, "remarks")
    user_id = _require_user_id(current_user)

    _get_user(db, user_id)
    _get_production_order(db, production_order_id)

    # The current model has no Pending state for final inspections, so a non-pass
    # result is used at creation time to keep release blocked until completion.
    inspection = FinalInspection(
        production_order_id=production_order_id,
        inspected_by=user_id,
        inspection_date=_today(),
        result=QualityInspectionResult.FAIL,
        remarks=remarks,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(inspection)
    db.flush()
    _add_trace_log(
        db,
        user_id=user_id,
        action="FINAL_INSPECTION_CREATED",
        table_name="final_inspections",
        record_id=inspection.id,
        reference_module="dispatch",
        reference_id=production_order_id,
        new_value={"result": inspection.result.value},
    )
    db.commit()
    db.refresh(inspection)
    return inspection


def complete_final_inspection(db: Session, inspection_id: int, result: Any) -> FinalInspection:
    inspection = _get_final_inspection(db, inspection_id)
    result_value = _coerce_enum(result, QualityInspectionResult, "result")

    inspection.result = result_value
    inspection.updated_by = inspection.inspected_by
    db.add(inspection)
    _add_trace_log(
        db,
        user_id=inspection.inspected_by,
        action="FINAL_INSPECTION_COMPLETED",
        table_name="final_inspections",
        record_id=inspection.id,
        reference_module="dispatch",
        reference_id=inspection.production_order_id,
        new_value={"result": result_value.value},
    )

    if result_value == QualityInspectionResult.FAIL:
        _create_ncr_record(
            db,
            reference_type="FinalInspection",
            reference_id=inspection.id,
            description=inspection.remarks or "Final inspection failed",
            reported_by=inspection.inspected_by,
        )

    db.commit()
    db.refresh(inspection)
    return inspection


def create_fai_report(db: Session, data: Any, current_user: Any) -> FAIReport:
    production_order_id = int(_field_value(data, "production_order_id"))
    drawing_number = str(_field_value(data, "drawing_number") or "").strip()
    revision = str(_field_value(data, "revision") or "").strip()
    part_number = str(_field_value(data, "part_number") or "").strip()
    attachment_path = _field_value(data, "attachment_path")
    user_id = _require_user_id(current_user)

    if not drawing_number:
        raise QualityBusinessRuleError("drawing_number is required")
    if not revision:
        raise QualityBusinessRuleError("revision is required")
    if not part_number:
        raise QualityBusinessRuleError("part_number is required")

    _get_user(db, user_id)
    _get_production_order(db, production_order_id)
    _validate_sales_document_linkage_for_production_order(db, production_order_id)

    fai_report = FAIReport(
        production_order_id=production_order_id,
        drawing_number=drawing_number,
        revision=revision,
        part_number=part_number,
        inspected_by=user_id,
        inspection_date=_today(),
        status=FAIReportStatus.PENDING,
        attachment_path=attachment_path,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(fai_report)
    db.commit()
    db.refresh(fai_report)
    return fai_report


def get_fai_report(db: Session, fai_report_id: int) -> FAIReport:
    return _get_fai_report(db, fai_report_id)


def create_ncr(db: Session, reference_type: str, reference_id: int, description: str, current_user: Any) -> NCR:
    user_id = _require_user_id(current_user)
    _get_user(db, user_id)

    if reference_type != "FAIReport":
        raise QualityBusinessRuleError("NCR must be linked to an FAI report")

    fai_report = _get_fai_report(db, reference_id)
    _validate_sales_document_linkage_for_production_order(db, fai_report.production_order_id)

    db.begin_nested()
    ncr = _create_ncr_record(
        db,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        reported_by=user_id,
    )
    db.commit()
    db.refresh(ncr)
    return ncr


def list_ncrs(db: Session) -> list[NCR]:
    return db.scalars(
        select(NCR)
        .where(NCR.is_deleted.is_(False))
        .order_by(NCR.reported_date.desc(), NCR.id.desc())
    ).all()


def check_repeated_ncr(db: Session, reference_type: str, reference_id: int) -> bool:
    repeated_count = db.scalar(
        select(func.count(NCR.id)).where(
            NCR.reference_type == reference_type,
            NCR.reference_id == reference_id,
            NCR.is_deleted.is_(False),
        )
    )
    return int(repeated_count or 0) > 3


def close_ncr(db: Session, ncr_id: int, current_user: Any) -> NCR:
    ncr = _get_ncr(db, ncr_id)
    user_id = _require_user_id(current_user)
    _get_user(db, user_id)

    ncr.status = NCRStatus.CLOSED
    ncr.updated_by = user_id
    db.add(ncr)
    db.commit()
    db.refresh(ncr)
    return ncr


def create_capa(db: Session, data: Any, current_user: Any) -> CAPA:
    ncr_id = int(_field_value(data, "ncr_id"))
    action_type = _coerce_enum(_field_value(data, "action_type"), CAPAActionType, "action_type")
    responsible_person = int(_field_value(data, "responsible_person"))
    target_date = _field_value(data, "target_date")
    user_id = _require_user_id(current_user)

    ncr = _get_ncr(db, ncr_id)
    _get_user(db, responsible_person)
    _get_user(db, user_id)

    if ncr.reference_type != "FAIReport":
        raise QualityBusinessRuleError("CAPA must be linked to an NCR that references an FAI report")

    fai_report = _get_fai_report(db, ncr.reference_id)
    _validate_sales_document_linkage_for_production_order(db, fai_report.production_order_id)

    capa = CAPA(
        ncr_id=ncr_id,
        action_type=action_type,
        responsible_person=responsible_person,
        target_date=target_date,
        status=CAPAStatus.OPEN,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(capa)
    db.commit()
    db.refresh(capa)
    return capa


def list_capas(db: Session) -> list[CAPA]:
    return db.scalars(
        select(CAPA)
        .where(CAPA.is_deleted.is_(False))
        .order_by(CAPA.id.desc())
    ).all()


def create_root_cause_analysis(db: Session, data: Any, current_user: Any) -> RootCauseAnalysis:
    ncr_id = int(_field_value(data, "ncr_id"))
    method = _coerce_enum(_field_value(data, "method"), RootCauseMethod, "method")
    analysis_text = _field_value(data, "analysis_text")
    user_id = _require_user_id(current_user)

    _get_ncr(db, ncr_id)
    _get_user(db, user_id)

    analysis = RootCauseAnalysis(
        ncr_id=ncr_id,
        method=method,
        analysis_text=analysis_text,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def check_gauge_validity(db: Session, gauge_id: int) -> Gauge:
    gauge = _get_gauge(db, gauge_id)

    if gauge.next_calibration_due < date.today():
        raise QualityBusinessRuleError("Gauge calibration expired")

    if gauge.status == GaugeStatus.EXPIRED:
        raise QualityBusinessRuleError("Gauge calibration expired")

    return gauge


def create_gauge(db: Session, data: Any) -> Gauge:
    gauge_code = str(_field_value(data, "gauge_code") or "").strip()
    gauge_name = str(_field_value(data, "gauge_name") or "").strip()
    last_calibration_date = _field_value(data, "last_calibration_date")
    next_calibration_due = _field_value(data, "next_calibration_due")

    if not gauge_code:
        raise QualityBusinessRuleError("gauge_code is required")
    if not gauge_name:
        raise QualityBusinessRuleError("gauge_name is required")

    existing_gauge = db.scalar(
        select(Gauge).where(
            Gauge.gauge_code == gauge_code,
            Gauge.is_deleted.is_(False),
        )
    )
    if existing_gauge:
        raise QualityBusinessRuleError("Gauge code already exists")

    status_value = GaugeStatus.EXPIRED if next_calibration_due < date.today() else GaugeStatus.VALID

    gauge = Gauge(
        gauge_code=gauge_code,
        gauge_name=gauge_name,
        last_calibration_date=last_calibration_date,
        next_calibration_due=next_calibration_due,
        status=status_value,
        created_by=None,
        updated_by=None,
    )
    db.add(gauge)
    db.commit()
    db.refresh(gauge)
    return gauge


def list_gauges(db: Session) -> list[Gauge]:
    return db.scalars(
        select(Gauge)
        .where(Gauge.is_deleted.is_(False))
        .order_by(Gauge.next_calibration_due.asc(), Gauge.id.desc())
    ).all()


def create_audit_plan(db: Session, data: Any, current_user: Any) -> AuditPlan:
    audit_area = str(_field_value(data, "audit_area")).strip()
    planned_date = _field_value(data, "planned_date")
    auditor = int(_field_value(data, "auditor"))
    user_id = _require_user_id(current_user)

    if not audit_area:
        raise QualityBusinessRuleError("audit_area is required")

    _get_user(db, auditor)
    _get_user(db, user_id)

    audit_plan = AuditPlan(
        audit_area=audit_area,
        planned_date=planned_date,
        auditor=auditor,
        status="Planned",
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(audit_plan)
    db.commit()
    db.refresh(audit_plan)
    return audit_plan


def create_audit_report(db: Session, data: Any, current_user: Any) -> AuditReport:
    audit_plan_id = int(_field_value(data, "audit_plan_id"))
    findings = _field_value(data, "findings")
    user_id = _require_user_id(current_user)

    _get_audit_plan(db, audit_plan_id)
    _get_user(db, user_id)

    audit_report = AuditReport(
        audit_plan_id=audit_plan_id,
        findings=findings,
        status="Draft",
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(audit_report)
    db.commit()
    db.refresh(audit_report)
    return audit_report


def create_management_review_meeting(db: Session, data: Any, current_user: Any) -> ManagementReviewMeeting:
    user_id = _require_user_id(current_user)
    _get_user(db, user_id)

    meeting = ManagementReviewMeeting(
        meeting_date=_field_value(data, "meeting_date"),
        participants=_field_value(data, "participants"),
        agenda=_field_value(data, "agenda"),
        minutes=_field_value(data, "minutes"),
        actions=_field_value(data, "actions"),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


def validate_grn_inspection_required(db: Session, *, grn_id: int, grn_item_id: int) -> IncomingInspection:
    _get_grn(db, grn_id)
    grn_item = _get_grn_item(db, grn_item_id)

    if grn_item.grn_id != grn_id:
        raise QualityBusinessRuleError("GRNItem does not belong to the selected GRN")

    inspection = _get_latest_incoming_inspection(db, grn_id, grn_item_id)
    if not inspection or inspection.status != IncomingInspectionStatus.ACCEPTED:
        raise QualityBusinessRuleError("Material cannot enter inventory until incoming inspection is accepted.")
    return inspection


def validate_operation_inspection_required(db: Session, *, production_operation_id: int) -> InProcessInspection:
    _get_production_operation(db, production_operation_id)

    inspection = _get_latest_operation_inspection(db, production_operation_id)
    if not inspection or inspection.inspection_result != InspectionResult.PASS:
        raise QualityBusinessRuleError("Operation cannot be completed without passing in-process inspection.")
    return inspection


def validate_final_inspection_required(db: Session, *, production_order_id: int) -> FinalInspection:
    _get_production_order(db, production_order_id)

    inspection = _get_latest_final_inspection(db, production_order_id)
    if not inspection or inspection.result != QualityInspectionResult.PASS:
        raise QualityBusinessRuleError("Dispatch blocked until final inspection is passed.")
    return inspection


__all__ = [
    "QualityBusinessRuleError",
    "create_incoming_inspection",
    "update_incoming_inspection_result",
    "create_inprocess_inspection",
    "complete_inprocess_inspection",
    "create_final_inspection",
    "complete_final_inspection",
    "create_fai_report",
    "get_fai_report",
    "create_ncr",
    "list_ncrs",
    "check_repeated_ncr",
    "close_ncr",
    "create_capa",
    "list_capas",
    "create_root_cause_analysis",
    "check_gauge_validity",
    "create_gauge",
    "list_gauges",
    "create_audit_plan",
    "create_audit_report",
    "create_management_review_meeting",
    "validate_grn_inspection_required",
    "validate_operation_inspection_required",
    "validate_final_inspection_required",
]