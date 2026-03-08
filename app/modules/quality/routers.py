from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.production.models import InProcessInspection, InspectionResult, ProductionLog, ProductionOperation, ProductionOrder
from app.modules.purchase.models import PurchaseOrder
from app.modules.quality.models import FinalInspection, IncomingInspection, IncomingInspectionStatus, NCR, QualityInspectionResult
from app.modules.quality.reports import (
    QualityReportGenerationError,
    generate_audit_report,
    generate_capa_report,
    generate_fai_report,
    generate_fir_report,
    generate_quality_reports_bundle,
    generate_ncr_report,
    generate_traceability_report,
)
from app.modules.quality.traceability import BatchTraceabilityError, get_batch_traceability
from app.modules.quality.schemas import (
    AuditPlanCreate,
    AuditPlanResponse,
    AuditReportCreate,
    AuditReportResponse,
    CAPACreate,
    CAPAResponse,
    FAICreate,
    FAIResponse,
    FinalInspectionCreate,
    FinalInspectionResponse,
    GaugeCreate,
    GaugeResponse,
    IncomingInspectionCreate,
    IncomingInspectionResponse,
    InProcessInspectionCreate,
    InProcessInspectionResponse,
    MRMCreate,
    MRMResponse,
    NCRCreate,
    NCRResponse,
    RootCauseCreate,
    RootCauseResponse,
)
from app.modules.quality.services import (
    QualityBusinessRuleError,
    close_ncr,
    complete_final_inspection,
    complete_inprocess_inspection,
    create_audit_plan,
    create_audit_report,
    create_capa,
    create_fai_report,
    create_final_inspection,
    create_gauge,
    create_incoming_inspection,
    create_inprocess_inspection,
    create_management_review_meeting,
    create_ncr,
    create_root_cause_analysis,
    get_fai_report,
    list_capas,
    list_gauges,
    list_ncrs,
    update_incoming_inspection_result,
)
from app.modules.sales.models import Customer, SalesOrder
from app.modules.stores.models import GRNItem


router = APIRouter(prefix="/quality", tags=["quality"])


class IncomingInspectionResultUpdate(BaseModel):
    result: IncomingInspectionStatus


class InProcessInspectionCompleteRequest(BaseModel):
    result: InspectionResult


class FinalInspectionCompleteRequest(BaseModel):
    result: QualityInspectionResult


