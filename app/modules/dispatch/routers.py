from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.dispatch.models import DispatchOrder
from app.modules.dispatch.schemas import (
    DeliveryChallanCreate,
    DeliveryChallanResponse,
    DispatchChecklistCreate,
    DispatchChecklistResponse,
    DispatchItemCreate,
    DispatchItemResponse,
    DispatchOrderCreate,
    DispatchOrderResponse,
    InvoiceCreate,
    InvoiceResponse,
    PackingListCreate,
    PackingListResponse,
)
from app.modules.dispatch.reports import (
    DispatchReportGenerationError,
    generate_delivery_challan as generate_delivery_challan_report,
    generate_invoice as generate_invoice_report,
)
from app.modules.dispatch.services import (
    DispatchBusinessRuleError,
    add_dispatch_item,
    complete_dispatch,
    create_dispatch_order,
    generate_delivery_challan as create_delivery_challan_document,
    generate_invoice as create_invoice_document,
    generate_packing_list,
    verify_dispatch_checklist,
)


router = APIRouter(prefix="/dispatch", tags=["dispatch"])


def _raise_dispatch_http_error(exc: DispatchBusinessRuleError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


def _raise_dispatch_report_http_error(exc: DispatchReportGenerationError) -> None:
    detail = str(exc)
    status_code = status.HTTP_404_NOT_FOUND if detail.endswith("not found") else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=detail)


def _ensure_report_path_in_storage(file_path: str) -> str:
    project_root = Path(__file__).resolve().parents[3]
    allowed_dir = (project_root / "storage" / "dispatch_documents").resolve()
    resolved = Path(file_path).resolve()
    if allowed_dir not in resolved.parents:
        raise HTTPException(status_code=500, detail="Generated report path is outside allowed storage folder")
    return str(resolved)


@router.post("/order", response_model=DispatchOrderResponse, status_code=status.HTTP_201_CREATED)
def create_dispatch_order_endpoint(
    payload: DispatchOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return create_dispatch_order(
            db,
            dispatch_number=payload.dispatch_number,
            sales_order_id=payload.sales_order_id,
            dispatch_date=payload.dispatch_date,
            certificate_of_conformance_id=payload.certificate_of_conformance_id,
            shipping_method=payload.shipping_method,
            destination=payload.destination,
            remarks=payload.remarks,
            created_by=current_user.id,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.get("/order", response_model=list[DispatchOrderResponse])
def list_dispatch_orders_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    _ = current_user
    return db.scalars(
        select(DispatchOrder)
        .where(DispatchOrder.is_deleted.is_(False))
        .order_by(DispatchOrder.id.desc())
    ).all()


@router.post("/order/{id}/item", response_model=DispatchItemResponse, status_code=status.HTTP_201_CREATED)
def add_dispatch_item_endpoint(
    id: int,
    payload: DispatchItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return add_dispatch_item(
            db,
            dispatch_order_id=id,
            production_order_id=payload.production_order_id,
            line_number=payload.line_number,
            item_code=payload.item_code,
            quantity=payload.quantity,
            uom=payload.uom,
            description=payload.description,
            lot_number=payload.lot_number,
            serial_number=payload.serial_number,
            is_traceability_verified=payload.is_traceability_verified,
            remarks=payload.remarks,
            created_by=current_user.id,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.post("/order/{id}/checklist", response_model=DispatchChecklistResponse, status_code=status.HTTP_201_CREATED)
def verify_dispatch_checklist_endpoint(
    id: int,
    payload: DispatchChecklistCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return verify_dispatch_checklist(
            db,
            dispatch_order_id=id,
            checklist_item=payload.checklist_item,
            requirement_reference=payload.requirement_reference,
            status=payload.status,
            checked_by=current_user.id,
            remarks=payload.remarks,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.post("/packing-list", response_model=PackingListResponse, status_code=status.HTTP_201_CREATED)
def generate_packing_list_endpoint(
    payload: PackingListCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return generate_packing_list(
            db,
            dispatch_order_id=payload.dispatch_order_id,
            packed_date=payload.packed_date,
            package_count=payload.package_count,
            gross_weight=payload.gross_weight,
            net_weight=payload.net_weight,
            dimensions=payload.dimensions,
            remarks=payload.remarks,
            created_by=current_user.id,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.post("/invoice", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def generate_invoice_endpoint(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return create_invoice_document(
            db,
            dispatch_order_id=payload.dispatch_order_id,
            invoice_date=payload.invoice_date,
            currency=payload.currency,
            subtotal=payload.subtotal,
            tax_amount=payload.tax_amount,
            total_amount=payload.total_amount,
            remarks=payload.remarks,
            created_by=current_user.id,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.post("/challan", response_model=DeliveryChallanResponse, status_code=status.HTTP_201_CREATED)
def generate_delivery_challan_endpoint(
    payload: DeliveryChallanCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return create_delivery_challan_document(
            db,
            dispatch_order_id=payload.dispatch_order_id,
            issue_date=payload.issue_date,
            received_by=payload.received_by,
            remarks=payload.remarks,
            created_by=current_user.id,
        )
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.patch("/order/{id}/ship", response_model=DispatchOrderResponse)
def complete_dispatch_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        return complete_dispatch(db, dispatch_order_id=id, released_by=current_user.id)
    except DispatchBusinessRuleError as exc:
        _raise_dispatch_http_error(exc)


@router.get("/report/invoice/{dispatch_order_id}")
def generate_invoice_report_endpoint(
    dispatch_order_id: int,
    checked_by_name: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        file_path = generate_invoice_report(
            db,
            dispatch_order_id,
            prepared_by_user_id=current_user.id,
            checked_by_name=checked_by_name,
        )
    except DispatchReportGenerationError as exc:
        _raise_dispatch_report_http_error(exc)

    resolved = _ensure_report_path_in_storage(file_path)
    return FileResponse(path=resolved, media_type="application/pdf", filename=Path(resolved).name)


@router.get("/report/challan/{dispatch_order_id}")
def generate_delivery_challan_report_endpoint(
    dispatch_order_id: int,
    checked_by_name: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Dispatch", "Sales", "Quality", module="dispatch")),
):
    try:
        file_path = generate_delivery_challan_report(
            db,
            dispatch_order_id,
            prepared_by_user_id=current_user.id,
            checked_by_name=checked_by_name,
        )
    except DispatchReportGenerationError as exc:
        _raise_dispatch_report_http_error(exc)

    resolved = _ensure_report_path_in_storage(file_path)
    return FileResponse(path=resolved, media_type="application/pdf", filename=Path(resolved).name)