from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.dispatch.models import (
    DeliveryChallan,
    DeliveryChallanStatus,
    DispatchChecklist,
    DispatchChecklistStatus,
    DispatchItem,
    DispatchOrder,
    DispatchOrderStatus,
    Invoice,
    InvoiceStatus,
    PackingList,
)
from app.modules.production.models import ProductionOrder
from app.modules.quality.models import CertificateOfConformance
from app.modules.quality.services import QualityBusinessRuleError, validate_final_inspection_required
from app.modules.sales.models import SalesOrder
from app.services.document_numbers import generate_sequential_document_number


class DispatchBusinessRuleError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _generate_number(db: Session, *, prefix: str, model, field_name: str) -> str:
    year = _utc_now().year
    field = getattr(model, field_name)
    return generate_sequential_document_number(
        db,
        field=field,
        prefix=prefix,
        year=year,
    )


def _get_sales_order(db: Session, sales_order_id: int) -> SalesOrder:
    sales_order = db.scalar(
        select(SalesOrder).where(
            SalesOrder.id == sales_order_id,
            SalesOrder.is_deleted.is_(False),
        )
    )
    if not sales_order:
        raise DispatchBusinessRuleError("SalesOrder not found")
    return sales_order


def _get_dispatch_order(db: Session, dispatch_order_id: int) -> DispatchOrder:
    dispatch_order = db.scalar(
        select(DispatchOrder).where(
            DispatchOrder.id == dispatch_order_id,
            DispatchOrder.is_deleted.is_(False),
        )
    )
    if not dispatch_order:
        raise DispatchBusinessRuleError("DispatchOrder not found")
    return dispatch_order


def _get_production_order(db: Session, production_order_id: int) -> ProductionOrder:
    production_order = db.scalar(
        select(ProductionOrder).where(
            ProductionOrder.id == production_order_id,
            ProductionOrder.is_deleted.is_(False),
        )
    )
    if not production_order:
        raise DispatchBusinessRuleError("ProductionOrder not found")
    return production_order


def _get_certificate_of_conformance(db: Session, certificate_id: int) -> CertificateOfConformance:
    certificate = db.scalar(
        select(CertificateOfConformance).where(CertificateOfConformance.id == certificate_id)
    )
    if not certificate:
        raise DispatchBusinessRuleError("CertificateOfConformance not found")
    return certificate


def _get_dispatch_items(db: Session, dispatch_order_id: int) -> list[DispatchItem]:
    return list(
        db.scalars(
            select(DispatchItem)
            .where(
                DispatchItem.dispatch_order_id == dispatch_order_id,
                DispatchItem.is_deleted.is_(False),
            )
            .order_by(DispatchItem.line_number.asc(), DispatchItem.id.asc())
        )
    )


def _get_dispatch_checklists(db: Session, dispatch_order_id: int) -> list[DispatchChecklist]:
    return list(
        db.scalars(
            select(DispatchChecklist)
            .where(
                DispatchChecklist.dispatch_order_id == dispatch_order_id,
                DispatchChecklist.is_deleted.is_(False),
            )
            .order_by(DispatchChecklist.id.asc())
        )
    )


def _ensure_dispatch_not_completed(dispatch_order: DispatchOrder) -> None:
    if dispatch_order.status == DispatchOrderStatus.RELEASED:
        raise DispatchBusinessRuleError("DispatchOrder is already completed")


def _checklist_is_approved(checklists: list[DispatchChecklist]) -> bool:
    if not checklists:
        return False

    approved_statuses = {
        DispatchChecklistStatus.COMPLETED,
        DispatchChecklistStatus.WAIVED,
    }
    return all(item.status in approved_statuses for item in checklists)


def _ensure_checklist_approved(db: Session, dispatch_order_id: int) -> list[DispatchChecklist]:
    checklists = _get_dispatch_checklists(db, dispatch_order_id)
    if not checklists:
        raise DispatchBusinessRuleError("Dispatch checklist approval is required before completing dispatch")

    if not _checklist_is_approved(checklists):
        raise DispatchBusinessRuleError("Dispatch checklist must be fully approved before completing dispatch")

    return checklists


def _ensure_coc_exists_for_dispatch(db: Session, dispatch_order: DispatchOrder, items: list[DispatchItem]) -> CertificateOfConformance:
    if dispatch_order.certificate_of_conformance_id is None:
        raise DispatchBusinessRuleError("Dispatch cannot be completed unless CertificateOfConformance exists")

    certificate = _get_certificate_of_conformance(db, dispatch_order.certificate_of_conformance_id)
    if items:
        production_order_ids = {item.production_order_id for item in items}
        if certificate.production_order_id not in production_order_ids:
            raise DispatchBusinessRuleError(
                "CertificateOfConformance must belong to a production order linked to the dispatch"
            )
    return certificate


