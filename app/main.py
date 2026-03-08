from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import create_db_and_tables, SessionLocal
from app.modules.admin.models_alert_settings import AlertSettings
from app.modules.dispatch import (
    DeliveryChallan,
    DispatchChecklist,
    DispatchItem,
    DispatchOrder,
    Invoice,
    PackingList,
    ShipmentTracking,
)
from app.modules.quality.reports import ensure_quality_report_directories
from app.services.auth_service import bootstrap_roles_and_admin


_ = AlertSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_db_and_tables()
    ensure_quality_report_directories()
    db = SessionLocal()
    try:
        bootstrap_roles_and_admin(db)
    finally:
        db.close()
    yield
    # Shutdown (add cleanup tasks here if necessary)


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)