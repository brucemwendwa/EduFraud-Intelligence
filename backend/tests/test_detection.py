"""Phase 6: explainable scoring, rule behaviour on planted scenarios, alerts, runs and fairness guarantees."""

from __future__ import annotations

import uuid
from collections import defaultdict

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.detection import anomaly
from app.detection.catalog import RULES
from app.detection.engine import DetectionEngine
from app.detection.signals import Signal, combine, level_for
from app.models import Alert, AuditEvent, DetectionRun, FinancialAidApplication, FraudSignal, RiskAssessment
from app.models.enums import RiskLevel, Severity
from tests.conftest import NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER


def _sig(code: str, weight: float) -> Signal:
    return Signal(code=code, category="test", severity=Severity.LOW, weight=weight, title=code, description="")


class TestScoring:
    def test_noisy_or_combination_and_exact_point_decomposition(self) -> None:
        signals = [_sig("A", 0.5), _sig("B", 0.4), _sig("C", 0.05)]
        score = combine(signals)
        assert score == pytest.approx(100 * (1 - 0.5 * 0.6 * 0.95), abs=0.05)
        assert sum(s.points for s in signals) == pytest.approx(score, abs=0.2)
        assert signals[0].points > signals[1].points > signals[2].points

    def test_score_is_bounded_and_empty_is_zero(self) -> None:
        assert combine([]) == 0.0
        assert combine([_sig(str(i), 0.99) for i in range(10)]) <= 100.0

    @pytest.mark.parametrize(
        ("score", "level"),
        [
            (0, RiskLevel.LOW),
            (29.9, RiskLevel.LOW),
            (30, RiskLevel.MEDIUM),
            (60, RiskLevel.HIGH),
            (80, RiskLevel.CRITICAL),
        ],
    )
    def test_level_thresholds(self, score: float, level: RiskLevel) -> None:
        assert level_for(score) == level

    def test_benign_signals_alone_cannot_reach_review(self) -> None:
        benign = [_sig("SHARED_HOUSEHOLD_OR_RESIDENCE", 0.04), _sig("SHARED_DEVICE_SPREAD", 0.03), _sig("OFF", 0.05)]
        assert level_for(combine(benign)) == RiskLevel.LOW


class TestFairness:
    def test_anomaly_features_exclude_income_and_demographics(self) -> None:
        names = " ".join(n for n, _ in anomaly.FEATURES).lower()
        for forbidden in ("aid_index", "sai", "income", "dependency", "age", "birth", "state", "gender", "race"):
            assert forbidden not in names

    def test_model_influence_is_capped_below_critical(self) -> None:
        assert anomaly.MAX_WEIGHT <= 0.30
        # On its own the model can ask for a look (medium) but never drive a record to high or critical.
        assert level_for(combine([_sig("ANOMALY_MODEL", anomaly.MAX_WEIGHT)])) in (RiskLevel.LOW, RiskLevel.MEDIUM)


@pytest.mark.seeded
class TestScenarioOutcomes:
    def _levels(self, db: Session) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for a in db.scalars(select(FinancialAidApplication).where(FinancialAidApplication.scenario_key.is_not(None))):
            out[a.scenario_key].append(a.risk_level)  # type: ignore[index, arg-type]
        return out

    def test_every_fraud_scenario_is_high_or_critical(self, db: Session) -> None:
        levels = self._levels(db)
        for scenario in ("coordinated_network", "duplicate_identity", "shared_destination", "unusual_disbursement"):
            assert levels[scenario] and set(levels[scenario]) <= {"high", "critical"}, scenario

    def test_legitimate_controls_are_not_flagged(self, db: Session) -> None:
        for scenario, levels in self._levels(db).items():
            if scenario.startswith("control_"):
                assert set(levels) <= {"low", "medium"}, scenario

    def test_baseline_is_overwhelmingly_low_risk(self, db: Session) -> None:
        baseline = db.scalars(
            select(FinancialAidApplication.risk_level).where(FinancialAidApplication.scenario_key.is_(None))
        ).all()
        flagged = [lvl for lvl in baseline if lvl in ("high", "critical")]
        assert len(flagged) == 0 and len(baseline) > 400

    def test_expected_signals_fire(self, db: Session) -> None:
        def codes(scenario: str) -> set[str]:
            return set(
                db.scalars(
                    select(FraudSignal.code)
                    .join(RiskAssessment, RiskAssessment.id == FraudSignal.assessment_id)
                    .join(FinancialAidApplication, FinancialAidApplication.id == RiskAssessment.application_id)
                    .where(FinancialAidApplication.scenario_key == scenario, RiskAssessment.is_current)
                )
            )

        assert {"SSN_IDENTITY_CONFLICT", "DEVICE_BURST", "NETWORK_CLUSTER"} <= codes("duplicate_identity")
        assert {"DESTINATION_SHARED"} <= codes("shared_destination")
        assert {"AMOUNT_OUTLIER", "DISBURSEMENT_BURST"} <= codes("unusual_disbursement")
        assert {"NETWORK_CLUSTER", "DEVICE_BURST", "NO_ATTENDANCE"} <= codes("coordinated_network")
        assert "DESTINATION_CHANGE_VERIFIED" in codes("control_bank_change")
        assert "SSN_IDENTITY_CONFLICT" not in codes("control_transfer")

    def test_every_emitted_code_is_documented(self, db: Session) -> None:
        emitted = set(db.scalars(select(FraudSignal.code).distinct()))
        assert emitted <= {r.code for r in RULES}

    def test_assessments_are_explainable_and_versioned(self, db: Session) -> None:
        app = db.scalar(
            select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "duplicate_identity")
        )
        a = db.scalar(select(RiskAssessment).where(RiskAssessment.application_id == app.id, RiskAssessment.is_current))  # type: ignore[union-attr]
        assert a is not None and a.rules_version.startswith("rules-") and a.method.startswith("hybrid")
        assert a.explanation.startswith(f"Score {a.score:.0f}/100") and a.recommended_action
        assert sum(s.points for s in a.signals) == pytest.approx(a.score, abs=0.5)

    def test_rerunning_detection_is_idempotent(self, db: Session) -> None:
        alerts_before = db.scalar(select(func.count()).select_from(Alert))
        stats = DetectionEngine(db).prepare().run()
        db.commit()
        assert stats.alerts_created == 0 and stats.assessments_changed == 0
        assert db.scalar(select(func.count()).select_from(Alert)) == alerts_before

    def test_one_live_alert_per_application(self, db: Session) -> None:
        rows = db.execute(select(Alert.application_id, func.count()).group_by(Alert.application_id)).all()
        assert rows and all(n == 1 for _, n in rows)