def _ensure_final_inspection_passed(db: Session, items: list[DispatchItem]) -> None:
    if not items:
        raise DispatchBusinessRuleError("Dispatch cannot be completed without dispatch items")

    failed_orders: list[str] = []
    for item in items:
        try:
            validate_final_inspection_required(db, production_order_id=item.production_order_id)
        except QualityBusinessRuleError:
            failed_orders.append(str(item.production_order_id))

    if failed_orders:
        failed_text = ", ".join(failed_orders)
        raise DispatchBusinessRuleError(
            "Dispatch not allowed unless final inspection = PASS for all linked production orders. "
            f"Failed production_order_id values: {failed_text}"
        )


def create_dispatch_order(
    db: Session,
    *,
    dispatch_number: str,
    sales_order_id: int,
    dispatch_date: date,
    certificate_of_conformance_id: int | None = None,
    shipping_method: str | None = None,
    destination: str | None = None,
    remarks: str | None = None,
    created_by: int | None = None,
) -> DispatchOrder:
    _get_sales_order(db, sales_order_id)

    if certificate_of_conformance_id is not None:
        _get_certificate_of_conformance(db, certificate_of_conformance_id)

    dispatch_order = DispatchOrder(
        dispatch_number=dispatch_number.strip(),
        sales_order_id=sales_order_id,
        certificate_of_conformance_id=certificate_of_conformance_id,
        dispatch_date=dispatch_date,
        status=DispatchOrderStatus.DRAFT,
        shipping_method=shipping_method,
        destination=destination,
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(dispatch_order)
    db.commit()
    db.refresh(dispatch_order)
    return dispatch_order


def add_dispatch_item(
    db: Session,
    *,
    dispatch_order_id: int,
    production_order_id: int,
    line_number: int,
    item_code: str,
    quantity: Decimal,
    uom: str,
    description: str | None = None,
    lot_number: str | None = None,
    serial_number: str | None = None,
    is_traceability_verified: bool = False,
    remarks: str | None = None,
    created_by: int | None = None,
) -> DispatchItem:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    production_order = _get_production_order(db, production_order_id)
    if production_order.sales_order_id != dispatch_order.sales_order_id:
        raise DispatchBusinessRuleError("ProductionOrder does not belong to the same SalesOrder as the DispatchOrder")

    quantity = _to_decimal(quantity)
    if quantity <= 0:
        raise DispatchBusinessRuleError("quantity must be greater than zero")

    dispatch_item = DispatchItem(
        dispatch_order_id=dispatch_order_id,
        production_order_id=production_order_id,
        line_number=line_number,
        item_code=item_code,
        description=description,
        quantity=quantity,
        uom=uom,
        lot_number=lot_number,
        serial_number=serial_number,
        is_traceability_verified=is_traceability_verified,
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(dispatch_item)
    db.commit()
    db.refresh(dispatch_item)
    return dispatch_item


def generate_packing_list(
    db: Session,
    *,
    dispatch_order_id: int,
    packed_date: date,
    package_count: int = 1,
    gross_weight: Decimal | None = None,
    net_weight: Decimal | None = None,
    dimensions: str | None = None,
    remarks: str | None = None,
    created_by: int | None = None,
) -> PackingList:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    existing = db.scalar(
        select(PackingList).where(
            PackingList.dispatch_order_id == dispatch_order_id,
            PackingList.is_deleted.is_(False),
        )
    )
    if existing:
        raise DispatchBusinessRuleError("PackingList already exists for this DispatchOrder")

    packing_list = PackingList(
        packing_list_number=_generate_number(
            db,
            prefix="PL",
            model=PackingList,
            field_name="packing_list_number",
        ),
        dispatch_order_id=dispatch_order_id,
        packed_date=packed_date,
        package_count=package_count,
        gross_weight=_to_decimal(gross_weight) if gross_weight is not None else None,
        net_weight=_to_decimal(net_weight) if net_weight is not None else None,
        dimensions=dimensions,
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(packing_list)
    db.commit()
    db.refresh(packing_list)
    return packing_list


def generate_invoice(
    db: Session,
    *,
    dispatch_order_id: int,
    invoice_date: date,
    currency: str,
    subtotal: Decimal = Decimal("0.00"),
    tax_amount: Decimal = Decimal("0.00"),
    total_amount: Decimal = Decimal("0.00"),
    remarks: str | None = None,
    created_by: int | None = None,
) -> Invoice:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    existing = db.scalar(
        select(Invoice).where(
            Invoice.dispatch_order_id == dispatch_order_id,
            Invoice.is_deleted.is_(False),
        )
    )
    if existing:
        raise DispatchBusinessRuleError("Invoice already exists for this DispatchOrder")

    invoice = Invoice(
        invoice_number=_generate_number(
            db,
            prefix="INV",
            model=Invoice,
            field_name="invoice_number",
        ),
        dispatch_order_id=dispatch_order_id,
        invoice_date=invoice_date,
        currency=currency,
        subtotal=_to_decimal(subtotal),
        tax_amount=_to_decimal(tax_amount),
        total_amount=_to_decimal(total_amount),
        status=InvoiceStatus.ISSUED,
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def generate_delivery_challan(
    db: Session,
    *,
    dispatch_order_id: int,
    issue_date: date,
    received_by: str | None = None,
    remarks: str | None = None,
    created_by: int | None = None,
) -> DeliveryChallan:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    existing = db.scalar(
        select(DeliveryChallan).where(
            DeliveryChallan.dispatch_order_id == dispatch_order_id,
            DeliveryChallan.is_deleted.is_(False),
        )
    )
    if existing:
        raise DispatchBusinessRuleError("DeliveryChallan already exists for this DispatchOrder")

    delivery_challan = DeliveryChallan(
        challan_number=_generate_number(
            db,
            prefix="DC",
            model=DeliveryChallan,
            field_name="challan_number",
        ),
        dispatch_order_id=dispatch_order_id,
        issue_date=issue_date,
        received_by=received_by,
        status=DeliveryChallanStatus.ISSUED,
        remarks=remarks,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(delivery_challan)
    db.commit()
    db.refresh(delivery_challan)
    return delivery_challan


def verify_dispatch_checklist(
    db: Session,
    *,
    dispatch_order_id: int,
    checklist_item: str,
    status: DispatchChecklistStatus,
    checked_by: int | None = None,
    requirement_reference: str | None = None,
    remarks: str | None = None,
) -> DispatchChecklist:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    checklist = db.scalar(
        select(DispatchChecklist).where(
            DispatchChecklist.dispatch_order_id == dispatch_order_id,
            DispatchChecklist.checklist_item == checklist_item,
            DispatchChecklist.is_deleted.is_(False),
        )
    )

    checked_at = _utc_now() if status in {DispatchChecklistStatus.COMPLETED, DispatchChecklistStatus.WAIVED} else None
    if checklist:
        checklist.requirement_reference = requirement_reference
        checklist.status = status
        checklist.checked_by = checked_by
        checklist.checked_at = checked_at
        checklist.remarks = remarks
        checklist.updated_by = checked_by
    else:
        checklist = DispatchChecklist(
            dispatch_order_id=dispatch_order_id,
            checklist_item=checklist_item,
            requirement_reference=requirement_reference,
            status=status,
            checked_by=checked_by,
            checked_at=checked_at,
            remarks=remarks,
            created_by=checked_by,
            updated_by=checked_by,
        )
        db.add(checklist)

    db.commit()
    db.refresh(checklist)
    return checklist


def complete_dispatch(
    db: Session,
    *,
    dispatch_order_id: int,
    released_by: int,
) -> DispatchOrder:
    dispatch_order = _get_dispatch_order(db, dispatch_order_id)
    _ensure_dispatch_not_completed(dispatch_order)

    items = _get_dispatch_items(db, dispatch_order_id)
    _ensure_final_inspection_passed(db, items)
    _ensure_coc_exists_for_dispatch(db, dispatch_order, items)
    _ensure_checklist_approved(db, dispatch_order_id)

    if not dispatch_order.packing_list:
        raise DispatchBusinessRuleError("PackingList must be generated before completing dispatch")
    if not dispatch_order.invoice:
        raise DispatchBusinessRuleError("Invoice must be generated before completing dispatch")
    if not dispatch_order.delivery_challan:
        raise DispatchBusinessRuleError("DeliveryChallan must be generated before completing dispatch")

    dispatch_order.status = DispatchOrderStatus.RELEASED
    dispatch_order.released_by = released_by
    dispatch_order.released_at = _utc_now()
    dispatch_order.updated_by = released_by

    db.commit()
    db.refresh(dispatch_order)
    return dispatch_order