import type { Tone } from '@/components/ui/Badge';

export const applicationStatusTone: Record<string, Tone> = {
  received: 'neutral',
  in_review: 'blue',
  approved: 'success',
  on_hold: 'warning',
  withdrawn: 'neutral',
};

export const reviewStatusTone: Record<string, Tone> = {
  unreviewed: 'neutral',
  in_review: 'blue',
  cleared: 'success',
  escalated: 'critical',
};

export const verificationStatusTone: Record<string, Tone> = {
  not_required: 'neutral',
  pending: 'blue',
  passed: 'success',
  failed: 'critical',
  manual_review: 'warning',
  review: 'warning',
};

export const disbursementStatusTone: Record<string, Tone> = {
  scheduled: 'blue',
  released: 'success',
  held: 'warning',
  reversed: 'critical',
};

export const enrollmentStatusTone: Record<string, Tone> = {
  enrolled: 'success',
  completed: 'navy',
  withdrawn: 'neutral',
  never_attended: 'critical',
};

export const alertStatusTone: Record<string, Tone> = {
  open: 'critical',
  acknowledged: 'warning',
  verification_requested: 'violet',
  escalated: 'high',
  in_investigation: 'blue',
  dismissed: 'neutral',
  false_positive: 'neutral',
  resolved: 'success',
};

/** Product vocabulary for alert statuses (stored values predate the account-protection module). */
export const alertStatusLabel: Record<string, string> = {
  open: 'New',
  acknowledged: 'Under review',
  verification_requested: 'Verification requested',
  escalated: 'Escalated',
  in_investigation: 'In investigation',
  dismissed: 'Dismissed',
  false_positive: 'False positive',
  resolved: 'Resolved',
};

export const alertCategoryLabel: Record<string, string> = {
  lost_stolen_card: 'Lost or stolen card',
  suspicious_login: 'Suspicious login',
  new_device: 'New device',
  password_reset: 'Password reset',
  account_takeover: 'Account takeover',
  unusual_transaction: 'Unusual transaction',
  suspicious_location: 'Suspicious location',
  aid_redirection: 'Financial aid redirection',
  verification_required: 'Identity verification required',
  coordinated_fraud: 'Coordinated fraud pattern',
  biometric: 'Biometric check failed',
  identity: 'Identity conflict',
  network: 'Linked network',
  disbursement: 'Disbursement',
  enrollment: 'Enrollment',
  application: 'Application',
  anomaly: 'Anomaly',
};

export const caseStatusTone: Record<string, Tone> = {
  new: 'blue',
  under_review: 'violet',
  awaiting_verification: 'warning',
  escalated: 'critical',
  resolved: 'success',
  closed: 'neutral',
};

/** Documented demonstration scenarios (see docs/demo-script.md). */
export const scenarioLabels: Record<string, string> = {
  identity_impersonation: 'Identity impersonation',
  duplicate_identity: 'Duplicate identity',
  shared_destination: 'Shared payment destination',
  unusual_disbursement: 'Unusual disbursement',
  coordinated_network: 'Coordinated network',
  control_siblings: 'Control · siblings',
  control_dorm: 'Control · residence hall',
  control_transfer: 'Control · transfer student',
  control_bank_change: 'Control · verified bank change',
  control_high_need: 'Control · high-need student',
  lost_card: 'Lost student ID card',
  password_reset: 'Suspicious password reset',
  account_takeover: 'Account takeover',
  suspicious_transaction: 'Suspicious transaction',
  coordinated_ring: 'Coordinated account ring',
  control_new_phone: 'Control · new phone',
  control_travel: 'Control · weekend trip',
  control_forgot_password: 'Control · forgotten password',
  control_study_abroad: 'Control · international student',
  control_saver: 'Control · saving aid',
};

export const isControlScenario = (key: string | null | undefined) => Boolean(key?.startsWith('control_'));

export const priorityTone: Record<string, Tone> = {
  low: 'neutral',
  medium: 'blue',
  high: 'high',
  urgent: 'critical',
};

/** What people have established about a case. Distinct from the AI's risk level, and only changed by a decision. */
export const findingMeta: Record<string, { label: string; tone: Tone; help: string }> = {
  suspicious_activity: {
    label: 'Suspicious activity',
    tone: 'warning',
    help: 'Raised by detection signals. Nothing has been established yet.',
  },
  suspected_fraud: {
    label: 'Suspected fraud',
    tone: 'high',
    help: 'An investigator judged the evidence serious enough to escalate or refer. Not a finding.',
  },
  confirmed_fraud: {
    label: 'Confirmed finding',
    tone: 'critical',
    help: 'An investigator recorded a confirmed finding with supporting evidence and justification.',
  },
  not_substantiated: {
    label: 'Not substantiated',
    tone: 'success',
    help: 'The investigation did not establish fraud. No adverse finding about the student.',
  },
};

export const accountStatusTone: Record<string, Tone> = {
  active: 'success',
  pending_verification: 'blue',
  restricted: 'warning',
  suspended: 'critical',
  closed: 'neutral',
};

export const cardStatusTone: Record<string, Tone> = {
  active: 'success',
  reported_lost: 'warning',
  blocked: 'critical',
  replacement_requested: 'blue',
  replaced: 'neutral',
};

export const transactionStatusTone: Record<string, Tone> = {
  approved: 'success',
  pending: 'blue',
  declined: 'critical',
  reversed: 'neutral',
};

export const transactionReviewTone: Record<string, Tone> = {
  unreviewed: 'neutral',
  cleared: 'success',
  suspicious: 'critical',
};

export const deviceTrustTone: Record<string, Tone> = {
  trusted: 'success',
  unfamiliar: 'warning',
  suspicious: 'critical',
};

export const verificationRequestTone: Record<string, Tone> = {
  not_required: 'neutral',
  pending: 'blue',
  in_progress: 'violet',
  verified: 'success',
  failed: 'critical',
  escalated: 'high',
  additional_info_required: 'warning',
};

export const decisionTone: Record<string, Tone> = { allow: 'success', step_up: 'warning', hold: 'critical' };

export const securityEventLabel: Record<string, string> = {
  login_success: 'Sign-in',
  login_failed: 'Failed sign-in',
  new_device_login: 'Sign-in from a new device',
  mfa_passed: 'Additional authentication passed',
  mfa_failed: 'Additional authentication failed',
  password_reset_requested: 'Password reset requested',
  password_changed: 'Password changed',
  account_recovery_requested: 'Account recovery requested',
  contact_details_changed: 'Recovery contact changed',
  aid_redirect_requested: 'Aid redirection requested',
  card_reported_lost: 'Card reported lost',
  card_blocked: 'Card blocked at provider',
  card_suspicious_activity: 'Suspicious card activity recorded',
  card_replacement_requested: 'Card replacement requested',
  card_replaced: 'Replacement card issued',
  account_restricted: 'Sensitive actions restricted',
  account_restriction_lifted: 'Restriction lifted',
};

export const studyModeLabel: Record<string, string> = {
  on_campus: 'On campus',
  remote_domestic: 'Remote (domestic)',
  international: 'International (remote)',
};
