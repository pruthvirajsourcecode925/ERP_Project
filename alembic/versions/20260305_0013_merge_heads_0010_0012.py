"""merge heads 0010 and 0012

Revision ID: 20260305_0013
Revises: 20260304_0010, 20260305_0012
Create Date: 2026-03-05 00:00:00
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20260305_0013"
down_revision: Union[str, Sequence[str], None] = ("20260304_0010", "20260305_0012")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
