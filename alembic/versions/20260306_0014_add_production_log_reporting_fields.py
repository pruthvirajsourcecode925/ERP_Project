"""add production log reporting fields

Revision ID: 20260306_0014
Revises: 20260305_0013
Create Date: 2026-03-06 22:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260306_0014"
down_revision: Union[str, None] = "20260305_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("production_logs", sa.Column("batch_number", sa.String(length=100), nullable=True))
    op.add_column("production_logs", sa.Column("operator_user_id", sa.Integer(), nullable=True))
    op.add_column("production_logs", sa.Column("machine_id", sa.BigInteger(), nullable=True))
    op.add_column("production_logs", sa.Column("scrap_reason", sa.String(length=255), nullable=True))
    op.add_column("production_logs", sa.Column("shift", sa.String(length=50), nullable=True))

    op.create_foreign_key(
        "fk_production_logs_operator_user_id_users",
        "production_logs",
        "users",
        ["operator_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_production_logs_machine_id_machines",
        "production_logs",
        "machines",
        ["machine_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE production_logs
        SET batch_number = 'LEGACY-' || id::text
        WHERE batch_number IS NULL;
        """
    )
    op.alter_column("production_logs", "batch_number", nullable=False)

    op.execute("CREATE INDEX IF NOT EXISTS ix_production_logs_batch_number ON production_logs (batch_number);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_production_logs_operator_user_id ON production_logs (operator_user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_production_logs_machine_id ON production_logs (machine_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_production_logs_machine_id;")
    op.execute("DROP INDEX IF EXISTS ix_production_logs_operator_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_production_logs_batch_number;")

    op.drop_constraint("fk_production_logs_machine_id_machines", "production_logs", type_="foreignkey")
    op.drop_constraint("fk_production_logs_operator_user_id_users", "production_logs", type_="foreignkey")

    op.drop_column("production_logs", "shift")
    op.drop_column("production_logs", "scrap_reason")
    op.drop_column("production_logs", "machine_id")
    op.drop_column("production_logs", "operator_user_id")
    op.drop_column("production_logs", "batch_number")
