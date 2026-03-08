from __future__ import annotations

from sqlalchemy import String, or_, select
from sqlalchemy.orm import Session

from app.modules.dispatch.models import DispatchOrder
from app.modules.production.models import ProductionOrder
from app.modules.purchase.models import Supplier
from app.modules.sales.models import Customer, SalesOrder
from app.modules.stores.models import BatchInventory


def _like_pattern(query: str) -> str:
    return f"%{query.strip()}%"


def global_search(db: Session, query: str) -> dict[str, list[dict[str, object]]]:
    search_text = query.strip()
    if not search_text:
        return {
            "customers": [],
            "suppliers": [],
            "sales_orders": [],
            "production_orders": [],
            "batches": [],
            "dispatch_orders": [],
        }

    pattern = _like_pattern(search_text)

    customers = db.scalars(
        select(Customer)
        .where(
            Customer.is_deleted.is_(False),
            or_(
                Customer.customer_code.ilike(pattern),
                Customer.name.ilike(pattern),
                Customer.email.ilike(pattern),
            ),
        )
        .order_by(Customer.id.desc())
        .limit(10)
    ).all()

    suppliers = db.scalars(
        select(Supplier)
        .where(
            Supplier.is_deleted.is_(False),
            or_(
                Supplier.supplier_code.ilike(pattern),
                Supplier.supplier_name.ilike(pattern),
                Supplier.email.ilike(pattern),
            ),
        )
        .order_by(Supplier.id.desc())
        .limit(10)
    ).all()

    sales_orders = db.scalars(
        select(SalesOrder)
        .where(
            SalesOrder.is_deleted.is_(False),
            or_(
                SalesOrder.sales_order_number.ilike(pattern),
                SalesOrder.status.cast(String).ilike(pattern),
            ),
        )
        .order_by(SalesOrder.id.desc())
        .limit(10)
    ).all()

    production_orders = db.scalars(
        select(ProductionOrder)
        .where(
            ProductionOrder.is_deleted.is_(False),
            or_(
                ProductionOrder.production_order_number.ilike(pattern),
                ProductionOrder.status.cast(String).ilike(pattern),
            ),
        )
        .order_by(ProductionOrder.id.desc())
        .limit(10)
    ).all()

    batches = db.scalars(
        select(BatchInventory)
        .where(
            BatchInventory.is_deleted.is_(False),
            or_(
                BatchInventory.batch_number.ilike(pattern),
                BatchInventory.item_code.ilike(pattern),
            ),
        )
        .order_by(BatchInventory.id.desc())
        .limit(10)
    ).all()

    dispatch_orders = db.scalars(
        select(DispatchOrder)
        .where(
            DispatchOrder.is_deleted.is_(False),
            or_(
                DispatchOrder.dispatch_number.ilike(pattern),
                DispatchOrder.status.cast(String).ilike(pattern),
            ),
        )
        .order_by(DispatchOrder.id.desc())
        .limit(10)
    ).all()

    return {
        "customers": [
            {
                "id": row.id,
                "customer_code": row.customer_code,
                "name": row.name,
                "email": row.email,
            }
            for row in customers
        ],
        "suppliers": [
            {
                "id": row.id,
                "supplier_code": row.supplier_code,
                "supplier_name": row.supplier_name,
                "email": row.email,
            }
            for row in suppliers
        ],
        "sales_orders": [
            {
                "id": row.id,
                "sales_order_number": row.sales_order_number,
                "status": row.status.value if row.status else None,
            }
            for row in sales_orders
        ],
        "production_orders": [
            {
                "id": row.id,
                "production_order_number": row.production_order_number,
                "status": row.status.value if row.status else None,
            }
            for row in production_orders
        ],
        "batches": [
            {
                "id": row.id,
                "batch_number": row.batch_number,
                "item_code": row.item_code,
                "current_quantity": str(row.current_quantity),
            }
            for row in batches
        ],
        "dispatch_orders": [
            {
                "id": row.id,
                "dispatch_number": row.dispatch_number,
                "status": row.status.value if row.status else None,
            }
            for row in dispatch_orders
        ],
    }
