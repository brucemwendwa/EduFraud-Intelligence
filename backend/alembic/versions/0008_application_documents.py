"""private application document metadata

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_documents",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(160), nullable=False),
        sa.Column("object_key", sa.String(256), nullable=False),
        sa.Column("detected_mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(1000), nullable=True),
        sa.Column("replaces_document_id", sa.Uuid(), nullable=True),
        sa.Column("scanner_provider", sa.String(40), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_attempts", sa.Integer(), nullable=False),
        sa.Column("scan_token", sa.String(64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["financial_aid_applications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replaces_document_id"], ["application_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("scan_token"),
    )
    op.create_index("ix_application_documents_application", "application_documents", ["application_id", "created_at"])
    op.create_index("ix_application_documents_organization_id", "application_documents", ["organization_id"])
    op.create_index("ix_application_documents_sha256", "application_documents", ["sha256"])
    op.create_index("ix_application_documents_status", "application_documents", ["status"])
    op.create_index("ix_application_documents_review_status", "application_documents", ["review_status"])
    op.create_table(
        "document_scan_jobs",
        sa.Column("document_id", sa.Uuid(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)), sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False), sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["application_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("document_id"),
    )
    op.create_index("ix_document_scan_jobs_status_retry", "document_scan_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("document_scan_jobs")
    op.drop_table("application_documents")
