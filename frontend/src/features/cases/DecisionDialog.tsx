import { Scale } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import type { CaseDecisionIn, CaseDetail } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Textarea } from '@/components/ui/Field';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { findingMeta } from '@/lib/status';
import { useDecision } from './api';

type Decision = CaseDecisionIn['decision'];
type Outcome = NonNullable<CaseDecisionIn['outcome']>;

const DECISIONS: Record<Decision, { label: string; body: string; finding?: string }> = {
  escalate: { label: 'Escalate', body: 'The evidence warrants treating this as suspected fraud.', finding: 'suspected_fraud' },
  resolve: { label: 'Resolve', body: 'Record the outcome of the investigation.' },
  reopen: { label: 'Reopen', body: 'New information means the case needs more review.', finding: 'suspicious_activity' },
  close: { label: 'Close', body: 'The resolution has been acted on; nothing further is required.' },
};

export const OUTCOMES: Record<Outcome, { label: string; body: string; finding: string }> = {
  no_fraud_found: { label: 'No fraud found', body: 'The activity is explained. No adverse finding about the student.', finding: 'not_substantiated' },
  insufficient_evidence: { label: 'Insufficient evidence', body: 'Fraud cannot be established. No adverse finding is recorded.', finding: 'not_substantiated' },
  referred_externally: { label: 'Refer for external review', body: 'Suspected, not established. Compliance or another authority decides.', finding: 'suspected_fraud' },
  confirmed_fraud: { label: 'Confirmed fraud', body: 'Needs attached evidence and a detailed justification. Aid actions still follow institutional due process.', finding: 'confirmed_fraud' },
};

export function allowedDecisions(status: string): Decision[] {
  if (status === 'new' || status === 'under_review') return ['escalate', 'resolve'];
  if (status === 'escalated') return ['resolve'];
  if (status === 'resolved') return ['reopen', 'close'];
  return [];
}

interface Props {
  c: CaseDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** A justified human decision. The AI's score informs it; it never makes it. */
export function DecisionDialog({ c, open, onOpenChange }: Props) {
  const { user } = useAuth();
  const options = allowedDecisions(c.status);
  const [decision, setDecision] = useState<Decision>(options[0] ?? 'resolve');
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [justification, setJustification] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const mutation = useDecision(c.id);

  const effective = options.includes(decision) ? decision : options[0]!;
  const minLength = effective === 'resolve' && outcome === 'confirmed_fraud' ? 50 : 20;
  const finding = effective === 'resolve' ? (outcome ? OUTCOMES[outcome].finding : null) : (DECISIONS[effective].finding ?? c.finding);
  const valid = justification.trim().length >= minLength && acknowledged && (effective !== 'resolve' || outcome !== null);

  const reset = () => {
    setOutcome(null);
    setJustification('');
    setAcknowledged(false);
  };

  const submit = () =>
    mutation.mutate(
      { decision: effective, outcome: effective === 'resolve' ? outcome : null, justification: justification.trim(), acknowledged },
      {
        onSuccess: (res) => {
          toast.success(`Decision recorded on ${res.reference}`, {
            description: `${findingMeta[res.finding]?.label ?? res.finding} · status ${res.status.replace('_', ' ')}`,
          });
          reset();
          onOpenChange(false);
        },
        onError: (err) => toast.error('Decision not recorded', { description: errorMessage(err) }),
      },
    );

  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
      size="lg"
      title={`Record a decision · ${c.reference}`}
      description="Decisions are made by people. Your name, the time and your justification are stored with the case and in the audit trail."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>Cancel</Button>
          <Button onClick={submit} loading={mutation.isPending} disabled={!valid} icon={<Scale className="size-4" />}>
            Record decision
          </Button>
        </>
      }
    >
      {options.length === 0 ? (
        <p className="text-sm text-slate-600">No further decisions are possible on a {c.status} case.</p>
      ) : (
        <div className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-slate-900">Decision</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {options.map((d) => (
                <Choice key={d} selected={effective === d} onClick={() => setDecision(d)} title={DECISIONS[d].label} body={DECISIONS[d].body} />
              ))}
            </div>
          </fieldset>

          {effective === 'resolve' && (
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-slate-900">Outcome</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {(Object.keys(OUTCOMES) as Outcome[]).map((o) => {
                  const blocked = o === 'confirmed_fraud' && c.evidence.length === 0;
                  return (
                    <Choice
                      key={o}
                      selected={outcome === o}
                      disabled={blocked}
                      onClick={() => setOutcome(o)}
                      title={OUTCOMES[o].label}
                      body={blocked ? 'Attach supporting evidence first.' : OUTCOMES[o].body}
                    />
                  );
                })}
              </div>
            </fieldset>
          )}

          <Field
            label="Justification"
            hint={`At least ${minLength} characters. Describe what you checked and why you reached this decision.`}
          >
            {(id, d) => (
              <>
                <Textarea id={id} aria-describedby={d} value={justification} maxLength={5000} onChange={(e) => setJustification(e.target.value)} />
                <p className={cn('tabular text-right text-[11px]', justification.trim().length >= minLength ? 'text-green-700' : 'text-slate-400')}>
                  {justification.trim().length}/{minLength}
                </p>
              </>
            )}
          </Field>

          <label className="flex items-start gap-2.5 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            <input type="checkbox" className="mt-0.5 size-4 accent-navy-900" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
            <span>
              I reviewed the evidence on this case. This is my decision. The risk score and alerts are inputs to it, not findings.
            </span>
          </label>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
            <span>
              Recorded as <span className="font-medium text-slate-700">{user?.full_name}</span> · {new Date().toLocaleString()}
            </span>
            {finding && (
              <span className="flex items-center gap-1.5">
                Finding after this decision
                <Badge tone={findingMeta[finding]?.tone ?? 'neutral'}>{findingMeta[finding]?.label ?? finding}</Badge>
              </span>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function Choice({ selected, onClick, title, body, disabled }: { selected: boolean; onClick: () => void; title: string; body: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        'rounded-lg border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        selected ? 'border-navy-900 bg-navy-50/60 ring-1 ring-navy-900' : 'border-slate-200 hover:border-slate-300',
      )}
    >
      <p className="text-sm font-medium text-slate-900">{title}</p>
      <p className="mt-0.5 text-xs text-slate-600">{body}</p>
    </button>
  );
}
