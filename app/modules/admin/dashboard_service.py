from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.dispatch.models import DispatchOrder, DispatchOrderStatus
from app.modules.production.models import ProductionOrder, ProductionOrderStatus
from app.modules.purchase.models import Supplier
from app.modules.quality.models import NCR, NCRStatus
from app.modules.sales.models import Customer


def get_dashboard_summary(db: Session) -> dict[str, int]:
    total_customers = db.scalar(
        select(func.count(Customer.id)).where(Customer.is_deleted.is_(False))
    )
    total_suppliers = db.scalar(
        select(func.count(Supplier.id)).where(Supplier.is_deleted.is_(False))
    )
    active_production_jobs = db.scalar(
        select(func.count(ProductionOrder.id)).where(
            ProductionOrder.is_deleted.is_(False),
            ProductionOrder.status.in_(
                [ProductionOrderStatus.RELEASED, ProductionOrderStatus.IN_PROGRESS]
            ),
        )
    )
    pending_dispatch = db.scalar(
        select(func.count(DispatchOrder.id)).where(
            DispatchOrder.is_deleted.is_(False),
            DispatchOrder.status.in_(
                [
                    DispatchOrderStatus.DRAFT,
                    DispatchOrderStatus.REVIEWED,
                    DispatchOrderStatus.HOLD,
                ]
            ),
        )
    )
    open_ncr = db.scalar(
        select(func.count(NCR.id)).where(
            NCR.is_deleted.is_(False),
            NCR.status.in_([NCRStatus.OPEN, NCRStatus.INVESTIGATING]),
        )
    )

    return {
        "total_customers": int(total_customers or 0),
        "total_suppliers": int(total_suppliers or 0),
        "active_production_jobs": int(active_production_jobs or 0),
        "pending_dispatch": int(pending_dispatch or 0),
        "open_ncr": int(open_ncr or 0),
    }