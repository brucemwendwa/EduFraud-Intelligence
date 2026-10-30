"""Human-readable sequential references (ALT-00042, CASE-2026-0007, IDV-030011)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_reference(db: Session, model: type, prefix: str, width: int) -> str:
    column = model.reference  # type: ignore[attr-defined]
    last = db.scalar(select(func.max(column)).where(column.like(f"{prefix}-%")))
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}-{number:0{width}d}"
