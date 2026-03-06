"""add batch traceability check constraint

Revision ID: 20260304_0009
Revises: 20260304_0008
Create Date: 2026-03-04 12:10:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260304_0009"
down_revision: Union[str, None] = "20260304_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_grn_items_batch_traceability_format'
            ) THEN
                ALTER TABLE grn_items
                ADD CONSTRAINT ck_grn_items_batch_traceability_format
                CHECK (
                    batch_number ~
                    '^DRW-[^/[:space:]]+[[:space:]]*/[[:space:]]*SO-[^/[:space:]]+[[:space:]]*/[[:space:]]*CUST-[^/[:space:]]+[[:space:]]*/[[:space:]]*HEAT-[^/[:space:]]+$'
                ) NOT VALID;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grn_items DROP CONSTRAINT IF EXISTS ck_grn_items_batch_traceability_format;")
