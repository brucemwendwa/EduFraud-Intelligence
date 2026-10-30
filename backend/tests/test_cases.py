"""Investigation-case workflow, authorization, auditability, and tenant isolation."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, AuditEvent, Organization
from tests.conftest import LS_INVESTIGATOR, NB_AUDITOR, NB_INVESTIGATOR

pytestmark = pytest.mark.seeded


def test_investigator_can_open_and_resolve_a_case_from_an_alert(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    northbridge = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
    alert = db.scalar(select(Alert).where(Alert.organization_id == northbridge.id).order_by(Alert.created_at.desc()))  # type: ignore[union-attr]
    assert alert is not None
    client = as_user(NB_INVESTIGATOR)
    created = client.post(
        "/api/v1/cases",
        json={"title": "Investigate linked aid activity", "alert_id": str(alert.id), "fraud_category": "identity"},
    )
    assert created.status_code == 201, created.text
    case = created.json()
    assert case["reference"].startswith("CASE-") and case["status"] == "new"
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/notes", json={"body": "Officer contacted through known-good channel."}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/evidence",
            json={"evidence_type": "alert", "title": "Risk alert", "summary": "Linked from triage queue."},
        ).status_code
        == 200
    )
    resolved = client.post(
        f"/api/v1/cases/{case['id']}/resolve",
        json={"resolution": "insufficient_evidence", "summary": "Evidence reviewed; no adverse action was taken."},
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert len(resolved.json()["notes"]) == len(resolved.json()["evidence"]) == 1
    actions = db.scalars(select(AuditEvent.action).where(AuditEvent.target_ref == case["reference"])).all()
    assert actions == ["case.create", "case.note_add", "case.evidence_add", "case.resolve"]


def test_cases_require_permissions_and_do_not_cross_tenants(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    northbridge = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
    alert = db.scalar(select(Alert).where(Alert.organization_id == northbridge.id).order_by(Alert.created_at.desc()))  # type: ignore[union-attr]
    assert alert is not None
    payload = {"title": "Investigate scoped alert", "alert_id": str(alert.id), "fraud_category": "identity"}
    assert as_user(NB_AUDITOR).post("/api/v1/cases", json=payload).status_code == 403
    created = as_user(NB_INVESTIGATOR).post("/api/v1/cases", json=payload)
    assert created.status_code == 201, created.text
    assert as_user(LS_INVESTIGATOR).get(f"/api/v1/cases/{created.json()['id']}").status_code == 404
