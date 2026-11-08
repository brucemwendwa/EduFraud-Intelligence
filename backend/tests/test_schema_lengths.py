"""SQLite ignores VARCHAR lengths, so every value a status column can hold is checked against the schema here."""

from __future__ import annotations

from enum import StrEnum

import pytest

from app.detection.account_rules import ACCOUNT_ENGINE_METHOD
from app.detection.versions import ENGINE_METHOD
from app.models import (
    Alert,
    ApplicationDocument,
    ApplicationStatusHistory,
    CaseDecision,
    FinancialAidApplication,
    InvestigationCase,
    RiskAssessment,
    StudentFinancialAccount,
    StudentIDCard,
    VerificationRequest,
)
from app.models.enums import (
    AccountStatus,
    AlertStatus,
    ApplicationStatus,
    CardStatus,
    CaseStatus,
    DocumentReviewStatus,
    DocumentStatus,
    ReviewStatus,
    VerificationRequestStatus,
    VerificationStatus,
)


@pytest.mark.parametrize(
    ("model", "column", "values"),
    [
        (FinancialAidApplication, "status", ApplicationStatus),
        (FinancialAidApplication, "review_status", ReviewStatus),
        (FinancialAidApplication, "verification_status", VerificationStatus),
        (ApplicationStatusHistory, "to_status", ApplicationStatus),
        (ApplicationStatusHistory, "from_status", ApplicationStatus),
        (ApplicationDocument, "status", DocumentStatus),
        (ApplicationDocument, "review_status", DocumentReviewStatus),
        (InvestigationCase, "status", CaseStatus),
        (CaseDecision, "from_status", CaseStatus),
        (CaseDecision, "to_status", CaseStatus),
        (Alert, "status", AlertStatus),
        (VerificationRequest, "status", VerificationRequestStatus),
        (StudentFinancialAccount, "status", AccountStatus),
        (StudentIDCard, "status", CardStatus),
    ],
)
def test_status_columns_fit_every_value(model: type, column: str, values: type[StrEnum]) -> None:
    length = model.__table__.columns[column].type.length  # type: ignore[attr-defined]
    too_long = [v.value for v in values if len(v.value) > length]
    assert not too_long, f"{model.__name__}.{column} is VARCHAR({length}) but must hold {too_long}"


@pytest.mark.parametrize("method", [ENGINE_METHOD, ACCOUNT_ENGINE_METHOD])
def test_assessment_method_labels_fit(method: str) -> None:
    assert len(method) <= RiskAssessment.__table__.columns["method"].type.length  # type: ignore[attr-defined]
