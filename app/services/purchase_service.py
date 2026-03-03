from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.purchase.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, Supplier


class PurchaseBusinessRuleError(Exception):
    pass


def _validate_po_dates(*, po_date: date, expected_delivery_date: date | None) -> None:
    if expected_delivery_date is not None and expected_delivery_date < po_date:
        raise PurchaseBusinessRuleError("Expected delivery date must be on or after PO date")


def _generate_po_number(db: Session) -> str:
    year = datetime.now(ZoneInfo("UTC")).year
    pattern = f"PO-{year}-%"
    latest = db.scalars(
        select(PurchaseOrder.po_number)
        .where(PurchaseOrder.po_number.like(pattern))
        .order_by(PurchaseOrder.po_number.desc())
    ).first()

    next_seq = 1
    if latest:
        try:
            next_seq = int(latest.rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            next_seq = 1

    return f"PO-{year}-{next_seq:04d}"


def _get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.is_deleted.is_(False)))
    if not supplier:
        raise PurchaseBusinessRuleError("Supplier not found")
    return supplier


def _get_purchase_order(db: Session, purchase_order_id: int) -> PurchaseOrder:
    po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id, PurchaseOrder.is_deleted.is_(False)))
    if not po:
        raise PurchaseBusinessRuleError("PurchaseOrder not found")
    return po


def _ensure_po_draft(po: PurchaseOrder) -> None:
    if po.status != PurchaseOrderStatus.DRAFT:
        raise PurchaseBusinessRuleError("PurchaseOrder can be modified only in Draft status")


def _recalculate_po_total_amount(db: Session, purchase_order_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(PurchaseOrderItem.line_total), 0))
        .where(
            PurchaseOrderItem.purchase_order_id == purchase_order_id,
            PurchaseOrderItem.is_deleted.is_(False),
        )
    )
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return total.quantize(Decimal("0.01"))


