"""student portal accounts

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite batch mode rebuilds `users`; dependent audit tables prevent the temporary
    # table swap unless foreign-key enforcement is paused for this DDL operation.
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        op.execute("PRAGMA foreign_keys=OFF")
        # A prior interrupted batch migration can leave only this temporary table.
        op.execute("DROP TABLE IF EXISTS _alembic_tmp_users")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("student_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_users_student_id_students", "students", ["student_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_unique_constraint("uq_users_student_id", ["student_id"])
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_student_id", type_="unique")
        batch.drop_constraint("fk_users_student_id_students", type_="foreignkey")
        batch.drop_column("student_id")
