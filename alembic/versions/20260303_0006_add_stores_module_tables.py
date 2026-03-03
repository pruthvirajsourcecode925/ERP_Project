"""add stores module tables

Revision ID: 20260303_0006
Revises: 20260303_0005
Create Date: 2026-03-03 22:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260303_0006"
down_revision: Union[str, None] = "20260303_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'grn_status') THEN
                CREATE TYPE grn_status AS ENUM ('Draft', 'UnderInspection', 'Accepted', 'Rejected');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rmir_inspection_status') THEN
                CREATE TYPE rmir_inspection_status AS ENUM ('Pending', 'Accepted', 'Rejected');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'stock_transaction_type') THEN
                CREATE TYPE stock_transaction_type AS ENUM ('GRN', 'ISSUE');
            END IF;
        END
        $$;
        """
    )

    grn_status = postgresql.ENUM("Draft", "UnderInspection", "Accepted", "Rejected", name="grn_status", create_type=False)
    rmir_status = postgresql.ENUM("Pending", "Accepted", "Rejected", name="rmir_inspection_status", create_type=False)
    stock_txn_type = postgresql.ENUM("GRN", "ISSUE", name="stock_transaction_type", create_type=False)

    op.create_table(
        "grns",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grn_number", sa.String(length=40), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("grn_date", sa.Date(), nullable=False),
        sa.Column("status", grn_status, nullable=False, server_default="Draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("grn_number", name="uq_grns_grn_number"),
    )
    op.create_index("ix_grns_grn_number", "grns", ["grn_number"], unique=False)
    op.create_index("ix_grns_purchase_order_id", "grns", ["purchase_order_id"], unique=False)
    op.create_index("ix_grns_supplier_id", "grns", ["supplier_id"], unique=False)
    op.create_index("ix_grns_status", "grns", ["status"], unique=False)
    op.create_index("ix_grns_created_by", "grns", ["created_by"], unique=False)
    op.create_index("ix_grns_updated_by", "grns", ["updated_by"], unique=False)
    op.create_index("ix_grns_is_deleted", "grns", ["is_deleted"], unique=False)

    op.create_table(
        "grn_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grn_id", sa.BigInteger(), nullable=False),
        sa.Column("item_code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("heat_number", sa.String(length=100), nullable=True),
        sa.Column("batch_number", sa.String(length=100), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 3), nullable=False, server_default="0.000"),
        sa.Column("rejected_quantity", sa.Numeric(18, 3), nullable=False, server_default="0.000"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("batch_number", name="uq_grn_items_batch_number"),
        sa.CheckConstraint("received_quantity > 0", name="ck_grn_items_received_qty_gt_zero"),
        sa.CheckConstraint("accepted_quantity >= 0", name="ck_grn_items_accepted_qty_gte_zero"),
        sa.CheckConstraint("rejected_quantity >= 0", name="ck_grn_items_rejected_qty_gte_zero"),
        sa.CheckConstraint("accepted_quantity + rejected_quantity = received_quantity", name="ck_grn_items_qty_balance"),
    )
    op.create_index("ix_grn_items_grn_id", "grn_items", ["grn_id"], unique=False)
    op.create_index("ix_grn_items_item_code", "grn_items", ["item_code"], unique=False)
    op.create_index("ix_grn_items_batch_number", "grn_items", ["batch_number"], unique=False)
    op.create_index("ix_grn_items_created_by", "grn_items", ["created_by"], unique=False)
    op.create_index("ix_grn_items_updated_by", "grn_items", ["updated_by"], unique=False)
    op.create_index("ix_grn_items_is_deleted", "grn_items", ["is_deleted"], unique=False)

    op.create_table(
        "rmir_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grn_item_id", sa.BigInteger(), nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=False),
        sa.Column("inspected_by", sa.Integer(), nullable=False),
        sa.Column("inspection_status", rmir_status, nullable=False, server_default="Pending"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["grn_item_id"], ["grn_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inspected_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("grn_item_id", name="uq_rmir_reports_grn_item_id"),
    )
    op.create_index("ix_rmir_reports_grn_item_id", "rmir_reports", ["grn_item_id"], unique=False)
    op.create_index("ix_rmir_reports_inspected_by", "rmir_reports", ["inspected_by"], unique=False)
    op.create_index("ix_rmir_reports_inspection_status", "rmir_reports", ["inspection_status"], unique=False)
    op.create_index("ix_rmir_reports_created_by", "rmir_reports", ["created_by"], unique=False)
    op.create_index("ix_rmir_reports_updated_by", "rmir_reports", ["updated_by"], unique=False)
    op.create_index("ix_rmir_reports_is_deleted", "rmir_reports", ["is_deleted"], unique=False)

    op.create_table(
        "mtc_verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grn_item_id", sa.BigInteger(), nullable=False),
        sa.Column("mtc_number", sa.String(length=120), nullable=False),
        sa.Column("chemical_composition_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("mechanical_properties_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("standard_compliance_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_by", sa.Integer(), nullable=False),
        sa.Column("verification_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["grn_item_id"], ["grn_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("grn_item_id", name="uq_mtc_verifications_grn_item_id"),
    )
    op.create_index("ix_mtc_verifications_grn_item_id", "mtc_verifications", ["grn_item_id"], unique=False)
    op.create_index("ix_mtc_verifications_mtc_number", "mtc_verifications", ["mtc_number"], unique=False)
    op.create_index("ix_mtc_verifications_verified_by", "mtc_verifications", ["verified_by"], unique=False)
    op.create_index("ix_mtc_verifications_created_by", "mtc_verifications", ["created_by"], unique=False)
    op.create_index("ix_mtc_verifications_updated_by", "mtc_verifications", ["updated_by"], unique=False)
    op.create_index("ix_mtc_verifications_is_deleted", "mtc_verifications", ["is_deleted"], unique=False)

    op.create_table(
        "batch_inventories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_number", sa.String(length=100), nullable=False),
        sa.Column("item_code", sa.String(length=80), nullable=False),
        sa.Column("current_quantity", sa.Numeric(18, 3), nullable=False, server_default="0.000"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["batch_number"], ["grn_items.batch_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("batch_number", name="uq_batch_inventories_batch_number"),
        sa.CheckConstraint("current_quantity >= 0", name="ck_batch_inventories_current_qty_gte_zero"),
    )
    op.create_index("ix_batch_inventories_batch_number", "batch_inventories", ["batch_number"], unique=False)
    op.create_index("ix_batch_inventories_item_code", "batch_inventories", ["item_code"], unique=False)
    op.create_index("ix_batch_inventories_created_by", "batch_inventories", ["created_by"], unique=False)
    op.create_index("ix_batch_inventories_updated_by", "batch_inventories", ["updated_by"], unique=False)
    op.create_index("ix_batch_inventories_is_deleted", "batch_inventories", ["is_deleted"], unique=False)

    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_number", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", stock_txn_type, nullable=False),
        sa.Column("reference_number", sa.String(length=80), nullable=False),
        sa.Column("quantity_in", sa.Numeric(18, 3), nullable=False, server_default="0.000"),
        sa.Column("quantity_out", sa.Numeric(18, 3), nullable=False, server_default="0.000"),
        sa.Column("balance_after", sa.Numeric(18, 3), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["batch_number"], ["batch_inventories.batch_number"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.CheckConstraint("quantity_in >= 0", name="ck_stock_ledger_qty_in_gte_zero"),
        sa.CheckConstraint("quantity_out >= 0", name="ck_stock_ledger_qty_out_gte_zero"),
        sa.CheckConstraint("balance_after >= 0", name="ck_stock_ledger_balance_after_gte_zero"),
        sa.CheckConstraint(
            "(transaction_type = 'GRN' AND quantity_in > 0 AND quantity_out = 0) OR "
            "(transaction_type = 'ISSUE' AND quantity_out > 0 AND quantity_in = 0)",
            name="ck_stock_ledger_direction_by_txn_type",
        ),
    )
    op.create_index("ix_stock_ledger_batch_number", "stock_ledger", ["batch_number"], unique=False)
    op.create_index("ix_stock_ledger_transaction_type", "stock_ledger", ["transaction_type"], unique=False)
    op.create_index("ix_stock_ledger_reference_number", "stock_ledger", ["reference_number"], unique=False)
    op.create_index("ix_stock_ledger_transaction_date", "stock_ledger", ["transaction_date"], unique=False)
    op.create_index("ix_stock_ledger_created_by", "stock_ledger", ["created_by"], unique=False)
    op.create_index("ix_stock_ledger_updated_by", "stock_ledger", ["updated_by"], unique=False)
    op.create_index("ix_stock_ledger_is_deleted", "stock_ledger", ["is_deleted"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stock_ledger_is_deleted", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_updated_by", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_created_by", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_transaction_date", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_reference_number", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_transaction_type", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_batch_number", table_name="stock_ledger")
    op.drop_table("stock_ledger")

    op.drop_index("ix_batch_inventories_is_deleted", table_name="batch_inventories")
    op.drop_index("ix_batch_inventories_updated_by", table_name="batch_inventories")
    op.drop_index("ix_batch_inventories_created_by", table_name="batch_inventories")
    op.drop_index("ix_batch_inventories_item_code", table_name="batch_inventories")
    op.drop_index("ix_batch_inventories_batch_number", table_name="batch_inventories")
    op.drop_table("batch_inventories")

    op.drop_index("ix_mtc_verifications_is_deleted", table_name="mtc_verifications")
    op.drop_index("ix_mtc_verifications_updated_by", table_name="mtc_verifications")
    op.drop_index("ix_mtc_verifications_created_by", table_name="mtc_verifications")
    op.drop_index("ix_mtc_verifications_verified_by", table_name="mtc_verifications")
    op.drop_index("ix_mtc_verifications_mtc_number", table_name="mtc_verifications")
    op.drop_index("ix_mtc_verifications_grn_item_id", table_name="mtc_verifications")
    op.drop_table("mtc_verifications")

    op.drop_index("ix_rmir_reports_is_deleted", table_name="rmir_reports")
    op.drop_index("ix_rmir_reports_updated_by", table_name="rmir_reports")
    op.drop_index("ix_rmir_reports_created_by", table_name="rmir_reports")
    op.drop_index("ix_rmir_reports_inspection_status", table_name="rmir_reports")
    op.drop_index("ix_rmir_reports_inspected_by", table_name="rmir_reports")
    op.drop_index("ix_rmir_reports_grn_item_id", table_name="rmir_reports")
    op.drop_table("rmir_reports")

    op.drop_index("ix_grn_items_is_deleted", table_name="grn_items")
    op.drop_index("ix_grn_items_updated_by", table_name="grn_items")
    op.drop_index("ix_grn_items_created_by", table_name="grn_items")
    op.drop_index("ix_grn_items_batch_number", table_name="grn_items")
    op.drop_index("ix_grn_items_item_code", table_name="grn_items")
    op.drop_index("ix_grn_items_grn_id", table_name="grn_items")
    op.drop_table("grn_items")

    op.drop_index("ix_grns_is_deleted", table_name="grns")
    op.drop_index("ix_grns_updated_by", table_name="grns")
    op.drop_index("ix_grns_created_by", table_name="grns")
    op.drop_index("ix_grns_status", table_name="grns")
    op.drop_index("ix_grns_supplier_id", table_name="grns")
    op.drop_index("ix_grns_purchase_order_id", table_name="grns")
    op.drop_index("ix_grns_grn_number", table_name="grns")
    op.drop_table("grns")

    op.execute("DROP TYPE IF EXISTS stock_transaction_type")
    op.execute("DROP TYPE IF EXISTS rmir_inspection_status")
    op.execute("DROP TYPE IF EXISTS grn_status")
