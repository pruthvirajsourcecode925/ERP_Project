"""add quotation terms settings

Revision ID: 20260302_0004
Revises: 20260301_0003
Create Date: 2026-03-02 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260302_0004"
down_revision: Union[str, None] = "20260301_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quotation_terms_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("terms_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_quotation_terms_settings_is_deleted", "quotation_terms_settings", ["is_deleted"], unique=False)
    op.create_index("ix_quotation_terms_settings_created_by", "quotation_terms_settings", ["created_by"], unique=False)
    op.create_index("ix_quotation_terms_settings_updated_by", "quotation_terms_settings", ["updated_by"], unique=False)
    op.create_foreign_key(
        "fk_quotation_terms_settings_created_by_users",
        "quotation_terms_settings",
        "users",
        ["created_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quotation_terms_settings_updated_by_users",
        "quotation_terms_settings",
        "users",
        ["updated_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_quotation_terms_settings_updated_by_users", "quotation_terms_settings", type_="foreignkey")
    op.drop_constraint("fk_quotation_terms_settings_created_by_users", "quotation_terms_settings", type_="foreignkey")
    op.drop_index("ix_quotation_terms_settings_updated_by", table_name="quotation_terms_settings")
    op.drop_index("ix_quotation_terms_settings_created_by", table_name="quotation_terms_settings")
    op.drop_index("ix_quotation_terms_settings_is_deleted", table_name="quotation_terms_settings")
    op.drop_table("quotation_terms_settings")
