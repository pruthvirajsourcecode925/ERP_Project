"""add sales document control fields

Revision ID: 20260301_0003
Revises: 20260301_0002
Create Date: 2026-03-01 16:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0003"
down_revision: Union[str, None] = "20260301_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _add_doc_columns(table_name: str, prefix: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return

    cols = _column_names(inspector, table_name)

    if "document_number" not in cols:
        op.add_column(table_name, sa.Column("document_number", sa.String(length=30), nullable=True))
    if "revision" not in cols:
        op.add_column(table_name, sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    if "generated_at" not in cols:
        op.add_column(table_name, sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    if "generated_by" not in cols:
        op.add_column(table_name, sa.Column("generated_by", sa.Integer(), nullable=True))

    bind.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET document_number = COALESCE(document_number, :prefix || '-' || EXTRACT(YEAR FROM NOW())::text || '-' || LPAD(id::text, 4, '0')),
                generated_at = COALESCE(generated_at, NOW())
            """
        ),
        {"prefix": prefix},
    )

    op.alter_column(table_name, "document_number", nullable=False)
    op.alter_column(table_name, "generated_at", nullable=False)

    try:
        op.create_foreign_key(
            f"fk_{table_name}_generated_by_users",
            table_name,
            "users",
            ["generated_by"],
            ["id"],
        )
    except Exception:
        pass

    inspector = sa.inspect(bind)
    existing_indexes = _index_names(inspector, table_name)

    doc_index_name = f"ix_{table_name}_document_number"
    if doc_index_name not in existing_indexes:
        op.create_index(doc_index_name, table_name, ["document_number"], unique=True)

    gen_index_name = f"ix_{table_name}_generated_at"
    if gen_index_name not in existing_indexes:
        op.create_index(gen_index_name, table_name, ["generated_at"], unique=False)

    gen_by_index_name = f"ix_{table_name}_generated_by"
    if gen_by_index_name not in existing_indexes:
        op.create_index(gen_by_index_name, table_name, ["generated_by"], unique=False)


def upgrade() -> None:
    _add_doc_columns("contract_reviews", "CR")
    _add_doc_columns("quotations", "QT")
    _add_doc_columns("customer_po_reviews", "POA")


def _drop_doc_columns(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return

    existing_indexes = _index_names(inspector, table_name)
    for index_name in [
        f"ix_{table_name}_generated_by",
        f"ix_{table_name}_generated_at",
        f"ix_{table_name}_document_number",
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)

    try:
        op.drop_constraint(f"fk_{table_name}_generated_by_users", table_name=table_name, type_="foreignkey")
    except Exception:
        pass

    cols = _column_names(inspector, table_name)
    for col_name in ["generated_by", "generated_at", "revision", "document_number"]:
        if col_name in cols:
            op.drop_column(table_name, col_name)


def downgrade() -> None:
    _drop_doc_columns("customer_po_reviews")
    _drop_doc_columns("quotations")
    _drop_doc_columns("contract_reviews")
