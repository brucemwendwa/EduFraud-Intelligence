"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""

from app.models.aid import Disbursement, EnrollmentRecord, FinancialAidApplication, PaymentDestinationToken
from app.models.audit import AuditEvent
from app.models.case import CaseDecision, CaseEvidence, CaseNote, InvestigationCase
from app.models.identity import Organization, Permission, Role, User, role_permissions
from app.models.notification import Notification
from app.models.risk import Alert, DetectionRun, FraudSignal, RiskAssessment
from app.models.student import Student, StudentIdentityToken
from app.models.verification import IdentityVerification

__all__ = [
    "Alert",
    "AuditEvent",
    "CaseDecision",
    "CaseEvidence",
    "CaseNote",
    "DetectionRun",
    "Disbursement",
    "EnrollmentRecord",
    "FinancialAidApplication",
    "FraudSignal",
    "IdentityVerification",
    "InvestigationCase",
    "Notification",
    "Organization",
    "PaymentDestinationToken",
    "Permission",
    "RiskAssessment",
    "Role",
    "Student",
    "StudentIdentityToken",
    "User",
    "role_permissions",
]
