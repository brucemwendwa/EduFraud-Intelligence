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
  in_investigation: 'blue',
  dismissed: 'neutral',
  resolved: 'success',
};

export const caseStatusTone: Record<string, Tone> = {
  new: 'blue',
  under_review: 'violet',
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
