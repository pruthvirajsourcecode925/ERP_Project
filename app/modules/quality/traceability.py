from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.production.models import InProcessInspection, ProductionLog, ProductionOperation, ProductionOrder
from app.modules.purchase.models import PurchaseOrder, Supplier
from app.modules.quality.models import FinalInspection, IncomingInspection, NCR
from app.modules.sales.models import Customer, SalesOrder
from app.modules.stores.models import BatchInventory, GRN, GRNItem


class BatchTraceabilityError(Exception):
    pass


def _serialize_supplier(supplier: Supplier | None) -> dict[str, Any] | None:
    if supplier is None:
        return None
    return {
        "id": supplier.id,
        "supplier_code": supplier.supplier_code,
        "supplier_name": supplier.supplier_name,
        "email": supplier.email,
        "phone": supplier.phone,
    }


def _serialize_purchase_order(purchase_order: PurchaseOrder | None) -> dict[str, Any] | None:
    if purchase_order is None:
        return None
    return {
        "id": purchase_order.id,
        "po_number": purchase_order.po_number,
        "status": purchase_order.status.value if purchase_order.status else None,
        "po_date": purchase_order.po_date.isoformat() if purchase_order.po_date else None,
        "sales_order_id": purchase_order.sales_order_id,
    }


def _serialize_grn(grn: GRN | None, grn_item: GRNItem | None) -> dict[str, Any] | None:
    if grn is None:
        return None
    return {
        "id": grn.id,
        "grn_number": grn.grn_number,
        "grn_date": grn.grn_date.isoformat() if grn.grn_date else None,
        "status": grn.status.value if grn.status else None,
        "grn_item_id": grn_item.id if grn_item else None,
        "item_code": grn_item.item_code if grn_item else None,
        "heat_number": grn_item.heat_number if grn_item else None,
    }


def _serialize_production_order(production_order: ProductionOrder) -> dict[str, Any]:
    return {
        "id": production_order.id,
        "production_order_number": production_order.production_order_number,
        "status": production_order.status.value if production_order.status else None,
        "sales_order_id": production_order.sales_order_id,
        "route_card_id": production_order.route_card_id,
        "start_date": production_order.start_date.isoformat() if production_order.start_date else None,
        "due_date": production_order.due_date.isoformat() if production_order.due_date else None,
    }


def _serialize_incoming_inspection(inspection: IncomingInspection) -> dict[str, Any]:
    return {
        "inspection_type": "incoming",
        "id": inspection.id,
        "grn_id": inspection.grn_id,
        "grn_item_id": inspection.grn_item_id,
        "status": inspection.status.value if inspection.status else None,
        "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        "remarks": inspection.remarks,
    }


def _serialize_inprocess_inspection(inspection: InProcessInspection) -> dict[str, Any]:
    return {
        "inspection_type": "inprocess",
        "id": inspection.id,
        "production_operation_id": inspection.production_operation_id,
        "inspection_result": inspection.inspection_result.value if inspection.inspection_result else None,
        "inspection_time": inspection.inspection_time.isoformat() if inspection.inspection_time else None,
        "remarks": inspection.remarks,
    }


def _serialize_final_inspection(inspection: FinalInspection) -> dict[str, Any]:
    return {
        "inspection_type": "final",
        "id": inspection.id,
        "production_order_id": inspection.production_order_id,
        "result": inspection.result.value if inspection.result else None,
        "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        "remarks": inspection.remarks,
    }


def _serialize_ncr(ncr: NCR) -> dict[str, Any]:
    return {
        "id": ncr.id,
        "reference_type": ncr.reference_type,
        "reference_id": ncr.reference_id,
        "defect_category": ncr.defect_category.value if ncr.defect_category else None,
        "description": ncr.description,
        "status": ncr.status.value if ncr.status else None,
        "reported_date": ncr.reported_date.isoformat() if ncr.reported_date else None,
    }


def _serialize_customer(customer: Customer) -> dict[str, Any]:
    return {
        "id": customer.id,
        "customer_code": customer.customer_code,
        "name": customer.name,
        "email": customer.email,
    }


