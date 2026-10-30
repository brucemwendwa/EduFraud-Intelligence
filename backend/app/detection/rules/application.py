"""Submission-pattern rules: bursts of applications from one device or network."""

from __future__ import annotations

from datetime import timedelta

from app.detection.context import DetectionContext
from app.detection.signals import Signal
from app.detection.versions import RULES_VERSION
from app.models import FinancialAidApplication
from app.models.enums import Severity, SignalCategory

BURST_WINDOW = timedelta(hours=72)
BURST_MIN_APPS = 3


def burst_peers(app: FinancialAidApplication, peers: list[FinancialAidApplication]) -> list[FinancialAidApplication]:
    """Applications from the same source submitted within the burst window of this one."""
    return [p for p in peers if p.id != app.id and abs(p.submitted_at - app.submitted_at) <= BURST_WINDOW]


def evaluate(ctx: DetectionContext, app: FinancialAidApplication) -> list[Signal]:
    signals: list[Signal] = []
    devices = ctx.device_apps.get(app.device_token or "", [])
    device_burst = burst_peers(app, devices)
    if len(device_burst) + 1 >= BURST_MIN_APPS:
        signals.append(
            Signal(
                code="DEVICE_BURST",
                category=SignalCategory.APPLICATION,
                severity=Severity.HIGH,
                weight=0.4,
                title="Burst of applications from one device",
                description=(
                    f"{len(device_burst) + 1} applications for different students were submitted from the same device "
                    "within 72 hours."
                ),
                version=RULES_VERSION,
                evidence={"applications_in_window": len(device_burst) + 1, "window_hours": 72},
            )
        )
    elif len(devices) >= BURST_MIN_APPS:
        signals.append(
            Signal(
                code="SHARED_DEVICE_SPREAD",
                category=SignalCategory.APPLICATION,
                severity=Severity.INFO,
                weight=0.03,
                title="Shared device used over a long period",
                description=(
                    f"The device was used by {len(devices)} applicants spread over weeks or months, consistent with a "
                    "campus kiosk or library computer."
                ),
                version=RULES_VERSION,
                evidence={"applications_on_device": len(devices)},
            )
        )

    ip_burst = burst_peers(app, ctx.ip_apps.get(app.ip_token or "", []))
    if len(ip_burst) + 1 >= BURST_MIN_APPS:
        signals.append(
            Signal(
                code="NETWORK_BURST",
                category=SignalCategory.APPLICATION,
                severity=Severity.MEDIUM,
                weight=0.2,
                title="Burst of applications from one network address",
                description=f"{len(ip_burst) + 1} applications came from the same network address within 72 hours.",
                version=RULES_VERSION,
                evidence={"applications_in_window": len(ip_burst) + 1},
            )
        )

    if app.submitted_at.hour < 5:
        signals.append(
            Signal(
                code="OFF_HOURS_SUBMISSION",
                category=SignalCategory.APPLICATION,
                severity=Severity.INFO,
                weight=0.05,
                title="Submitted between midnight and 5 a.m.",
                description=(
                    "Late-night submissions are common for students; this only matters alongside other signals."
                ),
                version=RULES_VERSION,
                evidence={"hour_utc": app.submitted_at.hour},
            )
        )
    return signals
