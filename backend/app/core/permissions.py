"""Permission catalogue and role definitions (single source of truth, synced into the DB at startup).

Keep keys in sync with `frontend/src/lib/permissions.ts`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class P(StrEnum):
    DASHBOARD_READ = "dashboard:read"
    APPLICATIONS_READ = "applications:read"
    APPLICATIONS_REVIEW = "applications:review"
    APPLICATIONS_ASSESS = "applications:assess"
    PII_REVEAL = "pii:reveal"
    DISBURSEMENTS_READ = "disbursements:read"
    DISBURSEMENTS_HOLD = "disbursements:hold"
    VERIFICATIONS_READ = "verifications:read"
    VERIFICATIONS_INITIATE = "verifications:initiate"
    ALERTS_READ = "alerts:read"
    ALERTS_TRIAGE = "alerts:triage"
    NETWORK_READ = "network:read"
    CASES_READ = "cases:read"
    CASES_CREATE = "cases:create"
    CASES_UPDATE = "cases:update"
    CASES_ASSIGN = "cases:assign"
    CASES_RESOLVE = "cases:resolve"
    AUDIT_READ = "audit:read"
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    ORGS_MANAGE = "organizations:manage"
    DETECTION_RUN = "detection:run"


PERMISSION_DESCRIPTIONS: dict[P, tuple[str, str]] = {
    P.DASHBOARD_READ: ("overview", "View the fraud intelligence dashboard"),
    P.APPLICATIONS_READ: ("applications", "View financial aid applications and risk assessments"),
    P.APPLICATIONS_REVIEW: ("applications", "Record a review decision on an application"),
    P.APPLICATIONS_ASSESS: ("applications", "Re-run risk assessment for an application"),
    P.PII_REVEAL: ("privacy", "Reveal a masked student name (requires a justification; audited)"),
    P.DISBURSEMENTS_READ: ("disbursements", "View disbursements and risk indicators"),
    P.DISBURSEMENTS_HOLD: ("disbursements", "Place or release a hold on a disbursement"),
    P.VERIFICATIONS_READ: ("verification", "View identity verification history"),
    P.VERIFICATIONS_INITIATE: ("verification", "Start a verification or record an alternative verification"),
    P.ALERTS_READ: ("alerts", "View fraud alerts"),
    P.ALERTS_TRIAGE: ("alerts", "Acknowledge or dismiss alerts"),
    P.NETWORK_READ: ("network", "Explore the fraud relationship graph"),
    P.CASES_READ: ("investigations", "View investigation cases"),
    P.CASES_CREATE: ("investigations", "Open investigation cases"),
    P.CASES_UPDATE: ("investigations", "Update cases, add notes and evidence"),
    P.CASES_ASSIGN: ("investigations", "Assign cases to investigators"),
    P.CASES_RESOLVE: ("investigations", "Record a case resolution"),
    P.AUDIT_READ: ("governance", "View the audit trail"),
    P.USERS_READ: ("governance", "View users and roles"),
    P.USERS_MANAGE: ("governance", "Create users and change roles"),
    P.ORGS_MANAGE: ("governance", "Create and edit institutions (platform level)"),
    P.DETECTION_RUN: ("detection", "Trigger detection engine runs"),
}


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    description: str
    permissions: frozenset[P]
    is_platform_role: bool = False


_READ_ONLY = frozenset(
    {
        P.DASHBOARD_READ,
        P.APPLICATIONS_READ,
        P.DISBURSEMENTS_READ,
        P.VERIFICATIONS_READ,
        P.ALERTS_READ,
        P.NETWORK_READ,
        P.CASES_READ,
    }
)

ROLES: tuple[RoleDef, ...] = (
    RoleDef(
        key="platform_admin",
        name="Platform Administrator",
        description="Operates the EduShield platform across all institutions.",
        permissions=frozenset(P),
        is_platform_role=True,
    ),
    RoleDef(
        key="institution_admin",
        name="Institution Administrator",
        description="Manages users and oversees fraud operations for one institution.",
        permissions=frozenset(P) - {P.ORGS_MANAGE},
    ),
    RoleDef(
        key="fraud_investigator",
        name="Fraud Investigator",
        description="Investigates alerts, manages cases and records decisions.",
        permissions=_READ_ONLY
        | {
            P.APPLICATIONS_REVIEW,
            P.APPLICATIONS_ASSESS,
            P.PII_REVEAL,
            P.DISBURSEMENTS_HOLD,
            P.VERIFICATIONS_INITIATE,
            P.ALERTS_TRIAGE,
            P.CASES_CREATE,
            P.CASES_UPDATE,
            P.CASES_ASSIGN,
            P.CASES_RESOLVE,
            P.DETECTION_RUN,
        },
    ),
    RoleDef(
        key="financial_aid_officer",
        name="Financial Aid Officer",
        description="Processes aid, verifies students and refers suspicious activity.",
        permissions=(_READ_ONLY - {P.NETWORK_READ})
        | {
            P.APPLICATIONS_REVIEW,
            P.PII_REVEAL,
            P.DISBURSEMENTS_HOLD,
            P.VERIFICATIONS_INITIATE,
            P.ALERTS_TRIAGE,
            P.CASES_CREATE,
        },
    ),
    RoleDef(
        key="auditor",
        name="Read-only Auditor",
        description="Reviews activity and the audit trail without changing data or seeing unmasked PII.",
        permissions=_READ_ONLY | {P.AUDIT_READ, P.USERS_READ},
    ),
)

ROLE_BY_KEY = {r.key: r for r in ROLES}
