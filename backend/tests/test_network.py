"""Phase 8: fraud network clusters and graphs, including cross-institution privacy."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, FinancialAidApplication
from tests.conftest import ADMIN, LS_INVESTIGATOR, NB_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded


def _ring_cluster(clusters: list[dict]) -> dict:
    return next(c for c in clusters if c["size"] >= 8)


def test_clusters_cover_the_planted_networks(as_user) -> None:  # type: ignore[no-untyped-def]
    clusters = as_user(ADMIN).get("/api/v1/network/clusters").json()
    scenarios = {s for c in clusters for s in c["scenarios"]}
    assert {"coordinated_network", "duplicate_identity", "shared_destination"} <= scenarios
    assert not any(s.startswith("control_") for s in scenarios), "legitimate controls must not form clusters"
    assert clusters[0]["risk_level"] == "critical"


def test_platform_admin_sees_the_whole_ring(as_user) -> None:  # type: ignore[no-untyped-def]
    c = as_user(ADMIN)
    ring = _ring_cluster(c.get("/api/v1/network/clusters").json())
    graph = c.get("/api/v1/network/graph", params={"cluster": ring["id"]}).json()
    assert graph["stats"]["applications"] == ring["size"] and graph["stats"]["applications_other_institutions"] == 0
    types = {n["type"] for n in graph["nodes"]}
    assert {"application", "student", "institution", "destination", "device", "enrollment", "alert"} <= types
    assert any(e["suspicious"] for e in graph["edges"])
    assert all("x" in n and "y" in n for n in graph["nodes"])


def test_other_institutions_records_are_anonymised(as_user) -> None:  # type: ignore[no-untyped-def]
    c = as_user(NB_INVESTIGATOR)
    ring = _ring_cluster(c.get("/api/v1/network/clusters").json())
    assert ring["applications_in_scope"] == 1 and ring["applications_other_institutions"] == 8
    graph = c.get("/api/v1/network/graph", params={"cluster": ring["id"]}).json()
    apps = [n for n in graph["nodes"] if n["type"] == "application"]
    assert len(apps) == 1
    external = [n for n in graph["nodes"] if n["type"] == "external"]
    assert external and all("FA-" not in n["label"] and "STU-" not in n["label"] for n in external)
    institutions = {n["label"] for n in graph["nodes"] if n["type"] == "institution"}
    assert institutions == {"Northbridge State University"}


def test_focus_mode_and_lakeshore_view(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    ring_app = db.scalar(
        select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "coordinated_network")
    )
    graph = as_user(ADMIN).get("/api/v1/network/graph", params={"focus": str(ring_app.id)}).json()  # type: ignore[union-attr]
    assert graph["focus"] == f"app:{ring_app.id}" and graph["cluster_id"]  # type: ignore[union-attr]
    lakeshore = as_user(LS_INVESTIGATOR).get("/api/v1/network/clusters").json()
    assert _ring_cluster(lakeshore)["applications_in_scope"] == 6


def test_out_of_scope_focus_and_bad_input(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    nb_app = db.scalar(
        select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "unusual_disbursement")
    )
    c = as_user(LS_INVESTIGATOR)
    assert c.get("/api/v1/network/graph", params={"focus": str(nb_app.id)}).status_code == 404  # type: ignore[union-attr]
    assert c.get("/api/v1/network/graph").status_code == 422
    assert c.get("/api/v1/network/graph", params={"cluster": "CL-<script>"}).status_code == 422


def test_network_requires_permission_and_views_are_audited(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    assert as_user(NB_OFFICER).get("/api/v1/network/clusters").status_code == 403
    c = as_user(NB_INVESTIGATOR)
    ring = _ring_cluster(c.get("/api/v1/network/clusters").json())
    c.get("/api/v1/network/graph", params={"cluster": ring["id"]})
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "network.view"))
    assert event is not None and event.category == "data_access" and event.target_ref == ring["id"]
