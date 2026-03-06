from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.modules.purchase.models import PurchaseOrder, PurchaseOrderStatus
from app.modules.stores.models import (
    BatchInventory,
    GRN,
    GRNItem,
    GRNStatus,
    InspectionStatus,
    MTCVerification,
    RMIR,
    StorageLocation,
    StockLedger,
    StockTransactionType,
)


class StoresBusinessRuleError(Exception):
    pass


class StoresNotFoundError(StoresBusinessRuleError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_purchase_order(db: Session, purchase_order_id: int) -> PurchaseOrder:
    purchase_order = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.is_deleted.is_(False),
        )
    )
    if not purchase_order:
        raise StoresBusinessRuleError("PurchaseOrder not found")
    return purchase_order


def _get_grn(db: Session, grn_id: int) -> GRN:
    grn = db.scalar(
        select(GRN).where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
        )
    )
    if not grn:
        raise StoresBusinessRuleError("GRN not found")
    return grn


def _get_grn_item(db: Session, grn_item_id: int) -> GRNItem:
    grn_item = db.scalar(
        select(GRNItem).where(
            GRNItem.id == grn_item_id,
            GRNItem.is_deleted.is_(False),
        )
    )
    if not grn_item:
        raise StoresBusinessRuleError("GRNItem not found")
    return grn_item


def _get_active_storage_location(db: Session, storage_location_id: int) -> StorageLocation:
    location = db.scalar(
        select(StorageLocation).where(
            StorageLocation.id == storage_location_id,
            StorageLocation.is_deleted.is_(False),
        )
    )
    if not location:
        raise StoresBusinessRuleError("Storage location not found")

    if location.is_active is not True:
        raise StoresBusinessRuleError("Selected storage location is inactive")

    return location


def _validate_batch_number_format(batch_number: str) -> str:
    parts = [part.strip() for part in batch_number.split("/")]
    required_prefixes = ("DRW-", "SO-", "CUST-", "HEAT-")

    if len(parts) != 4 or any(not part for part in parts):
        raise StoresBusinessRuleError(
            "Batch number must follow format: DRW-XXXX / SO-XX-XXX / CUST-XXX / HEAT-XX"
        )

    for part, prefix in zip(parts, required_prefixes):
        if not part.startswith(prefix) or len(part) <= len(prefix):
            raise StoresBusinessRuleError(
                "Batch number must follow format: DRW-XXXX / SO-XX-XXX / CUST-XXX / HEAT-XX"
            )

    return " / ".join(parts)


