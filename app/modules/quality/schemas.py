from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.production.models import InspectionResult
from app.modules.quality.models import (
    CAPAActionType,
    CAPAStatus,
    AuditPlan,
    FAIReportStatus,
    GaugeStatus,
    IncomingInspectionStatus,
    NCRStatus,
    QualityInspectionResult,
    RootCauseMethod,
)


class ORMResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IncomingInspectionCreate(BaseModel):
    grn_id: int
    grn_item_id: int
    remarks: str | None = None


class IncomingInspectionResponse(ORMResponseModel):
    id: int
    grn_id: int
    grn_item_id: int
    inspected_by: int
    inspection_date: date
    status: IncomingInspectionStatus
    remarks: str | None = None


class InProcessInspectionCreate(BaseModel):
    production_operation_id: int
    remarks: str | None = None


class InProcessInspectionResponse(ORMResponseModel):
    id: int
    production_operation_id: int
    inspected_by: int | None = None
    inspection_time: datetime | None = None
    result: InspectionResult = Field(validation_alias="inspection_result")
    remarks: str | None = None


class FinalInspectionCreate(BaseModel):
    production_order_id: int
    remarks: str | None = None


class FinalInspectionResponse(ORMResponseModel):
    id: int
    production_order_id: int
    inspected_by: int
    inspection_date: date
    result: QualityInspectionResult
    remarks: str | None = None


class FAICreate(BaseModel):
    production_order_id: int
    drawing_number: str
    revision: str
    part_number: str
    attachment_path: str | None = None


class FAIResponse(ORMResponseModel):
    id: int
    production_order_id: int
    drawing_number: str
    revision: str
    part_number: str
    inspected_by: int
    inspection_date: date
    status: FAIReportStatus
    attachment_path: str | None = None


class NCRCreate(BaseModel):
    reference_type: str
    reference_id: int
    description: str


class NCRResponse(ORMResponseModel):
    id: int
    reference_type: str
    reference_id: int
    reported_by: int
    reported_date: datetime
    description: str
    status: NCRStatus


class CAPACreate(BaseModel):
    ncr_id: int
    action_type: CAPAActionType
    responsible_person: int
    target_date: date


class CAPAResponse(ORMResponseModel):
    id: int
    ncr_id: int
    action_type: CAPAActionType
    responsible_person: int
    target_date: date
    status: CAPAStatus


class RootCauseCreate(BaseModel):
    ncr_id: int
    method: RootCauseMethod
    analysis_text: str


class RootCauseResponse(ORMResponseModel):
    id: int
    ncr_id: int
    method: RootCauseMethod
    analysis_text: str
    created_by: int | None = None
    created_at: datetime


class GaugeCreate(BaseModel):
    gauge_code: str
    gauge_name: str
    last_calibration_date: date
    next_calibration_due: date


class GaugeResponse(ORMResponseModel):
    id: int
    gauge_code: str
    gauge_name: str
    last_calibration_date: date
    next_calibration_due: date
    status: GaugeStatus


class AuditPlanCreate(BaseModel):
    audit_area: str
    planned_date: date
    auditor: int


class AuditPlanResponse(ORMResponseModel):
    id: int
    audit_area: str
    planned_date: date
    auditor: int
    status: str


class AuditReportCreate(BaseModel):
    audit_plan_id: int
    findings: str


class AuditReportResponse(ORMResponseModel):
    id: int
    audit_plan_id: int
    findings: str
    status: str


class MRMCreate(BaseModel):
    meeting_date: datetime
    participants: str
    agenda: str
    minutes: str | None = None
    actions: str | None = None


class MRMResponse(ORMResponseModel):
    id: int
    meeting_date: datetime
    participants: str
    agenda: str
    minutes: str | None = None
    actions: str | None = None