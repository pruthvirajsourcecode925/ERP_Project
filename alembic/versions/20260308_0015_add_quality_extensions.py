"""add quality model extensions

Revision ID: 20260308_0015
Revises: ec404ae4b937
Create Date: 2026-03-08 01:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260308_0015"
down_revision: Union[str, Sequence[str], None] = "ec404ae4b937"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ncr_defect_category = postgresql.ENUM(
        "Material Defect",
        "Process Deviation",
        "Documentation",
        "Dimensional",
        "Other",
        name="ncr_defect_category",
    )
    inspection_measurement_type = postgresql.ENUM(
        "Incoming",
        "In Process",
        "Final",
        name="inspection_measurement_type",
    )
    inspection_measurement_result = postgresql.ENUM(
        "Pass",
        "Fail",
        name="inspection_measurement_result",
    )
    ncr_defect_category_column_type = postgresql.ENUM(name="ncr_defect_category", create_type=False)
    inspection_measurement_type_column_type = postgresql.ENUM(
        name="inspection_measurement_type",
        create_type=False,
    )
    inspection_measurement_result_column_type = postgresql.ENUM(
        name="inspection_measurement_result",
        create_type=False,
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def index_exists(table_name: str, index_name: str) -> bool:
        return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))

    ncr_defect_category.create(bind, checkfirst=True)
    inspection_measurement_type.create(bind, checkfirst=True)
    inspection_measurement_result.create(bind, checkfirst=True)

    ncr_columns = {column["name"] for column in inspector.get_columns("ncrs")}
    if "defect_category" not in ncr_columns:
        op.add_column("ncrs", sa.Column("defect_category", ncr_defect_category_column_type, nullable=True))
    if not index_exists("ncrs", op.f("ix_ncrs_defect_category")):
        op.create_index(op.f("ix_ncrs_defect_category"), "ncrs", ["defect_category"], unique=False)

    if not inspector.has_table("inspection_measurements"):
        op.create_table(
            "inspection_measurements",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("inspection_type", inspection_measurement_type_column_type, nullable=False),
            sa.Column("inspection_id", sa.BigInteger(), nullable=False),
            sa.Column("parameter_name", sa.String(length=200), nullable=False),
            sa.Column("specification", sa.String(length=255), nullable=True),
            sa.Column("measured_value", sa.String(length=255), nullable=True),
            sa.Column("result", inspection_measurement_result_column_type, nullable=False),
            sa.Column("gauge_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["gauge_id"], ["gauges.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)

    if not index_exists("inspection_measurements", op.f("ix_inspection_measurements_id")):
        op.create_index(op.f("ix_inspection_measurements_id"), "inspection_measurements", ["id"], unique=False)
    if not index_exists("inspection_measurements", op.f("ix_inspection_measurements_inspection_type")):
        op.create_index(
            op.f("ix_inspection_measurements_inspection_type"),
            "inspection_measurements",
            ["inspection_type"],
            unique=False,
        )
    if not index_exists("inspection_measurements", op.f("ix_inspection_measurements_inspection_id")):
        op.create_index(
            op.f("ix_inspection_measurements_inspection_id"),
            "inspection_measurements",
            ["inspection_id"],
            unique=False,
        )
    if not index_exists("inspection_measurements", op.f("ix_inspection_measurements_result")):
        op.create_index(op.f("ix_inspection_measurements_result"), "inspection_measurements", ["result"], unique=False)
    if not index_exists("inspection_measurements", op.f("ix_inspection_measurements_gauge_id")):
        op.create_index(
            op.f("ix_inspection_measurements_gauge_id"),
            "inspection_measurements",
            ["gauge_id"],
            unique=False,
        )

    if not inspector.has_table("certificates_of_conformance"):
        op.create_table(
            "certificates_of_conformance",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("production_order_id", sa.BigInteger(), nullable=False),
            sa.Column("certificate_number", sa.String(length=120), nullable=False),
            sa.Column("issued_by", sa.Integer(), nullable=True),
            sa.Column("issued_date", sa.Date(), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["issued_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["production_order_id"], ["production_orders.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)

    if not index_exists("certificates_of_conformance", op.f("ix_certificates_of_conformance_id")):
        op.create_index(op.f("ix_certificates_of_conformance_id"), "certificates_of_conformance", ["id"], unique=False)
    if not index_exists("certificates_of_conformance", op.f("ix_certificates_of_conformance_production_order_id")):
        op.create_index(
            op.f("ix_certificates_of_conformance_production_order_id"),
            "certificates_of_conformance",
            ["production_order_id"],
            unique=False,
        )
    if not index_exists("certificates_of_conformance", op.f("ix_certificates_of_conformance_certificate_number")):
        op.create_index(
            op.f("ix_certificates_of_conformance_certificate_number"),
            "certificates_of_conformance",
            ["certificate_number"],
            unique=False,
        )
    if not index_exists("certificates_of_conformance", op.f("ix_certificates_of_conformance_issued_by")):
        op.create_index(
            op.f("ix_certificates_of_conformance_issued_by"),
            "certificates_of_conformance",
            ["issued_by"],
            unique=False,
        )
    if not index_exists("certificates_of_conformance", op.f("ix_certificates_of_conformance_issued_date")):
        op.create_index(
            op.f("ix_certificates_of_conformance_issued_date"),
            "certificates_of_conformance",
            ["issued_date"],
            unique=False,
        )

    if not inspector.has_table("quality_metrics"):
        op.create_table(
            "quality_metrics",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("metric_name", sa.String(length=120), nullable=False),
            sa.Column("metric_value", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("recorded_date", sa.Date(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)

    if not index_exists("quality_metrics", op.f("ix_quality_metrics_id")):
        op.create_index(op.f("ix_quality_metrics_id"), "quality_metrics", ["id"], unique=False)
    if not index_exists("quality_metrics", op.f("ix_quality_metrics_metric_name")):
        op.create_index(op.f("ix_quality_metrics_metric_name"), "quality_metrics", ["metric_name"], unique=False)
    if not index_exists("quality_metrics", op.f("ix_quality_metrics_recorded_date")):
        op.create_index(op.f("ix_quality_metrics_recorded_date"), "quality_metrics", ["recorded_date"], unique=False)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_quality_metrics_recorded_date")
    op.execute("DROP INDEX IF EXISTS ix_quality_metrics_metric_name")
    op.execute("DROP INDEX IF EXISTS ix_quality_metrics_id")
    op.execute("DROP TABLE IF EXISTS quality_metrics")

    op.execute("DROP INDEX IF EXISTS ix_certificates_of_conformance_issued_date")
    op.execute("DROP INDEX IF EXISTS ix_certificates_of_conformance_issued_by")
    op.execute("DROP INDEX IF EXISTS ix_certificates_of_conformance_certificate_number")
    op.execute("DROP INDEX IF EXISTS ix_certificates_of_conformance_production_order_id")
    op.execute("DROP INDEX IF EXISTS ix_certificates_of_conformance_id")
    op.execute("DROP TABLE IF EXISTS certificates_of_conformance")

    op.execute("DROP INDEX IF EXISTS ix_inspection_measurements_gauge_id")
    op.execute("DROP INDEX IF EXISTS ix_inspection_measurements_result")
    op.execute("DROP INDEX IF EXISTS ix_inspection_measurements_inspection_id")
    op.execute("DROP INDEX IF EXISTS ix_inspection_measurements_inspection_type")
    op.execute("DROP INDEX IF EXISTS ix_inspection_measurements_id")
    op.execute("DROP TABLE IF EXISTS inspection_measurements")

    op.execute("DROP INDEX IF EXISTS ix_ncrs_defect_category")
    op.execute("ALTER TABLE ncrs DROP COLUMN IF EXISTS defect_category")

    op.execute("DROP TYPE IF EXISTS inspection_measurement_result")
    op.execute("DROP TYPE IF EXISTS inspection_measurement_type")
    op.execute("DROP TYPE IF EXISTS ncr_defect_category")
