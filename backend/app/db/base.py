from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, MetaData, Numeric, Uuid, event
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.db.types import JSONType, UTCDateTime, utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        uuid.UUID: Uuid(),
        datetime: UTCDateTime(),
        Decimal: Numeric(12, 2),
        dict[str, Any]: JSONType,
        list[Any]: JSONType,
    }


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


@event.listens_for(Base, "init", propagate=True)
def _assign_id_on_construction(target: object, args: tuple, kwargs: dict) -> None:
    """Give every new entity its UUID immediately, so related rows can be linked before a flush."""
    if isinstance(target, UUIDPrimaryKey) and kwargs.get("id") is None:
        kwargs["id"] = uuid.uuid4()


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class TenantScoped:
    """Rows owned by one institution. Every query on these tables goes through tenancy.scoped()."""

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)


class Synthetic:
    """All records in this prototype are synthetic; real ingestion adapters must set False."""

    is_synthetic: Mapped[bool] = mapped_column(default=True)
