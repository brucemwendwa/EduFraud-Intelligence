import { ArrowUpRight, CheckCheck, CircleCheckBig, CircleDot, Flag, RotateCcw, ScanFace, ThumbsDown, UserPlus, UserX } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { AlertDetail } from '@/api/types';
import { SignalList } from '@/components/risk/SignalList';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog, Drawer } from '@/components/ui/Dialog';
import { SectionTitle } from '@/components/ui/DetailList';
import { Textarea } from '@/components/ui/Field';
import { RiskBadge, RiskScoreRing, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { alertCategoryLabel, alertStatusLabel, alertStatusTone } from '@/lib/status';
import { useAlert, useAlertAction, useTriageAlert } from './api';

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

type Triage = 'acknowledge' | 'escalate' | 'resolve' | 'false_positive' | 'dismiss' | 'reopen';
const LIVE = ['open', 'acknowledged', 'verification_requested', 'escalated', 'in_investigation'];
const NOTE_COPY: Partial<Record<Triage | 'request-verification', { title: string; description: string; confirm: string; label: string; tone?: 'danger' }>> = {
  escalate: { title: 'Escalate this alert?', description: 'Escalated alerts go to senior investigators. Explain why.', confirm: 'Escalate', label: 'Reason for escalation' },
  resolve: { title: 'Resolve this alert?', description: 'Record what was found and what was done. Resolved alerts stay in the record.', confirm: 'Resolve alert', label: 'Resolution' },
  false_positive: { title: 'Record a false positive?', description: 'Explain the legitimate reason (for example travel, a new phone, study abroad). This helps tune the rules.', confirm: 'Record false positive', label: 'Legitimate explanation' },
  dismiss: { title: 'Dismiss this alert?', description: 'Dismissed alerts stay in the record. Explain what you checked.', confirm: 'Dismiss alert', label: 'Dismissal reason' },
  'request-verification': { title: 'Request identity verification?', description: "The student is notified to verify through their pathway (on campus or remote). The alert waits for the outcome.", confirm: 'Request verification', label: 'Reason shown on the request' },
};

export function AlertStatusBadge({ status }: { status: string }) {
  return <Badge tone={alertStatusTone[status] ?? 'neutral'} dot>{alertStatusLabel[status] ?? label(status)}</Badge>;
}

export function AlertDrawer({ id, onClose, extraActions }: Props) {
  const { can, user } = useAuth();
  const { data: a, isLoading, error, refetch } = useAlert(id);
  const triage = useTriageAlert();
  const act = useAlertAction(id ?? '');
  const [pending, setPending] = useState<Triage | 'request-verification' | null>(null);

  const doTriage = (action: Triage, note?: string) =>
    a &&
    triage.mutate(
      { id: a.id, action, note: note ?? null },
      {
        onSuccess: (res) => {
          toast.success(`Alert ${(alertStatusLabel[res.status] ?? res.status).toLowerCase()}`, { description: `${res.reference} · recorded in the audit trail` });
          setPending(null);
        },
        onError: (err) => toast.error('Triage failed', { description: errorMessage(err) }),
      },
    );

  const doAction = (action: 'assign' | 'notes' | 'request-verification', body: unknown, done: string) =>
    act.mutate(
      { action, body },
      {
        onSuccess: (res) => {
          toast.success(done, { description: `${res.reference} · recorded in the audit trail` });
          setPending(null);
        },
        onError: (err) => toast.error('Action failed', { description: errorMessage(err) }),
      },
    );

  const canTriage = can(P.alertsTriage);
  const live = a ? LIVE.includes(a.status) : false;
  const footer = a && (
    <>
      {canTriage && a.status === 'open' && <Button variant="secondary" icon={<CheckCheck className="size-4" />} loading={triage.isPending} onClick={() => doTriage('acknowledge')}>Start review</Button>}
      {canTriage && can(P.verificationsInitiate) && live && a.status !== 'verification_requested' && (a.account_id || a.application_id) && (
        <Button variant="secondary" icon={<ScanFace className="size-4" />} onClick={() => setPending('request-verification')}>Request verification</Button>
      )}
      {canTriage && ['open', 'acknowledged', 'verification_requested'].includes(a.status) && <Button variant="secondary" icon={<Flag className="size-4" />} onClick={() => setPending('escalate')}>Escalate</Button>}
      {canTriage && ['acknowledged', 'verification_requested', 'escalated', 'in_investigation'].includes(a.status) && <Button variant="secondary" icon={<CircleCheckBig className="size-4" />} onClick={() => setPending('resolve')}>Resolve</Button>}
      {canTriage && ['open', 'acknowledged', 'verification_requested', 'escalated'].includes(a.status) && <Button variant="ghost" icon={<ThumbsDown className="size-4" />} onClick={() => setPending('false_positive')}>False positive</Button>}
      {canTriage && ['dismissed', 'false_positive'].includes(a.status) && <Button variant="secondary" icon={<RotateCcw className="size-4" />} loading={triage.isPending} onClick={() => doTriage('reopen')}>Reopen</Button>}
      {extraActions?.(a.id, a.application_id ?? null, a.status, a.case_id ?? null, a.case_ref ?? null)}
    </>
  );

  const copy = pending ? NOTE_COPY[pending] : undefined;
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
                <AlertStatusBadge status={a.status} />
                <Badge tone="navy">{alertCategoryLabel[a.category] ?? label(a.category)}</Badge>
              </div>
              <p className="text-xs text-slate-500">Raised {dateTime(a.created_at)}{a.student ? ` · ${a.student.student_ref} (${a.student.masked_name})` : ''}</p>
              <div className="flex flex-wrap gap-3">
                {a.account_id && <Link to={`/app/accounts/${a.account_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">Account {a.account_ref} <ArrowUpRight className="size-3.5" /></Link>}
                {a.application_id && <Link to={`/app/applications/${a.application_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">Application {a.application_ref} <ArrowUpRight className="size-3.5" /></Link>}
              </div>
            </div>
          </div>

          <p className="rounded-lg bg-slate-50 p-3.5 text-sm leading-relaxed text-slate-700">{a.summary}</p>
          {(a.recommended_action || a.assessment) && (
            <div className="rounded-lg bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900 ring-1 ring-amber-100">
              <span className="font-medium">Recommended next step:</span> {a.recommended_action ?? a.assessment?.recommended_action}
            </div>
          )}

          <section className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Assigned to</span>
            <span className="font-medium text-slate-900">{a.assigned_to?.full_name ?? 'Nobody yet'}</span>
            {canTriage && live && user && a.assigned_to?.id !== user.id && (
              <Button size="sm" variant="ghost" icon={<UserPlus className="size-3.5" />} loading={act.isPending} onClick={() => doAction('assign', { assigned_to_id: user.id }, 'Assigned to you')}>Assign to me</Button>
            )}
            {canTriage && a.assigned_to && <Button size="sm" variant="ghost" icon={<UserX className="size-3.5" />} loading={act.isPending} onClick={() => doAction('assign', { assigned_to_id: null }, 'Unassigned')}>Unassign</Button>}
          </section>

          {a.assessment && (
            <section>
              <SectionTitle>Why this alert was raised</SectionTitle>
              <SignalList signals={a.assessment.signals} compact />
              <p className="mt-3 text-[11px] text-slate-500">
                {a.assessment.method} · {a.assessment.rules_version}{a.assessment.model_version && ` · ${a.assessment.model_version}`} · decision support only
              </p>
            </section>
          )}

          {(a.related.length > 0 || a.disbursement_ref || a.verification_ref || a.case_id) && (
            <section>
              <SectionTitle>Related records</SectionTitle>
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {a.related.map((r) => (
                  <li key={`${r.kind}-${r.id}`} className="flex items-center gap-3 px-3.5 py-2.5 text-sm">
                    <span className="w-28 shrink-0 text-xs text-slate-500">{label(r.kind)}</span>
                    {r.link ? <Link to={r.link} className="font-medium text-brand-blue hover:underline">{r.reference}</Link> : <span className="font-medium">{r.reference}</span>}
                    <span className="min-w-0 flex-1 truncate text-slate-600">{r.label}</span>
                    {r.status && <Badge tone="neutral">{label(r.status)}</Badge>}
                  </li>
                ))}
                {a.disbursement_ref && <li className="flex gap-3 px-3.5 py-2.5 text-sm"><span className="w-28 text-xs text-slate-500">Allocation</span>{a.disbursement_ref}</li>}
                {a.verification_ref && <li className="flex gap-3 px-3.5 py-2.5 text-sm"><span className="w-28 text-xs text-slate-500">Verification attempt</span>{a.verification_ref}</li>}
                {a.case_id && <li className="flex gap-3 px-3.5 py-2.5 text-sm"><span className="w-28 text-xs text-slate-500">Investigation</span><Link className="text-brand-blue hover:underline" to={`/app/cases/${a.case_id}`}>{a.case_ref}</Link></li>}
              </ul>
            </section>
          )}

          <Notes a={a} canAdd={canTriage} onAdd={(body) => doAction('notes', { body }, 'Note added')} pending={act.isPending} />

          <section>
            <SectionTitle>Timeline</SectionTitle>
            <ol className="space-y-2.5 border-l border-slate-200 pl-4">
              {a.timeline.map((t, i) => (
                <li key={`${t.action}-${i}`} className="relative text-sm">
                  <CircleDot className="absolute top-0.5 -left-[22px] size-3.5 bg-white text-slate-400" aria-hidden />
                  <p className="font-medium text-slate-800">{label(t.action.replace('alert.', ''))}</p>
                  <p className="text-xs text-slate-500">{dateTime(t.occurred_at)} · {t.actor ?? 'system'}{typeof t.details.note === 'string' && t.details.note ? ` · “${t.details.note}”` : ''}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
      {copy && (
        <ConfirmDialog
          open={pending !== null}
          onOpenChange={(o) => !o && setPending(null)}
          title={copy.title}
          description={copy.description}
          reasonLabel={copy.label}
          confirmLabel={copy.confirm}
          loading={triage.isPending || act.isPending}
          onConfirm={(reason) =>
            pending === 'request-verification' ? doAction('request-verification', { reason }, 'Verification requested') : pending && doTriage(pending, reason)
          }
        />
      )}
    </Drawer>
  );
}

function Notes({ a, canAdd, onAdd, pending }: { a: AlertDetail; canAdd: boolean; onAdd: (body: string) => void; pending: boolean }) {
  const [body, setBody] = useState('');
  return (
    <section>
      <SectionTitle>Investigation notes</SectionTitle>
      {a.triage_note && (
        <div className="mb-2 rounded-lg border border-slate-200 p-3 text-sm">
          <p className="text-xs text-slate-500">Last decision note · {a.triaged_by} · {dateTime(a.triaged_at)}</p>
          <p className="mt-1 text-slate-800">{a.triage_note}</p>
        </div>
      )}
      {a.notes.length === 0 ? (
        <p className="text-sm text-slate-500">No notes yet.</p>
      ) : (
        <ul className="space-y-2">
          {a.notes.map((n) => (
            <li key={n.id} className="rounded-lg bg-slate-50 p-3 text-sm">
              <p className="text-slate-800">{n.body}</p>
              <p className="mt-1 text-xs text-slate-500">{n.author ?? 'Unknown'} · {dateTime(n.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
      {canAdd && (
        <div className="mt-2 space-y-2">
          <Textarea aria-label="New note" placeholder="Add a note (append-only)…" value={body} maxLength={2000} onChange={(e) => setBody(e.target.value)} />
          <Button size="sm" variant="secondary" disabled={body.trim().length < 3} loading={pending} onClick={() => { onAdd(body.trim()); setBody(''); }}>Add note</Button>
        </div>
      )}
    </section>
  );
}
