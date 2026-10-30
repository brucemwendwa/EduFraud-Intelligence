"""initial schema

Revision ID: 0001
Revises:
Initial EduShield AI schema: tenancy, RBAC, students (tokenized), aid records,
verifications, explainable risk, alerts, cases, hash-chained audit trail.

Create Date: 2026-10-30 12:36:25.575933
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Audit events are append-only. Enforced in the database so that even code (or a person)
# with direct table access cannot rewrite history through UPDATE, DELETE or TRUNCATE.
_PG_IMMUTABLE_AUDIT = [
    """
    CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only (% blocked)', TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable()
    """,
    """
    CREATE TRIGGER trg_audit_events_no_truncate BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_immutable()
    """,
]
_SQLITE_IMMUTABLE_AUDIT = [
    """
    CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only (UPDATE blocked)'); END
    """,
    """
    CREATE TRIGGER trg_audit_events_no_delete BEFORE DELETE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only (DELETE blocked)'); END
    """,
]


def _create_audit_triggers() -> None:
    dialect = op.get_bind().dialect.name
    statements = _PG_IMMUTABLE_AUDIT if dialect == "postgresql" else _SQLITE_IMMUTABLE_AUDIT
    for stmt in statements:
        op.execute(stmt)


def _drop_audit_triggers() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_truncate ON audit_events")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")


def upgrade() -> None:

    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("institution_type", sa.String(length=40), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("synthetic_ope_id", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("name", name=op.f("uq_organizations_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
        sa.UniqueConstraint("synthetic_ope_id", name=op.f("uq_organizations_synthetic_ope_id")),
    )
    op.create_table(
        "payment_destination_tokens",
        sa.Column("token_value", sa.String(length=64), nullable=False),
        sa.Column("destination_type", sa.String(length=16), nullable=False),
        sa.Column("display_suffix", sa.String(length=4), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_destination_tokens")),
        sa.UniqueConstraint("token_value", name=op.f("uq_payment_destination_tokens_token_value")),
    )
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("key", name=op.f("uq_permissions_key")),
    )
    op.create_table(
        "roles",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("is_platform_role", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("key", name=op.f("uq_roles_key")),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_role_permissions_role_id_roles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )
    op.create_table(
        "students",
        sa.Column("student_ref", sa.String(length=24), nullable=False),
        sa.Column("first_name", sa.String(length=512), nullable=False),
        sa.Column("last_name", sa.String(length=512), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=False),
        sa.Column("state_of_residence", sa.String(length=2), nullable=False),
        sa.Column("biometric_consent", sa.Boolean(), nullable=False),
        sa.Column("biometric_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("biometric_reference_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_students_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("organization_id", "student_ref", name=op.f("uq_students_organization_id")),
    )
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_students_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_users_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_users_role_id_roles"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_role_id"), ["role_id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("actor_role", sa.String(length=40), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("target_ref", sa.String(length=48), nullable=True),
        sa.Column("ip_hash", sa.String(length=16), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_events_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.UniqueConstraint("hash", name=op.f("uq_audit_events_hash")),
        sa.UniqueConstraint("sequence", name=op.f("uq_audit_events_sequence")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_events_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_actor_user_id"), ["actor_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_category"), ["category"], unique=False)
        batch_op.create_index("ix_audit_org_time", ["organization_id", "occurred_at"], unique=False)
        batch_op.create_index("ix_audit_target", ["target_type", "target_id"], unique=False)

    op.create_table(
        "detection_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("triggered_by_id", sa.Uuid(), nullable=True),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=True),
        sa.Column("applications_scored", sa.Integer(), nullable=False),
        sa.Column("disbursements_scored", sa.Integer(), nullable=False),
        sa.Column("alerts_created", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_detection_runs_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_id"],
            ["users.id"],
            name=op.f("fk_detection_runs_triggered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_runs")),
    )
    with op.batch_alter_table("detection_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_detection_runs_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "financial_aid_applications",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("award_year", sa.String(length=9), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dependency_status", sa.String(length=16), nullable=False),
        sa.Column("enrollment_intensity", sa.String(length=24), nullable=False),
        sa.Column("program", sa.String(length=120), nullable=False),
        sa.Column("requested_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("student_aid_index", sa.Integer(), nullable=False),
        sa.Column("submission_channel", sa.String(length=16), nullable=False),
        sa.Column("device_token", sa.String(length=64), nullable=True),
        sa.Column("ip_token", sa.String(length=64), nullable=True),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Double(), nullable=True),
        sa.Column("risk_level", sa.String(length=10), nullable=True),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scenario_key", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "requested_amount >= 0", name=op.f("ck_financial_aid_applications_requested_amount_non_negative")
        ),
        sa.CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name=op.f("ck_financial_aid_applications_risk_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_financial_aid_applications_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_financial_aid_applications_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_aid_applications")),
        sa.UniqueConstraint("reference", name=op.f("uq_financial_aid_applications_reference")),
    )
    with op.batch_alter_table("financial_aid_applications", schema=None) as batch_op:
        batch_op.create_index("ix_applications_org_risk", ["organization_id", "risk_score"], unique=False)
        batch_op.create_index("ix_applications_org_submitted", ["organization_id", "submitted_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_financial_aid_applications_device_token"), ["device_token"], unique=False)
        batch_op.create_index(batch_op.f("ix_financial_aid_applications_ip_token"), ["ip_token"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_financial_aid_applications_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_financial_aid_applications_risk_level"), ["risk_level"], unique=False)
        batch_op.create_index(batch_op.f("ix_financial_aid_applications_scenario_key"), ["scenario_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_financial_aid_applications_student_id"), ["student_id"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=200), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_notifications_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index("ix_notifications_user_read", ["user_id", "read_at"], unique=False)

    op.create_table(
        "student_identity_tokens",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("token_type", sa.String(length=16), nullable=False),
        sa.Column("token_value", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_student_identity_tokens_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_student_identity_tokens_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_identity_tokens")),
        sa.UniqueConstraint("student_id", "token_type", name=op.f("uq_student_identity_tokens_student_id")),
    )
    with op.batch_alter_table("student_identity_tokens", schema=None) as batch_op:
        batch_op.create_index("ix_identity_tokens_type_value", ["token_type", "token_value"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_student_identity_tokens_organization_id"), ["organization_id"], unique=False
        )

    op.create_table(
        "disbursements",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("destination_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("fund_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("disbursed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("destination_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_score", sa.Double(), nullable=True),
        sa.Column(
            "risk_flags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("hold_reason", sa.String(length=500), nullable=True),
        sa.Column("held_by_id", sa.Uuid(), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_disbursements_amount_positive")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_disbursements_application_id_financial_aid_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["payment_destination_tokens.id"],
            name=op.f("fk_disbursements_destination_id_payment_destination_tokens"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["held_by_id"], ["users.id"], name=op.f("fk_disbursements_held_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_disbursements_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_disbursements_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disbursements")),
        sa.UniqueConstraint("reference", name=op.f("uq_disbursements_reference")),
    )
    with op.batch_alter_table("disbursements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_disbursements_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_disbursements_destination_id"), ["destination_id"], unique=False)
        batch_op.create_index("ix_disbursements_org_date", ["organization_id", "disbursed_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_disbursements_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_disbursements_student_id"), ["student_id"], unique=False)

    op.create_table(
        "enrollment_records",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("term", sa.String(length=16), nullable=False),
        sa.Column("term_start", sa.Date(), nullable=False),
        sa.Column("program", sa.String(length=120), nullable=False),
        sa.Column("credit_hours", sa.Integer(), nullable=False),
        sa.Column("modality", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_attendance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.CheckConstraint("credit_hours >= 0", name=op.f("ck_enrollment_records_credit_hours_non_negative")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_enrollment_records_application_id_financial_aid_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_enrollment_records_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_enrollment_records_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment_records")),
    )
    with op.batch_alter_table("enrollment_records", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_enrollment_records_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_enrollment_records_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_enrollment_records_student_id"), ["student_id"], unique=False)

    op.create_table(
        "identity_verifications",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("provider_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("document_result", sa.String(length=24), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=True),
        sa.Column("face_match_score", sa.Double(), nullable=True),
        sa.Column("liveness_score", sa.Double(), nullable=True),
        sa.Column("liveness_result", sa.String(length=24), nullable=False),
        sa.Column("pad_result", sa.String(length=24), nullable=False),
        sa.Column("pad_attack_type", sa.String(length=32), nullable=True),
        sa.Column(
            "quality_flags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "risk_indicators",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("recommended_action", sa.String(length=300), nullable=False),
        sa.Column("sample_key", sa.String(length=48), nullable=True),
        sa.Column(
            "session_context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_identity_verifications_application_id_financial_aid_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_id"],
            ["users.id"],
            name=op.f("fk_identity_verifications_initiated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_identity_verifications_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_identity_verifications_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_verifications")),
        sa.UniqueConstraint("reference", name=op.f("uq_identity_verifications_reference")),
    )
    with op.batch_alter_table("identity_verifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_identity_verifications_application_id"), ["application_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_identity_verifications_organization_id"), ["organization_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_identity_verifications_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_identity_verifications_student_id"), ["student_id"], unique=False)

    op.create_table(
        "investigation_cases",
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("fraud_category", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("risk_score_at_open", sa.Double(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_investigation_cases_application_id_financial_aid_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_id"],
            ["users.id"],
            name=op.f("fk_investigation_cases_assigned_to_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_investigation_cases_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_investigation_cases_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_cases")),
        sa.UniqueConstraint("reference", name=op.f("uq_investigation_cases_reference")),
    )
    with op.batch_alter_table("investigation_cases", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_investigation_cases_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_investigation_cases_assigned_to_id"), ["assigned_to_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_investigation_cases_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_investigation_cases_status"), ["status"], unique=False)

    op.create_table(
        "case_evidence",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=24), nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("ref_label", sa.String(length=48), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            name=op.f("fk_case_evidence_added_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["investigation_cases.id"],
            name=op.f("fk_case_evidence_case_id_investigation_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_case_evidence_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_evidence")),
    )
    with op.batch_alter_table("case_evidence", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_case_evidence_case_id"), ["case_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_case_evidence_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "case_notes",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_case_notes_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["investigation_cases.id"],
            name=op.f("fk_case_notes_case_id_investigation_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_case_notes_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_notes")),
    )
    with op.batch_alter_table("case_notes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_case_notes_case_id"), ["case_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_case_notes_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "risk_assessments",
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("disbursement_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Double(), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(length=300), nullable=False),
        sa.Column(
            "feature_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(length=24), nullable=False),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name=op.f("ck_risk_assessments_score_range")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_risk_assessments_application_id_financial_aid_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["disbursement_id"],
            ["disbursements.id"],
            name=op.f("fk_risk_assessments_disbursement_id_disbursements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_risk_assessments_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name=op.f("fk_risk_assessments_triggered_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_assessments")),
    )
    with op.batch_alter_table("risk_assessments", schema=None) as batch_op:
        batch_op.create_index("ix_risk_assessments_app_current", ["application_id", "is_current"], unique=False)
        batch_op.create_index(batch_op.f("ix_risk_assessments_disbursement_id"), ["disbursement_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_risk_assessments_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("reference", sa.String(length=24), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("disbursement_id", sa.Uuid(), nullable=True),
        sa.Column("verification_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("risk_score", sa.Double(), nullable=True),
        sa.Column("triage_note", sa.String(length=500), nullable=True),
        sa.Column("triaged_by_id", sa.Uuid(), nullable=True),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["financial_aid_applications.id"],
            name=op.f("fk_alerts_application_id_financial_aid_applications"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["risk_assessments.id"],
            name=op.f("fk_alerts_assessment_id_risk_assessments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["investigation_cases.id"],
            name=op.f("fk_alerts_case_id_investigation_cases"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["disbursement_id"],
            ["disbursements.id"],
            name=op.f("fk_alerts_disbursement_id_disbursements"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_alerts_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triaged_by_id"], ["users.id"], name=op.f("fk_alerts_triaged_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["identity_verifications.id"],
            name=op.f("fk_alerts_verification_id_identity_verifications"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("reference", name=op.f("uq_alerts_reference")),
    )
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_alerts_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_alerts_dedupe_key"), ["dedupe_key"], unique=False)
        batch_op.create_index("ix_alerts_org_status", ["organization_id", "status"], unique=False)
        batch_op.create_index(batch_op.f("ix_alerts_organization_id"), ["organization_id"], unique=False)

    op.create_table(
        "fraud_signals",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.Column("points", sa.Double(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["risk_assessments.id"],
            name=op.f("fk_fraud_signals_assessment_id_risk_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_fraud_signals_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fraud_signals")),
    )
    with op.batch_alter_table("fraud_signals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_fraud_signals_assessment_id"), ["assessment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_fraud_signals_code"), ["code"], unique=False)
        batch_op.create_index(batch_op.f("ix_fraud_signals_organization_id"), ["organization_id"], unique=False)

    _create_audit_triggers()


def downgrade() -> None:
    _drop_audit_triggers()

    with op.batch_alter_table("fraud_signals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fraud_signals_organization_id"))
        batch_op.drop_index(batch_op.f("ix_fraud_signals_code"))
        batch_op.drop_index(batch_op.f("ix_fraud_signals_assessment_id"))

    op.drop_table("fraud_signals")
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alerts_organization_id"))
        batch_op.drop_index("ix_alerts_org_status")
        batch_op.drop_index(batch_op.f("ix_alerts_dedupe_key"))
        batch_op.drop_index(batch_op.f("ix_alerts_application_id"))

    op.drop_table("alerts")
    with op.batch_alter_table("risk_assessments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_risk_assessments_organization_id"))
        batch_op.drop_index(batch_op.f("ix_risk_assessments_disbursement_id"))
        batch_op.drop_index("ix_risk_assessments_app_current")

    op.drop_table("risk_assessments")
    with op.batch_alter_table("case_notes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_case_notes_organization_id"))
        batch_op.drop_index(batch_op.f("ix_case_notes_case_id"))

    op.drop_table("case_notes")
    with op.batch_alter_table("case_evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_case_evidence_organization_id"))
        batch_op.drop_index(batch_op.f("ix_case_evidence_case_id"))

    op.drop_table("case_evidence")
    with op.batch_alter_table("investigation_cases", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_investigation_cases_status"))
        batch_op.drop_index(batch_op.f("ix_investigation_cases_organization_id"))
        batch_op.drop_index(batch_op.f("ix_investigation_cases_assigned_to_id"))
        batch_op.drop_index(batch_op.f("ix_investigation_cases_application_id"))

    op.drop_table("investigation_cases")
    with op.batch_alter_table("identity_verifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_identity_verifications_student_id"))
        batch_op.drop_index(batch_op.f("ix_identity_verifications_status"))
        batch_op.drop_index(batch_op.f("ix_identity_verifications_organization_id"))
        batch_op.drop_index(batch_op.f("ix_identity_verifications_application_id"))

    op.drop_table("identity_verifications")
    with op.batch_alter_table("enrollment_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_enrollment_records_student_id"))
        batch_op.drop_index(batch_op.f("ix_enrollment_records_organization_id"))
        batch_op.drop_index(batch_op.f("ix_enrollment_records_application_id"))

    op.drop_table("enrollment_records")
    with op.batch_alter_table("disbursements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_disbursements_student_id"))
        batch_op.drop_index(batch_op.f("ix_disbursements_organization_id"))
        batch_op.drop_index("ix_disbursements_org_date")
        batch_op.drop_index(batch_op.f("ix_disbursements_destination_id"))
        batch_op.drop_index(batch_op.f("ix_disbursements_application_id"))

    op.drop_table("disbursements")
    with op.batch_alter_table("student_identity_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_student_identity_tokens_organization_id"))
        batch_op.drop_index("ix_identity_tokens_type_value")

    op.drop_table("student_identity_tokens")
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_user_read")

    op.drop_table("notifications")
    with op.batch_alter_table("financial_aid_applications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_student_id"))
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_scenario_key"))
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_risk_level"))
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_organization_id"))
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_ip_token"))
        batch_op.drop_index(batch_op.f("ix_financial_aid_applications_device_token"))
        batch_op.drop_index("ix_applications_org_submitted")
        batch_op.drop_index("ix_applications_org_risk")

    op.drop_table("financial_aid_applications")
    with op.batch_alter_table("detection_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_detection_runs_organization_id"))

    op.drop_table("detection_runs")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_target")
        batch_op.drop_index("ix_audit_org_time")
        batch_op.drop_index(batch_op.f("ix_audit_events_category"))
        batch_op.drop_index(batch_op.f("ix_audit_events_actor_user_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_action"))

    op.drop_table("audit_events")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role_id"))
        batch_op.drop_index(batch_op.f("ix_users_organization_id"))

    op.drop_table("users")
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_students_organization_id"))

    op.drop_table("students")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("payment_destination_tokens")
    op.drop_table("organizations")
