from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from app.core.config import settings
from app.db.base import Base

from app.models.role import Role
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.oauth_state import OAuthState
from app.modules.admin.models_alert_settings import AlertSettings
from app.modules.sales import Customer, Enquiry, ContractReview, Quotation, QuotationItem, CustomerPOReview, SalesOrder
from app.modules.purchase import Supplier, PurchaseOrder, PurchaseOrderItem
from app.modules.dispatch import (
    DispatchOrder,
    DispatchItem,
    DispatchChecklist,
    PackingList,
    Invoice,
    DeliveryChallan,
    ShipmentTracking,
)
from app.modules.engineering import (
    Drawing,
    DrawingRevision,
    RouteCard,
    RouteOperation,
    SpecialProcess,
    RouteOperationSpecialProcess,
    EngineeringReleaseRecord,
)
from app.modules.stores.models import GRN, GRNItem
from app.modules.production.models import ProductionOrder, ProductionOperation, InProcessInspection
from app.modules.quality.models import (
    IncomingInspection,
    FinalInspection,
    FAIReport,
    NCR,
    CAPA,
    RootCauseAnalysis,
    Gauge,
    AuditPlan,
    AuditReport,
    ManagementReviewMeeting,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of
# your application, can be accessed via
# config.get_main_option("key")
def get_url():
    return settings.DATABASE_URL


config.set_main_option("sqlalchemy.url", get_url())

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()