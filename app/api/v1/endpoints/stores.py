from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.stores.models import (
    BatchInventory,
    GRN,
    GRNItem,
    GRNStatus,
    InspectionStatus,
    StorageLocation,
)
from app.services.auth_service import add_audit_log
from app.services.stores_service import (
    StoresBusinessRuleError,
    StoresNotFoundError,
    add_grn_item,
    create_grn,
    create_mtc_verification,
    delete_location,
    issue_material_to_production,
    perform_rmir_inspection,
)

router = APIRouter(prefix="/stores", tags=["stores"])


class GRNCreate(BaseModel):
    grn_number: str
    purchase_order_id: int
    supplier_id: int
    grn_date: date


class GRNOut(BaseModel):
    id: int
    grn_number: str
    purchase_order_id: int
    supplier_id: int
    grn_date: date
    status: GRNStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class GRNItemCreate(BaseModel):
    item_code: str
    description: str | None = None
    heat_number: str | None = None
    batch_number: str
    received_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal


class GRNItemOut(BaseModel):
    id: int
    grn_id: int
    item_code: str
    description: str | None
    heat_number: str | None
    batch_number: str
    received_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal

    model_config = {"from_attributes": True}


class MTCVerificationCreate(BaseModel):
    mtc_number: str
    chemical_composition_verified: bool
    mechanical_properties_verified: bool
    standard_compliance_verified: bool
    verification_date: date


class InspectionCreate(BaseModel):
    inspection_date: date
    inspection_status: InspectionStatus
    remarks: str | None = None
    storage_location_id: int | None = None


class BatchInventoryOut(BaseModel):
    id: int
    batch_number: str
    item_code: str
    current_quantity: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class IssueMaterialRequest(BaseModel):
    batch_number: str
    storage_location_id: int
    issue_quantity: Decimal
    reference_number: str


class StorageLocationCreate(BaseModel):
    location_code: str
    location_name: str
    description: str | None = None
    is_active: bool = True


class StorageLocationUpdate(BaseModel):
    location_code: str | None = None
    location_name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class StorageLocationOut(BaseModel):
    id: int
    location_code: str
    location_name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("/grn", response_model=GRNOut, status_code=status.HTTP_201_CREATED)
def create_grn_endpoint(
    payload: GRNCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        grn = create_grn(
            db,
            grn_number=payload.grn_number,
            purchase_order_id=payload.purchase_order_id,
            supplier_id=payload.supplier_id,
            grn_date=payload.grn_date,
            created_by=current_user.id,
        )
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="GRN_CREATED",
        table_name="grns",
        record_id=grn.id,
        new_value={
            "grn_number": grn.grn_number,
            "purchase_order_id": grn.purchase_order_id,
            "supplier_id": grn.supplier_id,
        },
    )

    return grn


