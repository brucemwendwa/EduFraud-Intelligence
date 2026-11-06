"""Bind document metadata to storage identity and retain cleanup intents.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_documents", sa.Column("object_version_id", sa.String(128), nullable=True))
    op.create_index(
        "uq_active_document_replacement",
        "application_documents",
        ["replaces_document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_scan', 'scanning')"),
        sqlite_where=sa.text("status IN ('pending_scan', 'scanning')"),
    )
    op.create_table(
        "document_object_cleanups",
        sa.Column("object_key", sa.String(256), nullable=False),
        sa.Column("object_version_id", sa.String(128), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_document_cleanup_status_retry", "document_object_cleanups", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("document_object_cleanups")
    op.drop_index("uq_active_document_replacement", table_name="application_documents")
    op.drop_column("application_documents", "object_version_id")
