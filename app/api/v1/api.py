from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, roles, sales, engineering, purchase, stores, production
from app.modules.admin.alerts_router import router as admin_alerts_router
from app.modules.admin.analytics_router import router as admin_analytics_router
from app.modules.dispatch.routers import router as dispatch_router
from app.modules.admin.search_router import router as admin_search_router
from app.modules.admin.audit_router import router as admin_audit_router
from app.modules.admin.dashboard_router import router as admin_dashboard_router
from app.modules.production.report_router import router as production_report_router
from app.modules.quality.routers import router as quality_router
from app.modules.maintenance.routers import router as maintenance_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(sales.router)
api_router.include_router(engineering.router)
api_router.include_router(purchase.router)
api_router.include_router(stores.router)
api_router.include_router(production.router)
api_router.include_router(dispatch_router)
api_router.include_router(admin_search_router)
api_router.include_router(admin_audit_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_analytics_router)
api_router.include_router(admin_alerts_router)
api_router.include_router(production_report_router)
api_router.include_router(quality_router)
api_router.include_router(maintenance_router)
