"""add route card document fields

Revision ID: 20260304_0010
Revises: 20260304_0009
Create Date: 2026-03-04 23:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260304_0010"
down_revision: Union[str, None] = "20260304_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("route_cards", sa.Column("route_card_file_name", sa.String(length=255), nullable=True))
    op.add_column("route_cards", sa.Column("route_card_file_path", sa.Text(), nullable=True))
    op.add_column("route_cards", sa.Column("route_card_file_uploaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("route_cards", sa.Column("route_card_file_content_type", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("route_cards", "route_card_file_content_type")
    op.drop_column("route_cards", "route_card_file_uploaded_at")
    op.drop_column("route_cards", "route_card_file_path")
    op.drop_column("route_cards", "route_card_file_name")
