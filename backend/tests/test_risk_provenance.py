"""Assessments must explain their origin and limits, and the evaluation framework must refuse unjustified claims."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.detection.evaluation import (
    MIN_EXAMPLES_PER_CLASS,
    DatasetManifest,
    Example,
    UngovernedDatasetError,
    evaluate,
)
from app.models import AuditEvent, FinancialAidApplication, RiskAssessment
from app.seed.base import DEMO_STUDENT_EMAIL
from tests.conftest import NB_OFFICER
from tests.test_application_workflows import _officer_review, _submitted


@pytest.mark.seeded
class TestProvenance:
    def test_portal_assessment_records_its_origin_and_limits(self, as_user) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        assessment = as_user(NB_OFFICER).get(f"/api/v1/applications/{app['id']}").json()["assessment"]
        provenance = assessment["provenance"]
        assert provenance["rules_version"] == assessment["rules_version"]
        assert provenance["population_size"] > 400 and provenance["model_applied"] is True
        assert len(assessment["input_fingerprint"]) == 64
        assert assessment["score_reproducible"] is True
        limits = " ".join(assessment["limitations"])
        assert "not a finding of fraud" in limits and "No accuracy" in limits
        assert "No external fraud database" in limits and "student portal" in limits

    def test_tampering_with_a_stored_score_is_detectable(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        stored = db.scalar(select(RiskAssessment).where(RiskAssessment.application_id == uuid.UUID(app["id"])))
        assert stored is not None
        stored.score = min(stored.score + 40, 100)
        db.commit()
        assert (
            as_user(NB_OFFICER).get(f"/api/v1/applications/{app['id']}").json()["assessment"]["score_reproducible"]
            is False
        )

    def test_decisions_record_the_assessment_the_reviewer_saw(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        officer = as_user(NB_OFFICER)
        expected = officer.get(f"/api/v1/applications/{app['id']}").json()["assessment"]
        assert _officer_review(officer, app["id"], application_status="in_review").status_code == 200
        event = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "application.review", AuditEvent.target_id == app["id"])
        )
        assert event is not None
        assert event.details["assessment_seen"]["id"] == expected["id"]
        assert event.details["assessment_seen"]["rules_version"] == expected["rules_version"]

    def test_scoring_never_changes_an_application_decision(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        stored = db.get(FinancialAidApplication, uuid.UUID(app["id"]))
        assert stored is not None and stored.status == "submitted" and stored.review_status == "unreviewed"

    def test_records_inherit_the_student_data_classification(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        stored = db.get(FinancialAidApplication, uuid.UUID(app["id"]))
        assert stored is not None and stored.is_synthetic == stored.student.is_synthetic


GOVERNED = DatasetManifest(
    dataset_id="pilot-2027",
    is_synthetic=False,
    contains_direct_identifiers=False,
    labels_independent_of_system=True,
    consent_basis="Institutional data-sharing agreement 14",
    approved_by="Data governance board",
    approved_on=date(2027, 1, 15),
    label_source="Closed investigations",
)
SYNTHETIC = DatasetManifest(
    dataset_id="seed", is_synthetic=True, contains_direct_identifiers=False, labels_independent_of_system=False
)


def _balanced(count: int) -> list[Example]:
    return [Example(90.0, True)] * count + [Example(10.0, False)] * count


class TestEvaluationFramework:
    def test_synthetic_data_can_never_produce_a_performance_claim(self) -> None:
        report = evaluate(SYNTHETIC, _balanced(MIN_EXAMPLES_PER_CLASS * 2))
        assert report.claim_status == "not_a_performance_claim" and "real-world" in report.notice

    @pytest.mark.parametrize("field", ["consent_basis", "approved_by", "approved_on", "label_source"])
    def test_real_data_requires_recorded_governance(self, field: str) -> None:
        values = {**GOVERNED.__dict__, field: None}
        with pytest.raises(UngovernedDatasetError, match=field):
            evaluate(DatasetManifest(**values), _balanced(200))

    def test_circular_labels_are_refused(self) -> None:
        values = {**GOVERNED.__dict__, "labels_independent_of_system": False}
        with pytest.raises(UngovernedDatasetError, match="circular"):
            evaluate(DatasetManifest(**values), _balanced(200))

    def test_identifiable_datasets_are_refused(self) -> None:
        values = {**SYNTHETIC.__dict__, "contains_direct_identifiers": True}
        with pytest.raises(UngovernedDatasetError, match="identifiers"):
            evaluate(DatasetManifest(**values), _balanced(200))

    def test_small_samples_are_marked_insufficient(self) -> None:
        assert evaluate(GOVERNED, _balanced(MIN_EXAMPLES_PER_CLASS - 1)).claim_status == "insufficient_labels"

    def test_metrics_and_intervals_are_correct(self) -> None:
        examples = (
            [Example(90.0, True)] * 150
            + [Example(10.0, True)] * 50
            + [Example(90.0, False)] * 50
            + [Example(10.0, False)] * 150
        )
        report = evaluate(GOVERNED, examples)
        assert report.claim_status == "governed_evaluation"
        critical = report.thresholds[-1]
        assert (
            critical.true_positives,
            critical.false_positives,
            critical.true_negatives,
            critical.false_negatives,
        ) == (150, 50, 150, 50)
        assert critical.precision.value == 0.75 and critical.recall.value == 0.75
        assert critical.precision.lower < 0.75 < critical.precision.upper
