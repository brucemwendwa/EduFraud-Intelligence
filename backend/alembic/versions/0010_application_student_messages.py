"""Separate student-visible explanations from staff-only notes and widen status columns.

SQLite does not enforce VARCHAR lengths, so these undersized columns only fail on PostgreSQL.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_status_history", sa.Column("student_message", sa.String(1000), nullable=True))
    # Tenant filters on these tables were missing the index that every other tenant-scoped table has.
    op.create_index("ix_document_scan_jobs_organization_id", "document_scan_jobs", ["organization_id"])
    op.create_index("ix_document_object_cleanups_organization_id", "document_object_cleanups", ["organization_id"])
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite does not enforce the lengths, and rebuilding these tables would drop their data guards.
    # "additional_information_required" is 31 characters.
    op.alter_column("financial_aid_applications", "status", existing_type=sa.String(20), type_=sa.String(40))
    # "awaiting_verification" is 21 characters.
    op.alter_column("investigation_cases", "status", existing_type=sa.String(16), type_=sa.String(24))
    op.alter_column("case_decisions", "from_status", existing_type=sa.String(16), type_=sa.String(24))
    op.alter_column("case_decisions", "to_status", existing_type=sa.String(16), type_=sa.String(24))


def downgrade() -> None:
    # Column widths are left as they are: narrowing could fail on, or truncate, existing status values.
    op.drop_index("ix_document_object_cleanups_organization_id", table_name="document_object_cleanups")
    op.drop_index("ix_document_scan_jobs_organization_id", table_name="document_scan_jobs")
    with op.batch_alter_table("application_status_history") as batch_op:
        batch_op.drop_column("student_message")
