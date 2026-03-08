"""add alert settings table

Revision ID: 20260308_0017
Revises: 20260308_0016
Create Date: 2026-03-08 19:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260308_0017"
down_revision: Union[str, Sequence[str], None] = "20260308_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_alert_settings_singleton_id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_settings_created_by"), "alert_settings", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_settings_created_by"), table_name="alert_settings")
    op.drop_table("alert_settings")