def _raise_quality_http_error(exc: QualityBusinessRuleError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


def _build_quality_report_response(file_path: str, filename: str) -> FileResponse:
    return FileResponse(path=file_path, media_type="application/pdf", filename=filename)


def _filename_from_path(file_path: str, fallback: str) -> str:
    name = Path(file_path).name.strip()
    return name or fallback


def _raise_batch_traceability_http_error(exc: BatchTraceabilityError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


def _customer_payload(customer: Customer) -> dict[str, object | None]:
    return {
        "id": customer.id,
        "customer_code": customer.customer_code,
        "name": customer.name,
        "email": customer.email,
    }


def _sales_order_payload(sales_order: SalesOrder) -> dict[str, object | None]:
    return {
        "id": sales_order.id,
        "sales_order_number": sales_order.sales_order_number,
        "status": sales_order.status.value if sales_order.status else None,
        "order_date": sales_order.order_date.isoformat() if sales_order.order_date else None,
        "currency": sales_order.currency,
        "total_amount": str(sales_order.total_amount),
    }


def _customer_list_for_production_order_ids(db: Session, production_order_ids: list[int]) -> list[dict[str, object | None]]:
    customer_ids: set[int] = set()
    for production_order_id in production_order_ids:
        production_order = db.scalar(
            select(ProductionOrder).where(
                ProductionOrder.id == production_order_id,
                ProductionOrder.is_deleted.is_(False),
            )
        )
        if production_order is None:
            continue

        sales_order = db.scalar(
            select(SalesOrder).where(
                SalesOrder.id == production_order.sales_order_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if sales_order is not None:
            customer_ids.add(sales_order.customer_id)

    customers = []
    for customer_id in sorted(customer_ids):
        customer = db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is not None:
            customers.append(_customer_payload(customer))
    return customers


def _inspection_payloads_for_customer(
    db: Session, batch_numbers: list[str], production_order_ids: list[int]
) -> list[dict[str, object | None]]:
    incoming_inspections = []
    if batch_numbers:
        grn_items = db.scalars(
            select(GRNItem).where(
                GRNItem.batch_number.in_(batch_numbers),
                GRNItem.is_deleted.is_(False),
            )
        ).all()
        grn_item_ids = [item.id for item in grn_items]
        if grn_item_ids:
            incoming_rows = db.scalars(
                select(IncomingInspection).where(
                    IncomingInspection.grn_item_id.in_(grn_item_ids),
                    IncomingInspection.is_deleted.is_(False),
                )
            ).all()
            incoming_inspections.extend(
                {
                    "inspection_type": "incoming",
                    "id": inspection.id,
                    "status": inspection.status.value if inspection.status else None,
                    "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
                    "reference_id": inspection.grn_item_id,
                }
                for inspection in incoming_rows
            )

    inprocess_inspections = []
    final_inspections = []
    if production_order_ids:
        operations = db.scalars(
            select(ProductionOperation).where(
                ProductionOperation.production_order_id.in_(production_order_ids),
                ProductionOperation.is_deleted.is_(False),
            )
        ).all()
        operation_ids = [operation.id for operation in operations]
        if operation_ids:
            inprocess_rows = db.scalars(
                select(InProcessInspection).where(
                    InProcessInspection.production_operation_id.in_(operation_ids),
                    InProcessInspection.is_deleted.is_(False),
                )
            ).all()
            inprocess_inspections.extend(
                {
                    "inspection_type": "inprocess",
                    "id": inspection.id,
                    "status": inspection.inspection_result.value if inspection.inspection_result else None,
                    "inspection_date": inspection.inspection_time.isoformat() if inspection.inspection_time else None,
                    "reference_id": inspection.production_operation_id,
                }
                for inspection in inprocess_rows
            )

        final_rows = db.scalars(
            select(FinalInspection).where(
                FinalInspection.production_order_id.in_(production_order_ids),
                FinalInspection.is_deleted.is_(False),
            )
        ).all()
        final_inspections.extend(
            {
                "inspection_type": "final",
                "id": inspection.id,
                "status": inspection.result.value if inspection.result else None,
                "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
                "reference_id": inspection.production_order_id,
            }
            for inspection in final_rows
        )

    return [*incoming_inspections, *inprocess_inspections, *final_inspections]


@router.post(
    "/incoming-inspection",
    response_model=IncomingInspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incoming_inspection_endpoint(
    payload: IncomingInspectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_incoming_inspection(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.patch("/incoming-inspection/{id}/result", response_model=IncomingInspectionResponse)
def update_incoming_inspection_result_endpoint(
    id: int,
    payload: IncomingInspectionResultUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return update_incoming_inspection_result(db, id, payload.result)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post(
    "/inprocess-inspection",
    response_model=InProcessInspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inprocess_inspection_endpoint(
    payload: InProcessInspectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_inprocess_inspection(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.patch("/inprocess-inspection/{id}/complete", response_model=InProcessInspectionResponse)
def complete_inprocess_inspection_endpoint(
    id: int,
    payload: InProcessInspectionCompleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return complete_inprocess_inspection(db, id, payload.result)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post(
    "/final-inspection",
    response_model=FinalInspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_final_inspection_endpoint(
    payload: FinalInspectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_final_inspection(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.patch("/final-inspection/{id}/complete", response_model=FinalInspectionResponse)
def complete_final_inspection_endpoint(
    id: int,
    payload: FinalInspectionCompleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return complete_final_inspection(db, id, payload.result)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/fai", response_model=FAIResponse, status_code=status.HTTP_201_CREATED)
def create_fai_report_endpoint(
    payload: FAICreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_fai_report(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.get("/fai/{id}", response_model=FAIResponse)
def get_fai_report_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return get_fai_report(db, id)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.get("/report/fir/{inspection_id}")
def download_fir_report_endpoint(
    inspection_id: int,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_fir_report(inspection_id)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"FIR_{inspection_id}.pdf"))


@router.get("/report/fai/{fai_id}")
def download_fai_report_endpoint(
    fai_id: int,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_fai_report(fai_id)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"FAI_{fai_id}.pdf"))


@router.get("/report/ncr/{ncr_id}")
def download_ncr_report_endpoint(
    ncr_id: int,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_ncr_report(ncr_id)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"NCR_{ncr_id}.pdf"))


@router.get("/report/capa/{capa_id}")
def download_capa_report_endpoint(
    capa_id: int,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_capa_report(capa_id)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"CAPA_{capa_id}.pdf"))


@router.get("/report/audit/{audit_id}")
def download_audit_report_endpoint(
    audit_id: int,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_audit_report(audit_id)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"AUDIT_{audit_id}.pdf"))


@router.get("/report/trace/{batch_number:path}")
def download_traceability_report_endpoint(
    batch_number: str,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        file_path = generate_traceability_report(batch_number)
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    safe_batch_number = batch_number.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return _build_quality_report_response(file_path, _filename_from_path(file_path, f"TRACE_{safe_batch_number}.pdf"))


@router.get("/report/all")
def download_all_quality_reports_endpoint(
    inspection_id: int,
    fai_id: int,
    ncr_id: int,
    capa_id: int,
    audit_id: int,
    batch_number: str,
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        zip_path = generate_quality_reports_bundle(
            inspection_id=inspection_id,
            fai_id=fai_id,
            ncr_id=ncr_id,
            capa_id=capa_id,
            audit_id=audit_id,
            batch_number=batch_number,
        )
    except QualityReportGenerationError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=_filename_from_path(zip_path, "quality_reports_bundle.zip"),
    )


@router.get("/trace/batch/{batch_number:path}")
def get_batch_traceability_endpoint(
    batch_number: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return get_batch_traceability(db, batch_number)
    except BatchTraceabilityError as exc:
        _raise_batch_traceability_http_error(exc)


@router.get("/trace/ncr/{ncr_id}")
def get_ncr_traceability_endpoint(
    ncr_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    ncr = db.scalar(
        select(NCR).where(
            NCR.id == ncr_id,
            NCR.is_deleted.is_(False),
        )
    )
    if ncr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"NCR {ncr_id} not found")

    production_order_ids: set[int] = set()

    if ncr.reference_type == "IncomingInspection":
        inspection = db.scalar(
            select(IncomingInspection).where(
                IncomingInspection.id == ncr.reference_id,
                IncomingInspection.is_deleted.is_(False),
            )
        )
        if inspection is not None:
            grn_item = db.scalar(
                select(GRNItem).where(
                    GRNItem.id == inspection.grn_item_id,
                    GRNItem.is_deleted.is_(False),
                )
            )
            if grn_item is not None:
                production_logs = db.scalars(
                    select(ProductionLog).where(
                        ProductionLog.batch_number == grn_item.batch_number,
                        ProductionLog.is_deleted.is_(False),
                    )
                ).all()
                production_order_ids.update(log.production_order_id for log in production_logs)
    elif ncr.reference_type == "InProcessInspection":
        inspection = db.scalar(
            select(InProcessInspection).where(
                InProcessInspection.id == ncr.reference_id,
                InProcessInspection.is_deleted.is_(False),
            )
        )
        if inspection is not None:
            operation = db.scalar(
                select(ProductionOperation).where(
                    ProductionOperation.id == inspection.production_operation_id,
                    ProductionOperation.is_deleted.is_(False),
                )
            )
            if operation is not None:
                production_order_ids.add(operation.production_order_id)
    elif ncr.reference_type == "FinalInspection":
        inspection = db.scalar(
            select(FinalInspection).where(
                FinalInspection.id == ncr.reference_id,
                FinalInspection.is_deleted.is_(False),
            )
        )
        if inspection is not None:
            production_order_ids.add(inspection.production_order_id)

    impacted_production_orders = []
    for production_order_id in sorted(production_order_ids):
        production_order = db.scalar(
            select(ProductionOrder).where(
                ProductionOrder.id == production_order_id,
                ProductionOrder.is_deleted.is_(False),
            )
        )
        if production_order is not None:
            impacted_production_orders.append(
                {
                    "id": production_order.id,
                    "production_order_number": production_order.production_order_number,
                    "status": production_order.status.value if production_order.status else None,
                }
            )

    return {
        "ncr_id": ncr.id,
        "defect_description": ncr.description,
        "production_orders": impacted_production_orders,
        "customers_affected": _customer_list_for_production_order_ids(db, sorted(production_order_ids)),
    }


@router.get("/trace/customer/{customer_id}")
def get_customer_traceability_endpoint(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.is_deleted.is_(False),
        )
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

    sales_orders = db.scalars(
        select(SalesOrder).where(
            SalesOrder.customer_id == customer_id,
            SalesOrder.is_deleted.is_(False),
        )
    ).all()

    shipments = [_sales_order_payload(sales_order) for sales_order in sales_orders]
    sales_order_ids = [sales_order.id for sales_order in sales_orders]

    production_orders = db.scalars(
        select(ProductionOrder).where(
            ProductionOrder.sales_order_id.in_(sales_order_ids) if sales_order_ids else False,
            ProductionOrder.is_deleted.is_(False),
        )
    ).all() if sales_order_ids else []
    production_order_ids = [production_order.id for production_order in production_orders]

    production_logs = db.scalars(
        select(ProductionLog).where(
            ProductionLog.production_order_id.in_(production_order_ids) if production_order_ids else False,
            ProductionLog.is_deleted.is_(False),
        )
    ).all() if production_order_ids else []
    batch_numbers = sorted({log.batch_number for log in production_logs})

    return {
        "customer": _customer_payload(customer),
        "shipments": shipments,
        "batch_numbers": batch_numbers,
        "inspections": _inspection_payloads_for_customer(db, batch_numbers, production_order_ids),
    }


@router.post("/ncr", response_model=NCRResponse, status_code=status.HTTP_201_CREATED)
def create_ncr_endpoint(
    payload: NCRCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_ncr(db, payload.reference_type, payload.reference_id, payload.description, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.get("/ncr", response_model=list[NCRResponse])
def list_ncrs_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return list_ncrs(db)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.patch("/ncr/{id}/close", response_model=NCRResponse)
def close_ncr_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return close_ncr(db, id, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/capa", response_model=CAPAResponse, status_code=status.HTTP_201_CREATED)
def create_capa_endpoint(
    payload: CAPACreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_capa(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.get("/capa", response_model=list[CAPAResponse])
def list_capas_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return list_capas(db)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/root-cause", response_model=RootCauseResponse, status_code=status.HTTP_201_CREATED)
def create_root_cause_analysis_endpoint(
    payload: RootCauseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_root_cause_analysis(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/gauge", response_model=GaugeResponse, status_code=status.HTTP_201_CREATED)
def create_gauge_endpoint(
    payload: GaugeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_gauge(db, payload)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.get("/gauge", response_model=list[GaugeResponse])
def list_gauges_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return list_gauges(db)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/audit-plan", response_model=AuditPlanResponse, status_code=status.HTTP_201_CREATED)
def create_audit_plan_endpoint(
    payload: AuditPlanCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_audit_plan(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/audit-report", response_model=AuditReportResponse, status_code=status.HTTP_201_CREATED)
def create_audit_report_endpoint(
    payload: AuditReportCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_audit_report(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)


@router.post("/mrm", response_model=MRMResponse, status_code=status.HTTP_201_CREATED)
def create_management_review_meeting_endpoint(
    payload: MRMCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Quality", "Admin")),
):
    try:
        return create_management_review_meeting(db, payload, current_user)
    except QualityBusinessRuleError as exc:
        _raise_quality_http_error(exc)