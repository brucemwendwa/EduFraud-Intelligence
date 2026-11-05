"""student application drafts and lifecycle history

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("financial_aid_applications") as batch_op:
        batch_op.alter_column("award_year", existing_type=sa.String(9), nullable=True)
        batch_op.alter_column("submitted_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.alter_column("dependency_status", existing_type=sa.String(16), nullable=True)
        batch_op.alter_column("enrollment_intensity", existing_type=sa.String(24), nullable=True)
        batch_op.alter_column("program", existing_type=sa.String(120), nullable=True)
        batch_op.alter_column("requested_amount", existing_type=sa.Numeric(12, 2), nullable=True)
        batch_op.alter_column("student_aid_index", existing_type=sa.Integer(), nullable=True)
    op.create_table(
        "application_status_history",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(40), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["application_id"], ["financial_aid_applications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_status_history_application", "application_status_history", ["application_id", "created_at"])
    op.create_index("ix_application_status_history_organization_id", "application_status_history", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_application_status_history_organization_id", table_name="application_status_history")
    op.drop_index("ix_application_status_history_application", table_name="application_status_history")
    op.drop_table("application_status_history")
    with op.batch_alter_table("financial_aid_applications") as batch_op:
        batch_op.alter_column("student_aid_index", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("requested_amount", existing_type=sa.Numeric(12, 2), nullable=False)
        batch_op.alter_column("program", existing_type=sa.String(120), nullable=False)
        batch_op.alter_column("enrollment_intensity", existing_type=sa.String(24), nullable=False)
        batch_op.alter_column("dependency_status", existing_type=sa.String(16), nullable=False)
        batch_op.alter_column("submitted_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("award_year", existing_type=sa.String(9), nullable=False)
