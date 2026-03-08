"""add dispatch module tables

Revision ID: 20260308_0016
Revises: 20260308_0015
Create Date: 2026-03-08 16:50:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260308_0016"
down_revision: Union[str, Sequence[str], None] = "20260308_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dispatch_order_status = postgresql.ENUM(
        "draft",
        "reviewed",
        "released",
        "hold",
        "cancelled",
        name="dispatch_order_status",
        create_type=False,
    )
    dispatch_checklist_status = postgresql.ENUM(
        "pending",
        "completed",
        "failed",
        "waived",
        name="dispatch_checklist_status",
        create_type=False,
    )
    dispatch_invoice_status = postgresql.ENUM(
        "draft",
        "issued",
        "cancelled",
        "paid",
        name="dispatch_invoice_status",
        create_type=False,
    )
    delivery_challan_status = postgresql.ENUM(
        "issued",
        "in_transit",
        "delivered",
        "cancelled",
        name="delivery_challan_status",
        create_type=False,
    )
    shipment_tracking_status = postgresql.ENUM(
        "booked",
        "in_transit",
        "delivered",
        "exception",
        name="shipment_tracking_status",
        create_type=False,
    )

    bind = op.get_bind()
    dispatch_order_status.create(bind, checkfirst=True)
    dispatch_checklist_status.create(bind, checkfirst=True)
    dispatch_invoice_status.create(bind, checkfirst=True)
    delivery_challan_status.create(bind, checkfirst=True)
    shipment_tracking_status.create(bind, checkfirst=True)

    op.create_table(
        "dispatch_orders",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_number", sa.String(length=30), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("certificate_of_conformance_id", sa.BigInteger(), nullable=True),
        sa.Column("dispatch_date", sa.Date(), nullable=False),
        sa.Column("status", dispatch_order_status, nullable=False),
        sa.Column("released_by", sa.Integer(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_method", sa.String(length=100), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["certificate_of_conformance_id"], ["certificates_of_conformance.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_orders_id"), "dispatch_orders", ["id"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_dispatch_number"), "dispatch_orders", ["dispatch_number"], unique=True)
    op.create_index(op.f("ix_dispatch_orders_sales_order_id"), "dispatch_orders", ["sales_order_id"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_certificate_of_conformance_id"), "dispatch_orders", ["certificate_of_conformance_id"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_dispatch_date"), "dispatch_orders", ["dispatch_date"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_status"), "dispatch_orders", ["status"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_released_by"), "dispatch_orders", ["released_by"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_created_by"), "dispatch_orders", ["created_by"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_updated_by"), "dispatch_orders", ["updated_by"], unique=False)
    op.create_index(op.f("ix_dispatch_orders_is_deleted"), "dispatch_orders", ["is_deleted"], unique=False)

    op.create_table(
        "dispatch_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("production_order_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("lot_number", sa.String(length=100), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("is_traceability_verified", sa.Boolean(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint("line_number > 0", name="ck_dispatch_items_line_number_gt_zero"),
        sa.CheckConstraint("quantity > 0", name="ck_dispatch_items_quantity_gt_zero"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["production_order_id"], ["production_orders.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_items_id"), "dispatch_items", ["id"], unique=False)
    op.create_index(op.f("ix_dispatch_items_dispatch_order_id"), "dispatch_items", ["dispatch_order_id"], unique=False)
    op.create_index(op.f("ix_dispatch_items_production_order_id"), "dispatch_items", ["production_order_id"], unique=False)
    op.create_index(op.f("ix_dispatch_items_item_code"), "dispatch_items", ["item_code"], unique=False)
    op.create_index(op.f("ix_dispatch_items_lot_number"), "dispatch_items", ["lot_number"], unique=False)
    op.create_index(op.f("ix_dispatch_items_serial_number"), "dispatch_items", ["serial_number"], unique=False)
    op.create_index(op.f("ix_dispatch_items_created_by"), "dispatch_items", ["created_by"], unique=False)
    op.create_index(op.f("ix_dispatch_items_updated_by"), "dispatch_items", ["updated_by"], unique=False)
    op.create_index(op.f("ix_dispatch_items_is_deleted"), "dispatch_items", ["is_deleted"], unique=False)
    op.create_index("uq_dispatch_items_order_line", "dispatch_items", ["dispatch_order_id", "line_number"], unique=True)

    op.create_table(
        "dispatch_checklists",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("checklist_item", sa.String(length=255), nullable=False),
        sa.Column("requirement_reference", sa.String(length=100), nullable=True),
        sa.Column("status", dispatch_checklist_status, nullable=False),
        sa.Column("checked_by", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["checked_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_checklists_id"), "dispatch_checklists", ["id"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_dispatch_order_id"), "dispatch_checklists", ["dispatch_order_id"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_status"), "dispatch_checklists", ["status"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_checked_by"), "dispatch_checklists", ["checked_by"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_created_by"), "dispatch_checklists", ["created_by"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_updated_by"), "dispatch_checklists", ["updated_by"], unique=False)
    op.create_index(op.f("ix_dispatch_checklists_is_deleted"), "dispatch_checklists", ["is_deleted"], unique=False)

    op.create_table(
        "packing_lists",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("packing_list_number", sa.String(length=30), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("packed_date", sa.Date(), nullable=False),
        sa.Column("package_count", sa.Integer(), nullable=False),
        sa.Column("gross_weight", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("net_weight", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("dimensions", sa.String(length=255), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint("package_count >= 0", name="ck_packing_lists_package_count_gte_zero"),
        sa.CheckConstraint("gross_weight IS NULL OR gross_weight >= 0", name="ck_packing_lists_gross_weight_gte_zero"),
        sa.CheckConstraint("net_weight IS NULL OR net_weight >= 0", name="ck_packing_lists_net_weight_gte_zero"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_order_id"),
    )
    op.create_index(op.f("ix_packing_lists_id"), "packing_lists", ["id"], unique=False)
    op.create_index(op.f("ix_packing_lists_packing_list_number"), "packing_lists", ["packing_list_number"], unique=True)
    op.create_index(op.f("ix_packing_lists_dispatch_order_id"), "packing_lists", ["dispatch_order_id"], unique=True)
    op.create_index(op.f("ix_packing_lists_packed_date"), "packing_lists", ["packed_date"], unique=False)
    op.create_index(op.f("ix_packing_lists_created_by"), "packing_lists", ["created_by"], unique=False)
    op.create_index(op.f("ix_packing_lists_updated_by"), "packing_lists", ["updated_by"], unique=False)
    op.create_index(op.f("ix_packing_lists_is_deleted"), "packing_lists", ["is_deleted"], unique=False)

    op.create_table(
        "dispatch_invoices",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_number", sa.String(length=30), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status", dispatch_invoice_status, nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint("subtotal >= 0", name="ck_dispatch_invoices_subtotal_gte_zero"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_dispatch_invoices_tax_amount_gte_zero"),
        sa.CheckConstraint("total_amount >= 0", name="ck_dispatch_invoices_total_amount_gte_zero"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_order_id"),
    )
    op.create_index(op.f("ix_dispatch_invoices_id"), "dispatch_invoices", ["id"], unique=False)
    op.create_index(op.f("ix_dispatch_invoices_invoice_number"), "dispatch_invoices", ["invoice_number"], unique=True)
    op.create_index(op.f("ix_dispatch_invoices_dispatch_order_id"), "dispatch_invoices", ["dispatch_order_id"], unique=True)
    op.create_index(op.f("ix_dispatch_invoices_invoice_date"), "dispatch_invoices", ["invoice_date"], unique=False)
    op.create_index(op.f("ix_dispatch_invoices_status"), "dispatch_invoices", ["status"], unique=False)
    op.create_index(op.f("ix_dispatch_invoices_created_by"), "dispatch_invoices", ["created_by"], unique=False)
    op.create_index(op.f("ix_dispatch_invoices_updated_by"), "dispatch_invoices", ["updated_by"], unique=False)
    op.create_index(op.f("ix_dispatch_invoices_is_deleted"), "dispatch_invoices", ["is_deleted"], unique=False)

    op.create_table(
        "delivery_challans",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("challan_number", sa.String(length=30), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("received_by", sa.String(length=150), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", delivery_challan_status, nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispatch_order_id"),
    )
    op.create_index(op.f("ix_delivery_challans_id"), "delivery_challans", ["id"], unique=False)
    op.create_index(op.f("ix_delivery_challans_challan_number"), "delivery_challans", ["challan_number"], unique=True)
    op.create_index(op.f("ix_delivery_challans_dispatch_order_id"), "delivery_challans", ["dispatch_order_id"], unique=True)
    op.create_index(op.f("ix_delivery_challans_issue_date"), "delivery_challans", ["issue_date"], unique=False)
    op.create_index(op.f("ix_delivery_challans_status"), "delivery_challans", ["status"], unique=False)
    op.create_index(op.f("ix_delivery_challans_created_by"), "delivery_challans", ["created_by"], unique=False)
    op.create_index(op.f("ix_delivery_challans_updated_by"), "delivery_challans", ["updated_by"], unique=False)
    op.create_index(op.f("ix_delivery_challans_is_deleted"), "delivery_challans", ["is_deleted"], unique=False)

    op.create_table(
        "shipment_trackings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_order_id", sa.BigInteger(), nullable=False),
        sa.Column("tracking_number", sa.String(length=120), nullable=False),
        sa.Column("carrier_name", sa.String(length=150), nullable=True),
        sa.Column("shipment_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
        sa.Column("status", shipment_tracking_status, nullable=False),
        sa.Column("proof_of_delivery_path", sa.String(length=500), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "expected_delivery_date IS NULL OR expected_delivery_date >= shipment_date",
            name="ck_shipment_trackings_expected_delivery_after_shipment",
        ),
        sa.CheckConstraint(
            "actual_delivery_date IS NULL OR actual_delivery_date >= shipment_date",
            name="ck_shipment_trackings_actual_delivery_after_shipment",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dispatch_order_id"], ["dispatch_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shipment_trackings_id"), "shipment_trackings", ["id"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_dispatch_order_id"), "shipment_trackings", ["dispatch_order_id"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_tracking_number"), "shipment_trackings", ["tracking_number"], unique=True)
    op.create_index(op.f("ix_shipment_trackings_carrier_name"), "shipment_trackings", ["carrier_name"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_shipment_date"), "shipment_trackings", ["shipment_date"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_status"), "shipment_trackings", ["status"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_created_by"), "shipment_trackings", ["created_by"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_updated_by"), "shipment_trackings", ["updated_by"], unique=False)
    op.create_index(op.f("ix_shipment_trackings_is_deleted"), "shipment_trackings", ["is_deleted"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_shipment_trackings_is_deleted"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_updated_by"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_created_by"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_status"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_shipment_date"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_carrier_name"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_tracking_number"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_dispatch_order_id"), table_name="shipment_trackings")
    op.drop_index(op.f("ix_shipment_trackings_id"), table_name="shipment_trackings")
    op.drop_table("shipment_trackings")

    op.drop_index(op.f("ix_delivery_challans_is_deleted"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_updated_by"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_created_by"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_status"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_issue_date"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_dispatch_order_id"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_challan_number"), table_name="delivery_challans")
    op.drop_index(op.f("ix_delivery_challans_id"), table_name="delivery_challans")
    op.drop_table("delivery_challans")

    op.drop_index(op.f("ix_dispatch_invoices_is_deleted"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_updated_by"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_created_by"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_status"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_invoice_date"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_dispatch_order_id"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_invoice_number"), table_name="dispatch_invoices")
    op.drop_index(op.f("ix_dispatch_invoices_id"), table_name="dispatch_invoices")
    op.drop_table("dispatch_invoices")

    op.drop_index(op.f("ix_packing_lists_is_deleted"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_updated_by"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_created_by"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_packed_date"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_dispatch_order_id"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_packing_list_number"), table_name="packing_lists")
    op.drop_index(op.f("ix_packing_lists_id"), table_name="packing_lists")
    op.drop_table("packing_lists")

    op.drop_index(op.f("ix_dispatch_checklists_is_deleted"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_updated_by"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_created_by"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_checked_by"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_status"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_dispatch_order_id"), table_name="dispatch_checklists")
    op.drop_index(op.f("ix_dispatch_checklists_id"), table_name="dispatch_checklists")
    op.drop_table("dispatch_checklists")

    op.drop_index("uq_dispatch_items_order_line", table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_is_deleted"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_updated_by"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_created_by"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_serial_number"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_lot_number"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_item_code"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_production_order_id"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_dispatch_order_id"), table_name="dispatch_items")
    op.drop_index(op.f("ix_dispatch_items_id"), table_name="dispatch_items")
    op.drop_table("dispatch_items")

    op.drop_index(op.f("ix_dispatch_orders_is_deleted"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_updated_by"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_created_by"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_released_by"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_status"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_dispatch_date"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_certificate_of_conformance_id"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_sales_order_id"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_dispatch_number"), table_name="dispatch_orders")
    op.drop_index(op.f("ix_dispatch_orders_id"), table_name="dispatch_orders")
    op.drop_table("dispatch_orders")

    op.execute("DROP TYPE IF EXISTS shipment_tracking_status")
    op.execute("DROP TYPE IF EXISTS delivery_challan_status")
    op.execute("DROP TYPE IF EXISTS dispatch_invoice_status")
    op.execute("DROP TYPE IF EXISTS dispatch_checklist_status")
    op.execute("DROP TYPE IF EXISTS dispatch_order_status")