def get_batch_traceability(db: Session, batch_number: str) -> dict[str, Any]:
    normalized_batch_number = batch_number.strip()
    if not normalized_batch_number:
        raise BatchTraceabilityError("batch_number is required")

    batch_inventory = db.scalar(
        select(BatchInventory).where(
            BatchInventory.batch_number == normalized_batch_number,
            BatchInventory.is_deleted.is_(False),
        )
    )
    if batch_inventory is None:
        raise BatchTraceabilityError(f"Batch {normalized_batch_number} not found")

    grn_item = db.scalar(
        select(GRNItem).where(
            GRNItem.batch_number == normalized_batch_number,
            GRNItem.is_deleted.is_(False),
        )
    )

    grn = None
    purchase_order = None
    supplier = None
    if grn_item is not None:
        grn = db.scalar(
            select(GRN).where(
                GRN.id == grn_item.grn_id,
                GRN.is_deleted.is_(False),
            )
        )
    if grn is not None:
        purchase_order = db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == grn.purchase_order_id,
                PurchaseOrder.is_deleted.is_(False),
            )
        )
        supplier = db.scalar(
            select(Supplier).where(
                Supplier.id == grn.supplier_id,
                Supplier.is_deleted.is_(False),
            )
        )

    production_logs = db.scalars(
        select(ProductionLog).where(
            ProductionLog.batch_number == normalized_batch_number,
            ProductionLog.is_deleted.is_(False),
        )
    ).all()

    production_order_ids = sorted({log.production_order_id for log in production_logs})
    production_orders = []
    for production_order_id in production_order_ids:
        production_order = db.scalar(
            select(ProductionOrder).where(
                ProductionOrder.id == production_order_id,
                ProductionOrder.is_deleted.is_(False),
            )
        )
        if production_order is not None:
            production_orders.append(_serialize_production_order(production_order))

    incoming_inspections = []
    if grn_item is not None and grn is not None:
        incoming_inspections = db.scalars(
            select(IncomingInspection).where(
                IncomingInspection.grn_id == grn.id,
                IncomingInspection.grn_item_id == grn_item.id,
                IncomingInspection.is_deleted.is_(False),
            )
        ).all()

    operation_ids = sorted({log.operation_id for log in production_logs})
    inprocess_inspections = []
    if operation_ids:
        inprocess_inspections = db.scalars(
            select(InProcessInspection).where(
                InProcessInspection.production_operation_id.in_(operation_ids),
                InProcessInspection.is_deleted.is_(False),
            )
        ).all()

    final_inspections = []
    if production_order_ids:
        final_inspections = db.scalars(
            select(FinalInspection).where(
                FinalInspection.production_order_id.in_(production_order_ids),
                FinalInspection.is_deleted.is_(False),
            )
        ).all()

    inspections = [
        *[_serialize_incoming_inspection(item) for item in incoming_inspections],
        *[_serialize_inprocess_inspection(item) for item in inprocess_inspections],
        *[_serialize_final_inspection(item) for item in final_inspections],
    ]

    ncr_filters: list[tuple[str, int]] = []
    ncr_filters.extend(("IncomingInspection", inspection.id) for inspection in incoming_inspections)
    ncr_filters.extend(("InProcessInspection", inspection.id) for inspection in inprocess_inspections)
    ncr_filters.extend(("FinalInspection", inspection.id) for inspection in final_inspections)

    ncr_records: list[dict[str, Any]] = []
    seen_ncr_ids: set[int] = set()
    for reference_type, reference_id in ncr_filters:
        matched_ncrs = db.scalars(
            select(NCR).where(
                NCR.reference_type == reference_type,
                NCR.reference_id == reference_id,
                NCR.is_deleted.is_(False),
            )
        ).all()
        for ncr in matched_ncrs:
            if ncr.id not in seen_ncr_ids:
                seen_ncr_ids.add(ncr.id)
                ncr_records.append(_serialize_ncr(ncr))

    customer_ids: set[int] = set()
    if purchase_order is not None and purchase_order.sales_order_id is not None:
        sales_order = db.scalar(
            select(SalesOrder).where(
                SalesOrder.id == purchase_order.sales_order_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if sales_order is not None:
            customer_ids.add(sales_order.customer_id)

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
            customers.append(_serialize_customer(customer))

    return {
        "batch_number": normalized_batch_number,
        "supplier": _serialize_supplier(supplier),
        "purchase_order": _serialize_purchase_order(purchase_order),
        "grn": _serialize_grn(grn, grn_item),
        "production_orders": production_orders,
        "inspections": inspections,
        "ncr_records": ncr_records,
        "customers": customers,
    }


__all__ = ["BatchTraceabilityError", "get_batch_traceability"]