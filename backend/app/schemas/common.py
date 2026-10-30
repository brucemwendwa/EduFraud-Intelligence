from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](Schema):
    items: list[T]
    total: int
    page: int
    page_size: int


class OrgRef(Schema):
    id: uuid.UUID
    name: str
    slug: str


class UserRef(Schema):
    id: uuid.UUID
    full_name: str
    email: str


class Pagination:
    """Shared ?page=&page_size= query parameters with sane bounds."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, le=10_000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


ReasonText = Annotated[str, Field(min_length=5, max_length=500)]
