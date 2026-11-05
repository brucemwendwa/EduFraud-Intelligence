"""student invitation activation records

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_invitations",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("activated_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["activated_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_student_invitations_student_id"), "student_invitations", ["student_id"], unique=False)
    op.create_index(op.f("ix_student_invitations_organization_id"), "student_invitations", ["organization_id"], unique=False)
    op.create_index(op.f("ix_student_invitations_token_hash"), "student_invitations", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_student_invitations_token_hash"), table_name="student_invitations")
    op.drop_index(op.f("ix_student_invitations_organization_id"), table_name="student_invitations")
    op.drop_index(op.f("ix_student_invitations_student_id"), table_name="student_invitations")
    op.drop_table("student_invitations")
