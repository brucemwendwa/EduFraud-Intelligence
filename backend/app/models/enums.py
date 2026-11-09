"""Domain vocabularies shared by models, schemas and services. Stored as strings in the database."""

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    ADDITIONAL_INFORMATION_REQUIRED = "additional_information_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"
    WITHDRAWN = "withdrawn"


class DocumentStatus(StrEnum):
    PENDING_SCAN = "pending_scan"
    SCANNING = "scanning"
    AVAILABLE = "available"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class DocumentReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REPLACEMENT_REQUESTED = "replacement_requested"


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
    # Account-protection risk categories (student ID-linked accounts)
    DEVICE = "device"
    AUTHENTICATION = "authentication"
    TRANSACTION = "transaction"
    LOCATION = "location"
    CARD_SECURITY = "card_security"
    ACCOUNT_RECOVERY = "account_recovery"
    AID_REDIRECTION = "aid_redirection"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"  # shown as "New"
    ACKNOWLEDGED = "acknowledged"  # shown as "Under review"
    VERIFICATION_REQUESTED = "verification_requested"
    ESCALATED = "escalated"
    IN_INVESTIGATION = "in_investigation"
    DISMISSED = "dismissed"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


class AlertCategory(StrEnum):
    """Account-protection alert categories. Application alerts keep their SignalCategory values."""

    LOST_STOLEN_CARD = "lost_stolen_card"
    SUSPICIOUS_LOGIN = "suspicious_login"
    NEW_DEVICE = "new_device"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - alert category, not a secret
    ACCOUNT_TAKEOVER = "account_takeover"
    UNUSUAL_TRANSACTION = "unusual_transaction"
    SUSPICIOUS_LOCATION = "suspicious_location"
    AID_REDIRECTION = "aid_redirection"
    VERIFICATION_REQUIRED = "verification_required"
    COORDINATED_FRAUD = "coordinated_fraud"


class CaseStatus(StrEnum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    AWAITING_VERIFICATION = "awaiting_verification"
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
    ACCOUNT = "account"
    CARD = "card"
    TRANSACTION = "transaction"
    SECURITY = "security"
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


# ---------------------------------------------------------------- student ID-linked financial aid


class AccountStatus(StrEnum):
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class StudyMode(StrEnum):
    """Registered study arrangement (from the student record), used to pick a verification pathway."""

    ON_CAMPUS = "on_campus"
    REMOTE_DOMESTIC = "remote_domestic"
    INTERNATIONAL = "international"


class CardStatus(StrEnum):
    ACTIVE = "active"
    REPORTED_LOST = "reported_lost"
    BLOCKED = "blocked"
    REPLACEMENT_REQUESTED = "replacement_requested"
    REPLACED = "replaced"


class TransactionStatus(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"
    PENDING = "pending"
    REVERSED = "reversed"


class TransactionReview(StrEnum):
    UNREVIEWED = "unreviewed"
    CLEARED = "cleared"
    SUSPICIOUS = "suspicious"


class DeviceTrust(StrEnum):
    TRUSTED = "trusted"
    UNFAMILIAR = "unfamiliar"
    SUSPICIOUS = "suspicious"


class SecurityEventType(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    NEW_DEVICE_LOGIN = "new_device_login"
    MFA_PASSED = "mfa_passed"
    MFA_FAILED = "mfa_failed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"  # noqa: S105
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    ACCOUNT_RECOVERY_REQUESTED = "account_recovery_requested"
    CONTACT_DETAILS_CHANGED = "contact_details_changed"
    AID_REDIRECT_REQUESTED = "aid_redirect_requested"
    CARD_REPORTED_LOST = "card_reported_lost"
    CARD_BLOCKED = "card_blocked"
    CARD_SUSPICIOUS_ACTIVITY = "card_suspicious_activity"
    CARD_REPLACEMENT_REQUESTED = "card_replacement_requested"
    CARD_REPLACED = "card_replaced"
    ACCOUNT_RESTRICTED = "account_restricted"
    ACCOUNT_RESTRICTION_LIFTED = "account_restriction_lifted"


class VerificationRequestStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFIED = "verified"
    FAILED = "failed"
    ESCALATED = "escalated"
    ADDITIONAL_INFO_REQUIRED = "additional_info_required"


class VerificationPathway(StrEnum):
    ON_CAMPUS = "on_campus"
    REMOTE = "remote"


class VerificationRequestMethod(StrEnum):
    IN_PERSON_ID_CHECK = "in_person_id_check"
    SECURE_VIDEO = "secure_video"
    GOVERNMENT_ID_DOCUMENT = "government_id_document"
    LIVENESS_PROVIDER = "liveness_provider"
    ALTERNATIVE_METHOD = "alternative_method"
    EMBASSY_ASSISTED = "embassy_assisted"


class VerificationRequestTrigger(StrEnum):
    CARD_REPORTED_LOST = "card_reported_lost"
    SUSPICIOUS_PASSWORD_RECOVERY = "suspicious_password_recovery"  # noqa: S105
    AID_REDIRECTION_ATTEMPT = "aid_redirection_attempt"
    HIGH_RISK_DEVICE = "high_risk_device"
    ACCOUNT_TAKEOVER_INDICATORS = "account_takeover_indicators"
    MULTIPLE_FRAUD_SIGNALS = "multiple_fraud_signals"
    OFFICER_REQUEST = "officer_request"
