"""case decisions and finding level

Adds an append-only record of every consequential human decision on an investigation case
(who, when, what, why) and a finding level that keeps suspicion and findings distinct.

Revision ID: 0003
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investigation_cases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("finding", sa.String(length=24), nullable=False, server_default="suspicious_activity")
        )

    op.create_table(
        "case_decisions",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("finding", sa.String(length=24), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["investigation_cases.id"], name=op.f("fk_case_decisions_case_id_investigation_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_case_decisions_decided_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_case_decisions_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_decisions")),
    )
    with op.batch_alter_table("case_decisions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_case_decisions_case_id"), ["case_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_case_decisions_organization_id"), ["organization_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("case_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_case_decisions_organization_id"))
        batch_op.drop_index(batch_op.f("ix_case_decisions_case_id"))
    op.drop_table("case_decisions")
    with op.batch_alter_table("investigation_cases", schema=None) as batch_op:
        batch_op.drop_column("finding")
