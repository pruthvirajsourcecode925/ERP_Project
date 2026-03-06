"""add storage locations and location links

Revision ID: 20260304_0007
Revises: 20260303_0006
Create Date: 2026-03-04 10:30:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260304_0007"
down_revision: Union[str, None] = "20260303_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_locations (
            id BIGSERIAL PRIMARY KEY,
            location_code VARCHAR(40) NOT NULL UNIQUE,
            location_name VARCHAR(120) NOT NULL,
            description TEXT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by INTEGER NULL REFERENCES users(id),
            updated_by INTEGER NULL REFERENCES users(id),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_storage_locations_location_code ON storage_locations (location_code);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_storage_locations_created_by ON storage_locations (created_by);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_storage_locations_updated_by ON storage_locations (updated_by);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_storage_locations_is_deleted ON storage_locations (is_deleted);")

    op.execute(
        """
        INSERT INTO storage_locations (location_code, location_name, description, is_active, is_deleted)
        SELECT 'DEFAULT', 'Default Location', 'Auto-created default storage location', TRUE, FALSE
        WHERE NOT EXISTS (
            SELECT 1 FROM storage_locations WHERE location_code = 'DEFAULT'
        );
        """
    )

    op.execute("ALTER TABLE batch_inventories ADD COLUMN IF NOT EXISTS storage_location_id BIGINT;")
    op.execute("ALTER TABLE stock_ledger ADD COLUMN IF NOT EXISTS storage_location_id BIGINT;")

    op.execute(
        """
        UPDATE batch_inventories
        SET storage_location_id = sl.id
        FROM storage_locations sl
        WHERE sl.location_code = 'DEFAULT'
          AND batch_inventories.storage_location_id IS NULL;
        """
    )
    op.execute(
        """
        UPDATE stock_ledger
        SET storage_location_id = sl.id
        FROM storage_locations sl
        WHERE sl.location_code = 'DEFAULT'
          AND stock_ledger.storage_location_id IS NULL;
        """
    )

    op.execute("ALTER TABLE batch_inventories ALTER COLUMN storage_location_id SET NOT NULL;")
    op.execute("ALTER TABLE stock_ledger ALTER COLUMN storage_location_id SET NOT NULL;")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_batch_inventories_storage_location_id'
            ) THEN
                ALTER TABLE batch_inventories
                ADD CONSTRAINT fk_batch_inventories_storage_location_id
                FOREIGN KEY (storage_location_id) REFERENCES storage_locations(id);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_stock_ledger_storage_location_id'
            ) THEN
                ALTER TABLE stock_ledger
                ADD CONSTRAINT fk_stock_ledger_storage_location_id
                FOREIGN KEY (storage_location_id) REFERENCES storage_locations(id);
            END IF;
        END
        $$;
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_batch_inventories_storage_location_id ON batch_inventories (storage_location_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_ledger_storage_location_id ON stock_ledger (storage_location_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_storage_location_id;")
    op.execute("DROP INDEX IF EXISTS ix_batch_inventories_storage_location_id;")

    op.execute("ALTER TABLE stock_ledger DROP CONSTRAINT IF EXISTS fk_stock_ledger_storage_location_id;")
    op.execute("ALTER TABLE batch_inventories DROP CONSTRAINT IF EXISTS fk_batch_inventories_storage_location_id;")

    op.execute("ALTER TABLE stock_ledger DROP COLUMN IF EXISTS storage_location_id;")
    op.execute("ALTER TABLE batch_inventories DROP COLUMN IF EXISTS storage_location_id;")

    op.execute("DROP INDEX IF EXISTS ix_storage_locations_is_deleted;")
    op.execute("DROP INDEX IF EXISTS ix_storage_locations_updated_by;")
    op.execute("DROP INDEX IF EXISTS ix_storage_locations_created_by;")
    op.execute("DROP INDEX IF EXISTS ix_storage_locations_location_code;")
    op.execute("DROP TABLE IF EXISTS storage_locations;")
