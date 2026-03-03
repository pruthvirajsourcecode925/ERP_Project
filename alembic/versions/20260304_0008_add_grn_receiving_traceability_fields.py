"""add grn receiving traceability fields

Revision ID: 20260304_0008
Revises: 20260304_0007
Create Date: 2026-03-04 11:20:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260304_0008"
down_revision: Union[str, None] = "20260304_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE grns ADD COLUMN IF NOT EXISTS received_by INTEGER;")
    op.execute("ALTER TABLE grns ADD COLUMN IF NOT EXISTS received_datetime TIMESTAMPTZ;")

    op.execute(
        """
        UPDATE grns
        SET received_by = COALESCE(received_by, created_by)
        WHERE received_by IS NULL;
        """
    )
    op.execute(
        """
        UPDATE grns
        SET received_datetime = COALESCE(received_datetime, created_at, now())
        WHERE received_datetime IS NULL;
        """
    )

    op.execute("ALTER TABLE grns ALTER COLUMN received_by SET NOT NULL;")
    op.execute("ALTER TABLE grns ALTER COLUMN received_datetime SET NOT NULL;")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_grns_received_by_users'
            ) THEN
                ALTER TABLE grns
                ADD CONSTRAINT fk_grns_received_by_users
                FOREIGN KEY (received_by) REFERENCES users(id);
            END IF;
        END
        $$;
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_grns_received_by ON grns (received_by);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_grns_received_datetime ON grns (received_datetime);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_grns_received_datetime;")
    op.execute("DROP INDEX IF EXISTS ix_grns_received_by;")
    op.execute("ALTER TABLE grns DROP CONSTRAINT IF EXISTS fk_grns_received_by_users;")
    op.execute("ALTER TABLE grns DROP COLUMN IF EXISTS received_datetime;")
    op.execute("ALTER TABLE grns DROP COLUMN IF EXISTS received_by;")
