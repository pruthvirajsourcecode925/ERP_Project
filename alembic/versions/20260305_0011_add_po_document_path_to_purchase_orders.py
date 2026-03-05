"""add po document path to purchase orders

Revision ID: 20260305_0011
Revises: 20260303_0005
Create Date: 2026-03-05 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260305_0011"
down_revision: Union[str, None] = "20260303_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("po_document_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_orders", "po_document_path")
