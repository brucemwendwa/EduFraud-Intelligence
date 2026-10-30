"""Domain vocabularies shared by models, schemas and services. Stored as strings in the database."""

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApplicationStatus(StrEnum):
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ON_HOLD = "on_hold"
    WITHDRAWN = "withdrawn"


class VerificationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in_review"
    CLEARED = "cleared"
    ESCALATED = "escalated"


class EnrollmentStatus(StrEnum):
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"
    NEVER_ATTENDED = "never_attended"
    COMPLETED = "completed"


class Modality(StrEnum):
    IN_PERSON = "in_person"
    ONLINE = "online"
    HYBRID = "hybrid"


class FundType(StrEnum):
    PELL_GRANT = "pell_grant"
    DIRECT_SUBSIDIZED = "direct_subsidized"
    DIRECT_UNSUBSIDIZED = "direct_unsubsidized"
    INSTITUTIONAL_GRANT = "institutional_grant"
    CREDIT_BALANCE_REFUND = "credit_balance_refund"


class DisbursementStatus(StrEnum):
    SCHEDULED = "scheduled"
    RELEASED = "released"
    HELD = "held"
    REVERSED = "reversed"


class VerificationTrigger(StrEnum):
    PRE_DISBURSEMENT = "pre_disbursement"
    NEW_DEVICE_LOGIN = "new_device_login"
    ACCOUNT_RECOVERY = "account_recovery"
    PAYMENT_DESTINATION_CHANGE = "payment_destination_change"
    RISK_REVIEW = "risk_review"


class VerificationMethod(StrEnum):
    DOCUMENT_BIOMETRIC = "document_biometric"
    IN_PERSON_ID_CHECK = "in_person_id_check"
    OFFICER_VIDEO_CALL = "officer_video_call"
    MAILED_CODE = "mailed_code"


class VerificationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    REVIEW = "review"


class SignalCategory(StrEnum):
    IDENTITY = "identity"
    APPLICATION = "application"
    ENROLLMENT = "enrollment"
    DISBURSEMENT = "disbursement"
    NETWORK = "network"
    BIOMETRIC = "biometric"
    ANOMALY = "anomaly"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_INVESTIGATION = "in_investigation"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class CaseStatus(StrEnum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CasePriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CaseFinding(StrEnum):
    """What the people investigating have established (never set by the AI)."""

    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SUSPECTED_FRAUD = "suspected_fraud"
    CONFIRMED_FRAUD = "confirmed_fraud"
    NOT_SUBSTANTIATED = "not_substantiated"


class CaseDecisionType(StrEnum):
    ESCALATE = "escalate"
    RESOLVE = "resolve"
    REOPEN = "reopen"
    CLOSE = "close"


class CaseResolution(StrEnum):
    CONFIRMED_FRAUD = "confirmed_fraud"
    NO_FRAUD_FOUND = "no_fraud_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REFERRED_EXTERNALLY = "referred_externally"


class EvidenceType(StrEnum):
    ALERT = "alert"
    RISK_ASSESSMENT = "risk_assessment"
    VERIFICATION = "verification"
    DISBURSEMENT = "disbursement"
    APPLICATION = "application"
    NETWORK_CLUSTER = "network_cluster"
    DOCUMENT_NOTE = "document_note"


class AuditCategory(StrEnum):
    AUTHENTICATION = "authentication"
    VERIFICATION = "verification"
    INVESTIGATION = "investigation"
    PERMISSION = "permission"
    DATA_ACCESS = "data_access"
    DETECTION = "detection"
    DISBURSEMENT = "disbursement"
    APPLICATION = "application"
    SYSTEM = "system"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
