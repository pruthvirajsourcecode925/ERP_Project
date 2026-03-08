from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.modules.admin.analytics_service import (
    get_dispatch_trend,
    get_machine_utilization,
    get_production_trend,
    get_quality_distribution,
    get_supplier_performance,
    get_user_performance,
)


router = APIRouter(prefix="/dashboard", tags=["admin-analytics"])


@router.get("/production-trend")
def production_trend_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_production_trend(db)


@router.get("/quality-distribution")
def quality_distribution_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_quality_distribution(db)


@router.get("/dispatch-trend")
def dispatch_trend_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_dispatch_trend(db)


@router.get("/supplier-performance")
def supplier_performance_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_supplier_performance(db)


@router.get("/machine-utilization")
def machine_utilization_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_machine_utilization(db)


@router.get("/user-performance")
def user_performance_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin", "Management")),
):
    _ = current_user
    return get_user_performance(db)