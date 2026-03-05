"""add supplier quality requirements to purchase orders

Revision ID: 20260305_0012
Revises: 20260305_0011
Create Date: 2026-03-05 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260305_0012"
down_revision: Union[str, None] = "20260305_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column("supplier_quality_requirements", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "supplier_quality_requirements")
