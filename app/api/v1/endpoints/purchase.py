from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.purchase.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, Supplier
from app.services.auth_service import add_audit_log
from app.services.purchase_service import (
    PurchaseBusinessRuleError,
    add_po_item,
    approve_supplier,
    create_purchase_order,
    create_supplier,
    get_purchase_summary,
    remove_po_item,
    soft_delete_po,
    soft_delete_supplier,
    update_po_status,
    update_supplier,
)

router = APIRouter(prefix="/purchase", tags=["purchase"])


class SupplierCreate(BaseModel):
    supplier_code: str
    supplier_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_approved: bool = False
    is_active: bool = True


class SupplierApprove(BaseModel):
    approved: bool = True
    approval_remarks: str | None = None
    quality_acknowledged: bool | None = None


class SupplierUpdate(BaseModel):
    supplier_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None


class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    supplier_name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    is_approved: bool
    approval_date: datetime | None
    approved_by: int | None
    approval_remarks: str | None
    quality_acknowledged: bool
    last_evaluation_date: datetime | None
    evaluation_score: int | None
    evaluation_remarks: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    sales_order_id: int | None = None
    po_date: date
    expected_delivery_date: date | None = None
    remarks: str | None = None
    quality_notes: str | None = None


class PurchaseOrderItemCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrderStatusUpdate(BaseModel):
    status: PurchaseOrderStatus


class PurchaseOrderItemOut(BaseModel):
    id: int
    purchase_order_id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    sales_order_id: int | None
    po_date: date
    expected_delivery_date: date | None
    status: PurchaseOrderStatus
    total_amount: Decimal
    remarks: str | None
    quality_notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderDetailOut(PurchaseOrderOut):
    items: list[PurchaseOrderItemOut] = []


class PurchaseSummaryOut(BaseModel):
    total_suppliers: int
    total_approved_suppliers: int
    total_draft_pos: int
    total_issued_pos: int
    total_closed_pos: int


@router.post("/supplier", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier_endpoint(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = create_supplier(
            db,
            supplier_code=payload.supplier_code,
            supplier_name=payload.supplier_name,
            contact_person=payload.contact_person,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            is_approved=payload.is_approved,
            is_active=payload.is_active,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_CREATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={"supplier_code": supplier.supplier_code, "supplier_name": supplier.supplier_name},
    )

    return supplier


@router.post("/supplier/{supplier_id}/approve", response_model=SupplierOut)
def approve_supplier_endpoint(
    supplier_id: int,
    payload: SupplierApprove,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = approve_supplier(
            db,
            supplier_id=supplier_id,
            approved=payload.approved,
            approval_remarks=payload.approval_remarks,
            quality_acknowledged=payload.quality_acknowledged,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_APPROVAL_UPDATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={
            "is_approved": supplier.is_approved,
            "approval_date": supplier.approval_date.isoformat() if supplier.approval_date else None,
            "approved_by": supplier.approved_by,
            "quality_acknowledged": supplier.quality_acknowledged,
        },
    )

    return supplier


@router.get("/supplier/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted.is_(False))
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.patch("/supplier/{supplier_id}", response_model=SupplierOut)
def update_supplier_endpoint(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        supplier = update_supplier(
            db,
            supplier_id=supplier_id,
            supplier_name=payload.supplier_name,
            contact_person=payload.contact_person,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            is_active=payload.is_active,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_UPDATED",
        table_name="suppliers",
        record_id=supplier.id,
        new_value={"supplier_name": supplier.supplier_name, "is_active": supplier.is_active},
    )
    return supplier


@router.delete("/supplier/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_endpoint(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        soft_delete_supplier(db, supplier_id=supplier_id, updated_by=current_user.id)
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="SUPPLIER_DELETED",
        table_name="suppliers",
        record_id=supplier_id,
        new_value={"is_deleted": True},
    )


@router.get("/supplier", response_model=list[SupplierOut])
def list_suppliers(
    is_approved: bool | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    stmt = select(Supplier).where(Supplier.is_deleted.is_(False))
    if is_approved is not None:
        stmt = stmt.where(Supplier.is_approved.is_(is_approved))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active.is_(is_active))

    suppliers = db.scalars(stmt.order_by(Supplier.id.desc()).offset(skip).limit(limit)).all()
    return suppliers


@router.get("/summary", response_model=PurchaseSummaryOut)
def get_purchase_summary_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    return get_purchase_summary(db)


@router.post("/order", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order_endpoint(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        po = create_purchase_order(
            db,
            supplier_id=payload.supplier_id,
            sales_order_id=payload.sales_order_id,
            po_date=payload.po_date,
            expected_delivery_date=payload.expected_delivery_date,
            remarks=payload.remarks,
            quality_notes=payload.quality_notes,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_CREATED",
        table_name="purchase_orders",
        record_id=po.id,
        new_value={"po_number": po.po_number, "status": po.status.value},
    )

    return po


@router.post("/order/{purchase_order_id}/item", response_model=PurchaseOrderItemOut, status_code=status.HTTP_201_CREATED)
def add_po_item_endpoint(
    purchase_order_id: int,
    payload: PurchaseOrderItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        item = add_po_item(
            db,
            purchase_order_id=purchase_order_id,
            description=payload.description,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            created_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return item


@router.put("/order/{purchase_order_id}/status", response_model=PurchaseOrderOut)
def update_po_status_endpoint(
    purchase_order_id: int,
    payload: PurchaseOrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        po = update_po_status(
            db,
            purchase_order_id=purchase_order_id,
            new_status=payload.status,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_STATUS_CHANGED",
        table_name="purchase_orders",
        record_id=po.id,
        new_value={"status": po.status.value},
    )

    return po


@router.get("/order", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    status: PurchaseOrderStatus | None = Query(None),
    supplier_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    stmt = select(PurchaseOrder).where(PurchaseOrder.is_deleted.is_(False))
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

    orders = db.scalars(stmt.order_by(PurchaseOrder.id.desc()).offset(skip).limit(limit)).all()
    return orders


@router.delete("/order/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order_endpoint(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        soft_delete_po(db, purchase_order_id=purchase_order_id, updated_by=current_user.id)
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="PURCHASE_ORDER_DELETED",
        table_name="purchase_orders",
        record_id=purchase_order_id,
        new_value={"is_deleted": True},
    )


@router.delete("/order/{purchase_order_id}/item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_po_item_endpoint(
    purchase_order_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    try:
        remove_po_item(
            db,
            purchase_order_id=purchase_order_id,
            item_id=item_id,
            updated_by=current_user.id,
        )
    except PurchaseBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/order/{purchase_order_id}", response_model=PurchaseOrderDetailOut)
def get_purchase_order(
    purchase_order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Purchase", "Admin")),
):
    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.is_deleted.is_(False),
        )
    )
    if not po:
        raise HTTPException(status_code=404, detail="PurchaseOrder not found")

    items = db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == purchase_order_id,
            PurchaseOrderItem.is_deleted.is_(False),
        )
    ).all()

    return PurchaseOrderDetailOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        sales_order_id=po.sales_order_id,
        po_date=po.po_date,
        expected_delivery_date=po.expected_delivery_date,
        status=po.status,
        total_amount=po.total_amount,
        remarks=po.remarks,
        quality_notes=po.quality_notes,
        created_at=po.created_at,
        items=[PurchaseOrderItemOut.model_validate(item) for item in items],
    )
