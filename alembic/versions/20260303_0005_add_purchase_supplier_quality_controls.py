"""add purchase supplier quality controls

Revision ID: 20260303_0005
Revises: 20260302_0004
Create Date: 2026-03-03 18:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260303_0005"
down_revision: Union[str, None] = "20260302_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("suppliers", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("approval_remarks", sa.Text(), nullable=True))
    op.add_column(
        "suppliers",
        sa.Column("quality_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("suppliers", sa.Column("last_evaluation_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("suppliers", sa.Column("evaluation_score", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("evaluation_remarks", sa.Text(), nullable=True))

    op.create_index("ix_suppliers_approved_by", "suppliers", ["approved_by"], unique=False)
    op.create_foreign_key(
        "fk_suppliers_approved_by_users",
        "suppliers",
        "users",
        ["approved_by"],
        ["id"],
    )

    op.add_column("purchase_orders", sa.Column("quality_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_orders", "quality_notes")

    op.drop_constraint("fk_suppliers_approved_by_users", "suppliers", type_="foreignkey")
    op.drop_index("ix_suppliers_approved_by", table_name="suppliers")

    op.drop_column("suppliers", "evaluation_remarks")
    op.drop_column("suppliers", "evaluation_score")
    op.drop_column("suppliers", "last_evaluation_date")
    op.drop_column("suppliers", "quality_acknowledged")
    op.drop_column("suppliers", "approval_remarks")
    op.drop_column("suppliers", "approved_by")
    op.drop_column("suppliers", "approval_date")