def create_supplier(
    db: Session,
    *,
    supplier_code: str,
    supplier_name: str,
    contact_person: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    is_approved: bool = False,
    is_active: bool = True,
    created_by: int | None = None,
) -> Supplier:
    existing = db.scalar(select(Supplier).where(Supplier.supplier_code == supplier_code))
    if existing:
        raise PurchaseBusinessRuleError("Supplier code already exists")

    supplier = Supplier(
        supplier_code=supplier_code,
        supplier_name=supplier_name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        is_approved=is_approved,
        is_active=is_active,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def approve_supplier(
    db: Session,
    *,
    supplier_id: int,
    approved: bool = True,
    updated_by: int | None = None,
) -> Supplier:
    supplier = _get_supplier(db, supplier_id)
    supplier.is_approved = approved
    supplier.updated_by = updated_by
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def create_purchase_order(
    db: Session,
    *,
    supplier_id: int,
    sales_order_id: int | None = None,
    po_date: date,
    expected_delivery_date: date | None = None,
    remarks: str | None = None,
    created_by: int | None = None,
) -> PurchaseOrder:
    supplier = _get_supplier(db, supplier_id)
    if supplier.is_approved is not True:
        raise PurchaseBusinessRuleError("Cannot create PurchaseOrder for non-approved supplier")

    _validate_po_dates(po_date=po_date, expected_delivery_date=expected_delivery_date)

    duplicate_open_po_stmt = select(PurchaseOrder.id).where(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.is_deleted.is_(False),
        PurchaseOrder.status.in_([PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.ISSUED]),
    )
    if sales_order_id is None:
        duplicate_open_po_stmt = duplicate_open_po_stmt.where(PurchaseOrder.sales_order_id.is_(None))
    else:
        duplicate_open_po_stmt = duplicate_open_po_stmt.where(PurchaseOrder.sales_order_id == sales_order_id)

    has_duplicate_open_po = db.scalar(duplicate_open_po_stmt)
    if has_duplicate_open_po:
        raise PurchaseBusinessRuleError(
            "Open PurchaseOrder already exists for this supplier and sales order"
        )

    purchase_order = PurchaseOrder(
        po_number=_generate_po_number(db),
        supplier_id=supplier_id,
        sales_order_id=sales_order_id,
        po_date=po_date,
        expected_delivery_date=expected_delivery_date,
        status=PurchaseOrderStatus.DRAFT,
        total_amount=Decimal("0.00"),
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(purchase_order)
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


def add_po_item(
    db: Session,
    *,
    purchase_order_id: int,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    created_by: int | None = None,
) -> PurchaseOrderItem:
    po = _get_purchase_order(db, purchase_order_id)
    _ensure_po_draft(po)

    if quantity <= 0:
        raise PurchaseBusinessRuleError("Quantity must be greater than zero")
    if unit_price < 0:
        raise PurchaseBusinessRuleError("Unit price cannot be negative")

    line_total = (quantity * unit_price).quantize(Decimal("0.01"))

    item = PurchaseOrderItem(
        purchase_order_id=purchase_order_id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(item)
    db.flush()

    po.total_amount = _recalculate_po_total_amount(db, purchase_order_id)
    po.updated_by = created_by
    db.add(po)

    db.commit()
    db.refresh(item)
    return item


def update_po_status(
    db: Session,
    *,
    purchase_order_id: int,
    new_status: PurchaseOrderStatus,
    updated_by: int | None = None,
) -> PurchaseOrder:
    po = _get_purchase_order(db, purchase_order_id)

    if po.status == new_status:
        return po

    if po.status == PurchaseOrderStatus.DRAFT and new_status == PurchaseOrderStatus.ISSUED:
        has_items = db.scalar(
            select(PurchaseOrderItem.id).where(
                PurchaseOrderItem.purchase_order_id == purchase_order_id,
                PurchaseOrderItem.is_deleted.is_(False),
            )
        )
        if not has_items:
            raise PurchaseBusinessRuleError("Cannot set status to Issued without at least one item")
    elif po.status == PurchaseOrderStatus.ISSUED and new_status == PurchaseOrderStatus.CLOSED:
        pass
    else:
        raise PurchaseBusinessRuleError("Invalid PurchaseOrder status transition")

    po.status = new_status
    po.updated_by = updated_by
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


def update_supplier(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str | None = None,
    contact_person: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    is_active: bool | None = None,
    updated_by: int | None = None,
) -> Supplier:
    supplier = _get_supplier(db, supplier_id)
    if supplier_name is not None:
        supplier.supplier_name = supplier_name
    if contact_person is not None:
        supplier.contact_person = contact_person
    if phone is not None:
        supplier.phone = phone
    if email is not None:
        supplier.email = email
    if address is not None:
        supplier.address = address
    if is_active is not None and is_active is False and supplier.is_active is True:
        has_open_po = db.scalar(
            select(PurchaseOrder.id).where(
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.status.in_([PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.ISSUED]),
            )
        )
        if has_open_po:
            raise PurchaseBusinessRuleError(
                "Cannot deactivate supplier with open purchase orders"
            )

    if is_active is not None:
        supplier.is_active = is_active
    supplier.updated_by = updated_by
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def soft_delete_supplier(
    db: Session,
    *,
    supplier_id: int,
    updated_by: int | None = None,
) -> None:
    supplier = _get_supplier(db, supplier_id)
    has_active_po = db.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status != PurchaseOrderStatus.CLOSED,
        )
    )
    if has_active_po:
        raise PurchaseBusinessRuleError("Cannot delete supplier with active purchase orders")
    supplier.is_deleted = True
    supplier.updated_by = updated_by
    db.add(supplier)
    db.commit()


def remove_po_item(
    db: Session,
    *,
    purchase_order_id: int,
    item_id: int,
    updated_by: int | None = None,
) -> None:
    po = _get_purchase_order(db, purchase_order_id)
    _ensure_po_draft(po)

    item = db.scalar(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.id == item_id,
            PurchaseOrderItem.purchase_order_id == purchase_order_id,
            PurchaseOrderItem.is_deleted.is_(False),
        )
    )
    if not item:
        raise PurchaseBusinessRuleError("Item not found on this PurchaseOrder")

    item.is_deleted = True
    item.updated_by = updated_by
    db.add(item)
    db.flush()

    po.total_amount = _recalculate_po_total_amount(db, purchase_order_id)
    po.updated_by = updated_by
    db.add(po)
    db.commit()


def soft_delete_po(
    db: Session,
    *,
    purchase_order_id: int,
    updated_by: int | None = None,
) -> None:
    po = _get_purchase_order(db, purchase_order_id)
    _ensure_po_draft(po)

    po.is_deleted = True
    po.updated_by = updated_by
    db.add(po)
    db.commit()


def get_purchase_summary(db: Session) -> dict[str, int]:
    total_suppliers = db.scalar(
        select(func.count(Supplier.id)).where(Supplier.is_deleted.is_(False))
    )
    total_approved_suppliers = db.scalar(
        select(func.count(Supplier.id)).where(
            Supplier.is_deleted.is_(False),
            Supplier.is_approved.is_(True),
        )
    )

    total_draft_pos = db.scalar(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status == PurchaseOrderStatus.DRAFT,
        )
    )
    total_issued_pos = db.scalar(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status == PurchaseOrderStatus.ISSUED,
        )
    )
    total_closed_pos = db.scalar(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status == PurchaseOrderStatus.CLOSED,
        )
    )

    return {
        "total_suppliers": int(total_suppliers or 0),
        "total_approved_suppliers": int(total_approved_suppliers or 0),
        "total_draft_pos": int(total_draft_pos or 0),
        "total_issued_pos": int(total_issued_pos or 0),
        "total_closed_pos": int(total_closed_pos or 0),
    }
