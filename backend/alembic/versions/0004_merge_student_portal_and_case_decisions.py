"""Merge student portal and case decision migration branches.

Revision ID: 0004
Revises: 0002, 0003
"""

from collections.abc import Sequence


revision: str = "0004"
down_revision: tuple[str, str] = ("0002", "0003")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join independent schema branches; their DDL is applied by parent revisions."""


def downgrade() -> None:
    """The parent revisions own their respective downgrade operations."""
