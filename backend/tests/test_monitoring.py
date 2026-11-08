"""Application pipeline and operations monitoring: real counts, tenant scope and no private data."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DetectionRun, FinancialAidApplication, User
from app.models.enums import RunStatus
from app.seed.base import DEMO_STUDENT_EMAIL
from tests.conftest import ADMIN, LS_INVESTIGATOR, NB_ADMIN, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER
from tests.test_application_workflows import _draft, _submitted

pytestmark = pytest.mark.seeded


class TestApplicationPipeline:
    def test_counts_come_from_scoped_records(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        scope = db.scalar(select(User).where(User.email == NB_OFFICER)).organization_id
        body = officer.get("/api/v1/dashboard/applications").json()
        stored = db.scalars(
            select(FinancialAidApplication.status).where(
                FinancialAidApplication.organization_id == scope, FinancialAidApplication.submitted_at.is_not(None)
            )
        ).all()
        assert body["total"] == len(stored)
        assert body["approved"] == stored.count("approved")
        assert body["awaiting_review"] == stored.count("received") + stored.count("submitted")

    def test_new_submission_moves_the_pipeline_and_drafts_do_not(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        officer = as_user(NB_OFFICER)
        before = officer.get("/api/v1/dashboard/applications").json()
        _draft(student)
        assert officer.get("/api/v1/dashboard/applications").json()["total"] == before["total"]
        app = _submitted(student)
        after = officer.get("/api/v1/dashboard/applications").json()
        assert after["awaiting_review"] == before["awaiting_review"] + 1
        assert after["recent_activity"][0]["reference"] == app["reference"]

    def test_scoped_by_institution_and_permission(self, as_user) -> None:  # type: ignore[no-untyped-def]
        northbridge = as_user(NB_OFFICER).get("/api/v1/dashboard/applications").json()
        lakeshore = as_user(LS_INVESTIGATOR).get("/api/v1/dashboard/applications").json()
        assert northbridge["total"] != lakeshore["total"]
        assert not {a["reference"] for a in northbridge["recent_activity"]} & {
            a["reference"] for a in lakeshore["recent_activity"]
        }
        assert as_user(DEMO_STUDENT_EMAIL).get("/api/v1/dashboard/applications").status_code == 403


class TestOperations:
    def test_requires_operations_permission(self, as_user) -> None:  # type: ignore[no-untyped-def]
        assert as_user(NB_INVESTIGATOR).get("/api/v1/operations/overview").status_code == 403
        assert as_user(NB_OFFICER).get("/api/v1/operations/overview").status_code == 403
        assert as_user(DEMO_STUDENT_EMAIL).get("/api/v1/operations/overview").status_code == 403
        assert as_user(NB_AUDITOR).get("/api/v1/operations/overview").status_code == 200

    def test_reports_unconfigured_services_honestly(self, as_user) -> None:  # type: ignore[no-untyped-def]
        body = as_user(NB_ADMIN).get("/api/v1/operations/overview").json()
        health = {check["key"]: check["status"] for check in body["health"]}
        assert body["scope"] == "institution"
        assert health["database"] == "ok" and health["migrations"] == "ok"
        assert health["storage"] == "not_configured" and health["scanner"] == "not_configured"
        assert health["email"] == "not_configured" and health["jobs"] == "not_configured"
        assert health["identity"] == "simulated" and health["payments"] == "simulated"
        assert body["overall_health"] == "ok"

    def test_counts_are_tenant_scoped_and_free_of_private_data(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        admin = as_user(NB_ADMIN)
        response = admin.get("/api/v1/operations/overview")
        body = response.json()
        assert body["applications"]["submitted_24h"] >= 1
        assert app["reference"] not in response.text
        assert DEMO_STUDENT_EMAIL not in response.text
        assert all("details" not in entry and "actor_email" not in entry for entry in body["recent_audit"])

        platform = as_user(ADMIN).get("/api/v1/operations/overview").json()
        assert platform["scope"] == "platform"
        assert platform["applications"]["open_total"] > body["applications"]["open_total"]

    def test_failed_jobs_surface_without_exception_text(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        scope = db.scalar(select(User).where(User.email == NB_ADMIN)).organization_id
        db.add(
            DetectionRun(
                organization_id=scope,
                status=RunStatus.FAILED,
                mode="inline",
                rules_version="test",
                model_version="test",
                error="secret student detail in traceback",
            )
        )
        db.commit()
        response = as_user(NB_ADMIN).get("/api/v1/operations/overview")
        assert response.json()["risk"]["failed_runs_7d"] >= 1
        assert any(f["kind"] == "detection_run" for f in response.json()["jobs"]["recent_failures"])
        assert "secret student detail" not in response.text