@router.post("/grn/{id}/item", response_model=GRNItemOut, status_code=status.HTTP_201_CREATED)
def add_grn_item_endpoint(
    id: int,
    payload: GRNItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        grn_item = add_grn_item(
            db,
            grn_id=id,
            item_code=payload.item_code,
            description=payload.description,
            heat_number=payload.heat_number,
            batch_number=payload.batch_number,
            received_quantity=payload.received_quantity,
            accepted_quantity=payload.accepted_quantity,
            rejected_quantity=payload.rejected_quantity,
            created_by=current_user.id,
        )
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return grn_item


@router.post("/grn/{id}/mtc", status_code=status.HTTP_201_CREATED)
def create_mtc_verification_endpoint(
    id: int,
    payload: MTCVerificationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        mtc = create_mtc_verification(
            db,
            grn_item_id=id,
            mtc_number=payload.mtc_number,
            chemical_composition_verified=payload.chemical_composition_verified,
            mechanical_properties_verified=payload.mechanical_properties_verified,
            standard_compliance_verified=payload.standard_compliance_verified,
            verified_by=current_user.id,
            verification_date=payload.verification_date,
            created_by=current_user.id,
        )
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "id": mtc.id,
        "grn_item_id": mtc.grn_item_id,
        "mtc_number": mtc.mtc_number,
    }


@router.post("/grn/{id}/inspect", status_code=status.HTTP_200_OK)
def perform_rmir_inspection_endpoint(
    id: int,
    payload: InspectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        rmir = perform_rmir_inspection(
            db,
            grn_item_id=id,
            inspection_date=payload.inspection_date,
            inspected_by=current_user.id,
            inspection_status=payload.inspection_status,
            remarks=payload.remarks,
            storage_location_id=payload.storage_location_id,
            updated_by=current_user.id,
        )
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="RMIR_INSPECTION_PERFORMED",
        table_name="rmir_reports",
        record_id=rmir.id,
        new_value={
            "grn_item_id": rmir.grn_item_id,
            "inspection_status": rmir.inspection_status.value,
        },
    )

    return {
        "id": rmir.id,
        "grn_item_id": rmir.grn_item_id,
        "inspection_status": rmir.inspection_status.value,
    }


@router.get("/grn", response_model=list[GRNOut])
def list_grns(
    status_filter: GRNStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    stmt = select(GRN).where(GRN.is_deleted.is_(False))
    if status_filter is not None:
        stmt = stmt.where(GRN.status == status_filter)

    items = db.scalars(stmt.order_by(GRN.id.desc()).offset(skip).limit(limit)).all()
    return items


@router.get("/batch-inventory", response_model=list[BatchInventoryOut])
def list_batch_inventory(
    item_code: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    stmt = select(BatchInventory).where(BatchInventory.is_deleted.is_(False))
    if item_code:
        stmt = stmt.where(BatchInventory.item_code == item_code)

    items = db.scalars(stmt.order_by(BatchInventory.id.desc()).offset(skip).limit(limit)).all()
    return items


@router.post("/issue", status_code=status.HTTP_201_CREATED)
def issue_material_endpoint(
    payload: IssueMaterialRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        ledger_entry = issue_material_to_production(
            db,
            batch_number=payload.batch_number,
            storage_location_id=payload.storage_location_id,
            issue_quantity=payload.issue_quantity,
            reference_number=payload.reference_number,
            updated_by=current_user.id,
        )
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    add_audit_log(
        db=db,
        user_id=current_user.id,
        action="MATERIAL_ISSUED_TO_PRODUCTION",
        table_name="stock_ledger",
        record_id=ledger_entry.id,
        new_value={
            "batch_number": ledger_entry.batch_number,
            "quantity_out": str(ledger_entry.quantity_out),
            "reference_number": ledger_entry.reference_number,
        },
    )

    return {
        "id": ledger_entry.id,
        "batch_number": ledger_entry.batch_number,
        "transaction_type": ledger_entry.transaction_type.value,
        "quantity_out": str(ledger_entry.quantity_out),
        "balance_after": str(ledger_entry.balance_after),
    }


@router.post("/location", response_model=StorageLocationOut, status_code=status.HTTP_201_CREATED)
def create_storage_location_endpoint(
    payload: StorageLocationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    existing = db.scalar(
        select(StorageLocation).where(
            StorageLocation.location_code == payload.location_code,
            StorageLocation.is_deleted.is_(False),
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Storage location code already exists")

    location = StorageLocation(
        location_code=payload.location_code,
        location_name=payload.location_name,
        description=payload.description,
        is_active=payload.is_active,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/location", response_model=list[StorageLocationOut], status_code=status.HTTP_200_OK)
def list_storage_locations_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    items = db.scalars(
        select(StorageLocation)
        .where(StorageLocation.is_deleted.is_(False))
        .order_by(StorageLocation.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return items


@router.patch("/location/{id}", response_model=StorageLocationOut, status_code=status.HTTP_200_OK)
def update_storage_location_endpoint(
    id: int,
    payload: StorageLocationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    location = db.scalar(
        select(StorageLocation).where(
            StorageLocation.id == id,
            StorageLocation.is_deleted.is_(False),
        )
    )
    if not location:
        raise HTTPException(status_code=404, detail="Storage location not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    if "location_code" in update_data:
        existing = db.scalar(
            select(StorageLocation).where(
                StorageLocation.location_code == update_data["location_code"],
                StorageLocation.id != id,
                StorageLocation.is_deleted.is_(False),
            )
        )
        if existing:
            raise HTTPException(status_code=400, detail="Storage location code already exists")

    for field, value in update_data.items():
        setattr(location, field, value)
    location.updated_by = current_user.id

    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.delete("/location/{id}", status_code=status.HTTP_200_OK)
def delete_storage_location_endpoint(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Stores", "Admin")),
):
    try:
        location = delete_location(db, location_id=id, deleted_by=current_user.id)
    except StoresNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StoresBusinessRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "id": location.id,
        "location_code": location.location_code,
        "is_active": location.is_active,
        "is_deleted": location.is_deleted,
    }
