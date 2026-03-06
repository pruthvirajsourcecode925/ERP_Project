"""add oauth_states table

Revision ID: 20260301_0002
Revises: 20260301_0001
Create Date: 2026-03-01 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_0002"
down_revision: Union[str, None] = "20260301_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "oauth_states" not in table_names:
        op.create_table(
            "oauth_states",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=30), nullable=False),
            sa.Column("state", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("oauth_states")}
    if "ix_oauth_states_id" not in existing_indexes:
        op.create_index(op.f("ix_oauth_states_id"), "oauth_states", ["id"], unique=False)
    if "ix_oauth_states_provider" not in existing_indexes:
        op.create_index(op.f("ix_oauth_states_provider"), "oauth_states", ["provider"], unique=False)
    if "ix_oauth_states_state" not in existing_indexes:
        op.create_index(op.f("ix_oauth_states_state"), "oauth_states", ["state"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "oauth_states" not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("oauth_states")}
    if "ix_oauth_states_state" in existing_indexes:
        op.drop_index(op.f("ix_oauth_states_state"), table_name="oauth_states")
    if "ix_oauth_states_provider" in existing_indexes:
        op.drop_index(op.f("ix_oauth_states_provider"), table_name="oauth_states")
    if "ix_oauth_states_id" in existing_indexes:
        op.drop_index(op.f("ix_oauth_states_id"), table_name="oauth_states")

    op.drop_table("oauth_states")