@pytest.mark.seeded
class TestDetectionApi:
    def test_application_detail_includes_explainable_assessment(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = db.scalar(
            select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "unusual_disbursement")
        )
        detail = as_user(NB_INVESTIGATOR).get(f"/api/v1/applications/{app.id}").json()  # type: ignore[union-attr]
        assessment = detail["assessment"]
        assert assessment["level"] in ("high", "critical")
        assert {"code", "points", "description", "method", "version", "evidence"} <= set(assessment["signals"][0])
        assert detail["alerts"] and detail["alerts"][0]["title"] == "Unusual disbursement activity"
        assert detail["assessment_history"]

    def test_manual_reassessment_is_permissioned_and_audited(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = db.scalar(select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "control_dorm"))
        url = f"/api/v1/applications/{app.id}/assess"  # type: ignore[union-attr]
        assert as_user(NB_OFFICER).post(url).status_code == 403
        res = as_user(NB_INVESTIGATOR).post(url)
        assert res.status_code == 200 and res.json()["assessment"]["level"] == "low"
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "application.assess")) is not None

    def test_detection_run_executes_in_background_and_records_outcome(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        res = as_user(NB_INVESTIGATOR).post("/api/v1/detection/runs")
        assert res.status_code == 202 and res.json()["mode"] == "inline"
        db.expire_all()
        run = db.get(DetectionRun, uuid.UUID(res.json()["id"]))
        assert run is not None and run.status == "completed" and run.applications_scored > 0
        status = as_user(NB_INVESTIGATOR).get("/api/v1/detection/status").json()
        assert status["last_run"]["id"] == str(run.id)
        assert "Not evaluated" in status["model_card"]["evaluation"]
        assert as_user(NB_AUDITOR).post("/api/v1/detection/runs").status_code == 403

    def test_scenario_validation_passes_for_all_scenarios(self, as_user) -> None:  # type: ignore[no-untyped-def]
        checks = as_user("admin@edushield.demo").get("/api/v1/detection/scenario-validation").json()
        assert len(checks) == 10
        assert all(c["passed"] for c in checks), [c["scenario"] for c in checks if not c["passed"]]

    def test_alert_triage_lifecycle(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        open_alerts = client.get("/api/v1/alerts", params={"status": "open"}).json()["items"]
        assert open_alerts
        target = open_alerts[0]["id"]
        assert client.patch(f"/api/v1/alerts/{target}", json={"action": "dismiss"}).status_code == 422
        ack = client.patch(f"/api/v1/alerts/{target}", json={"action": "acknowledge"})
        assert ack.status_code == 200 and ack.json()["status"] == "acknowledged"
        assert client.patch(f"/api/v1/alerts/{target}", json={"action": "acknowledge"}).status_code == 409
        dismissed = client.patch(f"/api/v1/alerts/{target}", json={"action": "dismiss", "note": "Verified in person"})
        assert dismissed.json()["status"] == "dismissed" and dismissed.json()["triage_note"] == "Verified in person"
        assert as_user(NB_AUDITOR).patch(f"/api/v1/alerts/{target}", json={"action": "reopen"}).status_code == 403

    def test_alerts_are_tenant_scoped(self, as_user) -> None:  # type: ignore[no-untyped-def]
        items = as_user("investigator@lakeshore.demo").get("/api/v1/alerts", params={"page_size": 100}).json()["items"]
        assert items and {i["organization"]["slug"] for i in items} == {"lakeshore"}
