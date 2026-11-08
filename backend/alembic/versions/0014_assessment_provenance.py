"""Record how each risk assessment was produced.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import JSONType

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("risk_assessments", sa.Column("provenance", JSONType, nullable=True))
    op.add_column("risk_assessments", sa.Column("input_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("risk_assessments") as batch_op:
        batch_op.drop_column("input_fingerprint")
        batch_op.drop_column("provenance")