def create_grn(
    db: Session,
    *,
    grn_number: str,
    purchase_order_id: int,
    supplier_id: int,
    storage_location_id: int,
    grn_date: date,
    created_by: int | None = None,
) -> GRN:
    existing_grn = db.scalar(
        select(GRN).where(
            GRN.grn_number == grn_number,
            GRN.is_deleted.is_(False),
        )
    )
    if existing_grn:
        raise StoresBusinessRuleError("GRN number already exists")

    purchase_order = _get_purchase_order(db, purchase_order_id)
    if purchase_order.status != PurchaseOrderStatus.ISSUED:
        raise StoresBusinessRuleError("Cannot create GRN unless PurchaseOrder status is Issued")

    _get_active_storage_location(db, storage_location_id)

    if created_by is None:
        raise StoresBusinessRuleError("Received by user is required")

    grn = GRN(
        grn_number=grn_number,
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_id,
        received_by=created_by,
        received_datetime=_utc_now(),
        grn_date=grn_date,
        status=GRNStatus.DRAFT,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(grn)
    db.commit()
    db.refresh(grn)
    return grn


def add_grn_item(
    db: Session,
    *,
    grn_id: int,
    item_code: str,
    description: str | None,
    heat_number: str | None,
    batch_number: str,
    received_quantity: Decimal,
    accepted_quantity: Decimal,
    rejected_quantity: Decimal,
    created_by: int | None = None,
) -> GRNItem:
    _get_grn(db, grn_id)

    normalized_batch_number = _validate_batch_number_format(batch_number)

    if accepted_quantity + rejected_quantity != received_quantity:
        raise StoresBusinessRuleError("Accepted quantity plus rejected quantity must equal received quantity")

    existing_batch_for_grn = db.scalar(
        select(GRNItem.id).where(
            GRNItem.grn_id == grn_id,
            GRNItem.batch_number == normalized_batch_number,
            GRNItem.is_deleted.is_(False),
        )
    )
    if existing_batch_for_grn:
        raise StoresBusinessRuleError("Batch number already exists for this GRN")

    grn_item = GRNItem(
        grn_id=grn_id,
        item_code=item_code,
        description=description,
        heat_number=heat_number,
        batch_number=normalized_batch_number,
        received_quantity=received_quantity,
        accepted_quantity=accepted_quantity,
        rejected_quantity=rejected_quantity,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(grn_item)
    db.commit()
    db.refresh(grn_item)
    return grn_item


def create_mtc_verification(
    db: Session,
    *,
    grn_item_id: int,
    mtc_number: str,
    chemical_composition_verified: bool,
    mechanical_properties_verified: bool,
    standard_compliance_verified: bool,
    verified_by: int,
    verification_date: date,
    created_by: int | None = None,
) -> MTCVerification:
    _get_grn_item(db, grn_item_id)

    existing_mtc = db.scalar(
        select(MTCVerification).where(
            MTCVerification.grn_item_id == grn_item_id,
            MTCVerification.is_deleted.is_(False),
        )
    )
    if existing_mtc:
        raise StoresBusinessRuleError("MTC verification already exists for this GRN item")

    mtc_verification = MTCVerification(
        grn_item_id=grn_item_id,
        mtc_number=mtc_number,
        chemical_composition_verified=chemical_composition_verified,
        mechanical_properties_verified=mechanical_properties_verified,
        standard_compliance_verified=standard_compliance_verified,
        verified_by=verified_by,
        verification_date=verification_date,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(mtc_verification)
    db.commit()
    db.refresh(mtc_verification)
    return mtc_verification


def perform_rmir_inspection(
    db: Session,
    *,
    grn_item_id: int,
    inspection_date: date,
    inspected_by: int,
    inspection_status: InspectionStatus,
    remarks: str | None = None,
    storage_location_id: int | None = None,
    updated_by: int | None = None,
) -> RMIR:
    grn_item = _get_grn_item(db, grn_item_id)

    if inspection_status == InspectionStatus.ACCEPTED:
        mtc_verification = db.scalar(
            select(MTCVerification).where(
                MTCVerification.grn_item_id == grn_item_id,
                MTCVerification.is_deleted.is_(False),
            )
        )
        if not mtc_verification:
            raise StoresBusinessRuleError("Cannot accept RMIR until MTC verification is completed")
        if storage_location_id is None:
            raise StoresBusinessRuleError("storage_location_id is required when inspection_status is Accepted")

    rmir = db.scalar(
        select(RMIR).where(
            RMIR.grn_item_id == grn_item_id,
            RMIR.is_deleted.is_(False),
        )
    )

    if rmir is None:
        rmir = RMIR(
            grn_item_id=grn_item_id,
            inspection_date=inspection_date,
            inspected_by=inspected_by,
            inspection_status=inspection_status,
            remarks=remarks,
            created_by=updated_by,
            updated_by=updated_by,
        )
        db.add(rmir)
    else:
        rmir.inspection_date = inspection_date
        rmir.inspected_by = inspected_by
        rmir.inspection_status = inspection_status
        rmir.remarks = remarks
        rmir.updated_by = updated_by
        db.add(rmir)

    if inspection_status == InspectionStatus.ACCEPTED:
        accepted_qty = Decimal(str(grn_item.accepted_quantity))
        if accepted_qty <= 0:
            raise StoresBusinessRuleError("Accepted quantity must be greater than zero for inventory posting")

        storage_location = _get_active_storage_location(db, storage_location_id)

        batch_inventory = db.scalar(
            select(BatchInventory).where(
                BatchInventory.batch_number == grn_item.batch_number,
                BatchInventory.is_deleted.is_(False),
            )
        )
        if batch_inventory is None:
            batch_inventory = BatchInventory(
                batch_number=grn_item.batch_number,
                storage_location_id=storage_location.id,
                item_code=grn_item.item_code,
                current_quantity=Decimal("0.000"),
                created_by=updated_by,
                updated_by=updated_by,
            )
            db.add(batch_inventory)
            db.flush()
        else:
            batch_inventory.storage_location_id = storage_location.id

        current_qty = Decimal(str(batch_inventory.current_quantity))
        new_balance = (current_qty + accepted_qty).quantize(Decimal("0.001"))

        batch_inventory.current_quantity = new_balance
        batch_inventory.updated_by = updated_by
        db.add(batch_inventory)

        ledger_entry = StockLedger(
            batch_number=grn_item.batch_number,
            storage_location_id=batch_inventory.storage_location_id,
            transaction_type=StockTransactionType.GRN,
            reference_number=grn_item.grn.grn_number,
            quantity_in=accepted_qty,
            quantity_out=Decimal("0.000"),
            balance_after=new_balance,
            transaction_date=_utc_now(),
            created_by=updated_by,
            updated_by=updated_by,
        )
        db.add(ledger_entry)

    db.commit()
    db.refresh(rmir)
    return rmir


def issue_material_to_production(
    db: Session,
    *,
    batch_number: str,
    storage_location_id: int,
    issue_quantity: Decimal,
    reference_number: str,
    updated_by: int | None = None,
) -> StockLedger:
    if issue_quantity <= 0:
        raise StoresBusinessRuleError("Issue quantity must be greater than zero")

    storage_location = db.scalar(
        select(StorageLocation).where(
            StorageLocation.id == storage_location_id,
            StorageLocation.is_deleted.is_(False),
        )
    )
    if not storage_location:
        raise StoresBusinessRuleError("Storage location not found")
    if storage_location.is_active is not True:
        raise StoresBusinessRuleError("Cannot issue from inactive storage location")

    batch_inventory = db.scalar(
        select(BatchInventory).where(
            BatchInventory.batch_number == batch_number,
            BatchInventory.storage_location_id == storage_location_id,
            BatchInventory.is_deleted.is_(False),
        )
    )
    if not batch_inventory:
        raise StoresBusinessRuleError("Batch inventory not found for selected storage location")

    current_qty = Decimal(str(batch_inventory.current_quantity))
    if issue_quantity > current_qty:
        raise StoresBusinessRuleError("Insufficient batch inventory quantity")

    new_balance = (current_qty - issue_quantity).quantize(Decimal("0.001"))
    batch_inventory.current_quantity = new_balance
    batch_inventory.updated_by = updated_by
    db.add(batch_inventory)

    ledger_entry = StockLedger(
        batch_number=batch_number,
        storage_location_id=storage_location_id,
        transaction_type=StockTransactionType.ISSUE,
        reference_number=reference_number,
        quantity_in=Decimal("0.000"),
        quantity_out=issue_quantity,
        balance_after=new_balance,
        transaction_date=_utc_now(),
        created_by=updated_by,
        updated_by=updated_by,
    )
    db.add(ledger_entry)

    db.commit()
    db.refresh(ledger_entry)
    return ledger_entry


def delete_location(
    db: Session,
    *,
    location_id: int,
    deleted_by: int | None = None,
) -> StorageLocation:
    location = db.scalar(
        select(StorageLocation).where(
            StorageLocation.id == location_id,
            StorageLocation.is_deleted.is_(False),
        )
    )
    if not location:
        raise StoresNotFoundError("Storage location not found")

    has_live_stock = db.scalar(
        select(BatchInventory.id).where(
            BatchInventory.storage_location_id == location_id,
            BatchInventory.current_quantity > 0,
            BatchInventory.is_deleted.is_(False),
        )
    )
    if has_live_stock:
        raise StoresBusinessRuleError("Cannot delete storage location with available stock")

    location.is_active = False
    location.is_deleted = True
    location.updated_by = deleted_by
    db.add(location)

    audit_entry = AuditLog(
        user_id=deleted_by,
        action="STORAGE_LOCATION_DELETED",
        table_name="storage_locations",
        record_id=location.id,
        old_value={
            "location_code": location.location_code,
            "location_name": location.location_name,
            "is_active": True,
            "is_deleted": False,
        },
        new_value={
            "is_active": location.is_active,
            "is_deleted": location.is_deleted,
        },
    )
    db.add(audit_entry)

    db.commit()
    db.refresh(location)
    return location
