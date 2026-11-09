from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Schema

DocumentCategory = Literal[
    "government_id", "admission_proof", "academic_record", "income_evidence", "guardian_sponsor", "other"
]


class DocumentOut(Schema):
    id: uuid.UUID
    application_id: uuid.UUID
    original_filename: str
    detected_mime_type: str
    size_bytes: int
    category: str
    status: str
    scanner_provider: str | None
    scanned_at: datetime | None
    review_status: str
    review_reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None
    replaces_document_id: uuid.UUID | None


class DocumentReview(Schema):
    decision: Literal["accepted", "rejected", "replacement_requested"]
    reason: str = Field(min_length=5, max_length=1000)


class DownloadUrl(Schema):
    url: str
    expires_in_seconds: int
