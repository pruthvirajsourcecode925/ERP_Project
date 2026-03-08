from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.admin.models_alert_settings import AlertSettings
from app.modules.dispatch.models import DispatchOrder, DispatchOrderStatus
from app.modules.maintenance.models import BreakdownReport, BreakdownStatus
from app.modules.quality.models import NCR, NCRStatus
from app.modules.stores.models import BatchInventory


LOW_STOCK_THRESHOLD = Decimal("10.000")


def get_system_alerts(db: Session) -> list[dict[str, str]]:
    settings = db.scalar(select(AlertSettings).where(AlertSettings.id == 1))
    if settings is not None and settings.alerts_enabled is False:
        return []

    alerts: list[dict[str, str]] = []

    low_stock_count = db.scalar(
        select(func.count(BatchInventory.id)).where(
            BatchInventory.is_deleted.is_(False),
            BatchInventory.current_quantity < LOW_STOCK_THRESHOLD,
        )
    )
    if int(low_stock_count or 0) > 0:
        alerts.append(
            {
                "type": "LOW_STOCK",
                "message": "Stock below threshold",
                "severity": "warning",
            }
        )

    open_breakdown_count = db.scalar(
        select(func.count(BreakdownReport.id)).where(
            BreakdownReport.is_deleted.is_(False),
            BreakdownReport.status == BreakdownStatus.OPEN,
        )
    )
    if int(open_breakdown_count or 0) > 0:
        alerts.append(
            {
                "type": "MACHINE_BREAKDOWN",
                "message": "Open machine breakdown reports require attention",
                "severity": "critical",
            }
        )

    pending_dispatch_count = db.scalar(
        select(func.count(DispatchOrder.id)).where(
            DispatchOrder.is_deleted.is_(False),
            DispatchOrder.status != DispatchOrderStatus.RELEASED,
        )
    )
    if int(pending_dispatch_count or 0) > 0:
        alerts.append(
            {
                "type": "PENDING_DISPATCH",
                "message": "Dispatch orders are pending release",
                "severity": "warning",
            }
        )

    open_ncr_count = db.scalar(
        select(func.count(NCR.id)).where(
            NCR.is_deleted.is_(False),
            NCR.status == NCRStatus.OPEN,
        )
    )
    if int(open_ncr_count or 0) > 0:
        alerts.append(
            {
                "type": "OPEN_NCR",
                "message": "Open NCR records require action",
                "severity": "critical",
            }
        )

    return alerts