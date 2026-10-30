import { ArrowUpRight, CheckCheck, RotateCcw, XCircle } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { SignalList } from '@/components/risk/SignalList';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog, Drawer } from '@/components/ui/Dialog';
import { RiskBadge, RiskScoreRing, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { alertStatusTone } from '@/lib/status';
import { useAlert, useTriageAlert } from './api';

interface Props {
  id: string | null;
  onClose: () => void;
  /** Extra actions (e.g. "Open investigation") supplied by the caller. */
  extraActions?: (
    alertId: string,
    applicationId: string | null,
    status: string,
    caseId: string | null,
    caseRef: string | null,
  ) => ReactNode;
}

export function AlertDrawer({ id, onClose, extraActions }: Props) {
  const { can } = useAuth();
  const { data: a, isLoading, error, refetch } = useAlert(id);
  const triage = useTriageAlert();
  const [dismissing, setDismissing] = useState(false);

  const act = (action: 'acknowledge' | 'dismiss' | 'reopen', note?: string) =>
    a &&
    triage.mutate(
      { id: a.id, action, note: note ?? null },
      {
        onSuccess: (res) => {
          toast.success(`Alert ${label(res.status).toLowerCase()}`, { description: `${res.reference} · recorded in the audit trail` });
          setDismissing(false);
        },
        onError: (err) => toast.error('Triage failed', { description: errorMessage(err) }),
      },
    );

  const canTriage = can(P.alertsTriage);
  const footer = a && (
    <>
      {canTriage && a.status === 'open' && (
        <Button variant="secondary" icon={<CheckCheck className="size-4" />} loading={triage.isPending} onClick={() => act('acknowledge')}>
          Acknowledge
        </Button>
      )}
      {canTriage && (a.status === 'open' || a.status === 'acknowledged') && (
        <Button variant="secondary" icon={<XCircle className="size-4" />} onClick={() => setDismissing(true)}>Dismiss</Button>
      )}
      {canTriage && a.status === 'dismissed' && (
        <Button variant="secondary" icon={<RotateCcw className="size-4" />} loading={triage.isPending} onClick={() => act('reopen')}>Reopen</Button>
      )}
      {extraActions?.(a.id, a.application_id ?? null, a.status, a.case_id ?? null, a.case_ref ?? null)}
    </>
  );

  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={a?.title ?? 'Alert'} description={a ? `${a.reference} · ${a.organization.name}` : undefined} footer={footer} className="max-w-xl">
      {isLoading ? (
        <CardSkeleton />
      ) : error || !a ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            {a.risk_score != null && <RiskScoreRing score={a.risk_score} level={a.severity as RiskLevel} size={80} />}
            <div className="space-y-1.5">
              <div className="flex flex-wrap gap-1.5">
                <RiskBadge level={a.severity as RiskLevel} />
                <StatusBadge value={a.status} map={alertStatusTone} />
              </div>
              <p className="text-xs text-slate-500">Raised {dateTime(a.created_at)} · {label(a.category)}</p>
              {a.application_id && (
                <Link to={`/app/applications/${a.application_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">
                  Open application {a.application_ref} <ArrowUpRight className="size-3.5" />
                </Link>
              )}
            </div>
          </div>

          <p className="rounded-lg bg-slate-50 p-3.5 text-sm leading-relaxed text-slate-700">{a.summary}</p>

          {a.assessment && (
            <>
              <div className="rounded-lg bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900 ring-1 ring-amber-100">
                <span className="font-medium">Recommended:</span> {a.assessment.recommended_action}
              </div>
              <section>
                <h3 className="mb-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">Why this alert was raised</h3>
                <SignalList signals={a.assessment.signals} compact />
                <p className="mt-3 text-[11px] text-slate-500">
                  {a.assessment.method} · {a.assessment.rules_version}
                  {a.assessment.model_version && ` · ${a.assessment.model_version}`}
                </p>
              </section>
            </>
          )}

          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Item label="Student">{a.student ? <span className="font-mono text-xs">{a.student.student_ref}</span> : '—'}</Item>
            <Item label="Linked disbursement">{a.disbursement_ref ?? '—'}</Item>
            <Item label="Linked verification">{a.verification_ref ?? '—'}</Item>
            <Item label="Investigation">{a.case_id ? <Link className="text-brand-blue hover:underline" to={`/app/cases/${a.case_id}`}>{a.case_ref}</Link> : '—'}</Item>
          </dl>

          {a.triage_note && (
            <div className="rounded-lg border border-slate-200 p-3.5 text-sm">
              <p className="text-xs text-slate-500">Triage note · {a.triaged_by} · {dateTime(a.triaged_at)}</p>
              <p className="mt-1 text-slate-800">{a.triage_note}</p>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={dismissing}
        onOpenChange={setDismissing}
        title="Dismiss this alert?"
        description="Dismissed alerts stay in the record. Explain what you checked."
        reasonLabel="Dismissal reason"
        confirmLabel="Dismiss alert"
        loading={triage.isPending}
        onConfirm={(reason) => act('dismiss', reason)}
      />
    </Drawer>
  );
}

function Item({ label: name, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{name}</dt>
      <dd className="mt-0.5 text-slate-800">{children}</dd>
    </div>
  );
}
