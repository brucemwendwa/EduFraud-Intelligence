"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""

from app.models.account import Device, SecurityEvent, StudentFinancialAccount, StudentIDCard, Transaction
from app.models.aid import (
    ApplicationStatusHistory,
    Disbursement,
    EnrollmentRecord,
    FinancialAidApplication,
    PaymentDestinationToken,
)
from app.models.audit import AuditEvent
from app.models.case import CaseDecision, CaseEvidence, CaseNote, InvestigationCase
from app.models.document import ApplicationDocument, DocumentObjectCleanup, DocumentScanJob
from app.models.identity import Organization, Permission, Role, User, role_permissions
from app.models.notification import Notification
from app.models.risk import Alert, AlertNote, DetectionRun, FraudSignal, RiskAssessment
from app.models.student import Student, StudentIdentityToken, StudentInvitation
from app.models.verification import IdentityVerification, VerificationRequest, VerificationRequestEvent

__all__ = [
    "Alert",
    "AlertNote",
    "ApplicationStatusHistory",
    "ApplicationDocument",
    "DocumentObjectCleanup",
    "DocumentScanJob",
    "Device",
    "SecurityEvent",
    "StudentFinancialAccount",
    "StudentIDCard",
    "Transaction",
    "VerificationRequest",
    "VerificationRequestEvent",
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
    "StudentInvitation",
    "User",
    "role_permissions",
]
