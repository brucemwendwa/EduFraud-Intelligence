import { Building2, CalendarClock, CheckCircle2, Circle, FlaskConical, Globe2, Send, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { VerificationRequestDetail } from '@/api/types';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Drawer } from '@/components/ui/Dialog';
import { Detail, DetailList, SectionTitle } from '@/components/ui/DetailList';
import { Field, Input, Select, Textarea } from '@/components/ui/Field';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { verificationRequestTone } from '@/lib/status';
import { useVerificationOptions, useVerificationRequest, useVerificationStep } from './api';

const OPEN = ['pending', 'in_progress', 'additional_info_required', 'escalated'];
const STEP_LABELS: Record<string, string> = {
  created: 'Request created',
  linked: 'Linked to another record',
  student_notified: 'Student notified',
  appointment_scheduled: 'Visit scheduled',
  session_started: 'Verification started',
  pathway_changed: 'Pathway changed',
  documents_checked: 'Identity documents checked',
  identity_procedure_completed: 'Identity procedure completed',
  video_session_completed: 'Secure video session completed',
  alternative_method_completed: 'Alternative method completed',
  embassy_confirmation_received: 'Embassy / consulate confirmation received',
  liveness_check_completed: 'Provider liveness check (simulated)',
  decision_verified: 'Decision: identity verified',
  decision_failed: 'Decision: verification failed',
  decision_escalated: 'Decision: escalated',
  decision_additional_info_required: 'Decision: more information required',
  access_restored: 'Restricted access restored',
};
const CHECK_STEPS = ['documents_checked', 'identity_procedure_completed', 'video_session_completed', 'alternative_method_completed', 'embassy_confirmation_received'];

export function RequestDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data: r, isLoading, error, refetch } = useVerificationRequest(id);
  return (
    <Drawer
      open={Boolean(id)}
      onOpenChange={(o) => !o && onClose()}
      title={r ? `${r.reference} · ${label(r.trigger)}` : 'Verification request'}
      description={r ? `${r.student.student_ref} · ${r.organization.name}` : undefined}
      className="max-w-xl"
    >
      {isLoading ? <CardSkeleton /> : error || !r ? <ErrorState error={error} onRetry={() => refetch()} /> : <Body r={r} />}
    </Drawer>
  );
}

function Body({ r }: { r: VerificationRequestDetail }) {
  const { can } = useAuth();
  const open = OPEN.includes(r.status);
  const decide = can(P.verificationsDecide);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={r.status} map={verificationRequestTone} />
        <Badge tone="navy" icon={r.pathway === 'on_campus' ? <Building2 className="size-3" /> : <Globe2 className="size-3" />}>{label(r.pathway)} pathway</Badge>
        {r.method && <Badge tone="neutral">{label(r.method)}</Badge>}
        {r.access_restored && <Badge tone="success">Access restored</Badge>}
      </div>
      <p className="rounded-lg bg-slate-50 p-3.5 text-sm text-slate-700">{r.reason}</p>
      <DetailList>
        <Detail label="Account">{r.account_id ? <Link className="text-brand-blue hover:underline" to={`/app/accounts/${r.account_id}`}>{r.account_ref}</Link> : '—'}</Detail>
        <Detail label="Student">{r.student.student_ref} · {r.student.masked_name}</Detail>
        <Detail label="Study arrangement">{r.study_mode ? label(r.study_mode) : '—'}</Detail>
        <Detail label="Due">{dateTime(r.due_at)}</Detail>
        {r.pathway === 'on_campus' && <Detail label="Verification office" className="col-span-2">{r.location_note ?? '—'}</Detail>}
        {r.appointment_at && <Detail label="Appointment">{dateTime(r.appointment_at)}</Detail>}
        <Detail label="Assigned officer">{r.assigned_to?.full_name ?? 'Unassigned'}</Detail>
        {r.alert_ref && <Detail label="Alert"><Link className="text-brand-blue hover:underline" to={`/app/alerts?selected=${r.alert_id}`}>{r.alert_ref}</Link></Detail>}
        {r.card_ref && <Detail label="Card">{r.card_ref}</Detail>}
        <Detail label="Biometric consent">{r.biometric_consent ? 'Given' : 'Not given (non-biometric methods only)'}</Detail>
        {r.embassy_arrangement && <Detail label="Embassy arrangement" className="col-span-2">{r.embassy_arrangement}</Detail>}
      </DetailList>
      {r.outcome_reason && (
        <div className="rounded-lg border border-slate-200 p-3.5 text-sm">
          <p className="text-xs text-slate-500">Outcome · {r.decided_by ?? '—'} · {dateTime(r.decided_at)}</p>
          <p className="mt-1 text-slate-800">{r.outcome_reason}</p>
        </div>
      )}

      {open && decide && <Workflow r={r} />}
      {open && !decide && <p className="text-xs text-slate-500">A financial aid officer or administrator conducts the verification and records the outcome.</p>}

      <section>
        <SectionTitle>Timeline</SectionTitle>
        <ol className="relative space-y-4 border-l border-slate-200 pl-5">
          {r.events.map((e, i) => (
            <li key={`${e.step}-${i}`} className="relative">
              <span className="absolute top-0.5 -left-[27px] flex size-3.5 items-center justify-center rounded-full bg-white">
                {e.step.startsWith('decision') || e.step === 'access_restored' ? <CheckCircle2 className="size-3.5 text-navy-700" aria-hidden /> : <Circle className="size-3 text-slate-400" aria-hidden />}
              </span>
              <p className="text-sm font-medium text-slate-900">{STEP_LABELS[e.step] ?? label(e.step)}</p>
              <p className="text-xs text-slate-500">{dateTime(e.created_at)} · {e.actor_label}</p>
              {e.note && <p className="mt-1 text-sm text-slate-700">{e.note}</p>}
              {typeof e.details.result === 'string' && <Badge tone={e.details.result === 'pass' || e.details.result === 'passed' ? 'success' : e.details.result === 'fail' || e.details.result === 'failed' ? 'critical' : 'warning'} className="mt-1">Result: {label(e.details.result)}</Badge>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function Workflow({ r }: { r: VerificationRequestDetail }) {
  const step = useVerificationStep(r.id);
  const options = useVerificationOptions();
  const [appointment, setAppointment] = useState('');
  const [method, setMethod] = useState('');
  const [check, setCheck] = useState({ step: r.pathway === 'on_campus' ? 'documents_checked' : 'video_session_completed', result: 'pass', note: '' });
  const [sample, setSample] = useState('enrolled_student');
  const [decision, setDecision] = useState({ outcome: 'verified', reason: '', restore_access: true });

  const send = (name: string, body: unknown, success: string) =>
    step.mutate(
      { step: name, body },
      {
        onSuccess: () => toast.success(success, { description: `${r.reference} · recorded on the timeline and in the audit trail` }),
        onError: (err) => toast.error('Step not recorded', { description: errorMessage(err) }),
      },
    );

  const remoteMethods = r.methods.filter((m) => m.pathway === 'remote');
  return (
    <section className="space-y-4 rounded-xl border border-navy-100 bg-navy-50/40 p-4">
      <SectionTitle>Conduct verification</SectionTitle>
      {r.status === 'pending' && r.pathway === 'on_campus' && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label="Visit date and time" className="flex-1">
            {(id) => <Input id={id} type="datetime-local" value={appointment} onChange={(e) => setAppointment(e.target.value)} />}
          </Field>
          <Button icon={<CalendarClock className="size-4" />} disabled={!appointment} loading={step.isPending}
            onClick={() => send('schedule', { appointment_at: new Date(appointment).toISOString() }, 'Visit scheduled')}>
            Schedule visit
          </Button>
        </div>
      )}
      {r.status !== 'in_progress' && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label={r.pathway === 'on_campus' ? 'Or start a remote method (student is away)' : 'Remote method'} className="flex-1">
            {(id) => (
              <Select id={id} value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="">Choose a method…</option>
                {remoteMethods.map((m) => <option key={m.method} value={m.method} disabled={!m.available}>{m.label}{m.available ? '' : ` — ${m.reason}`}</option>)}
              </Select>
            )}
          </Field>
          <Button variant="secondary" disabled={!method} loading={step.isPending} onClick={() => send('start', { method }, 'Verification started')}>Start</Button>
        </div>
      )}
      {r.status === 'in_progress' && (
        <div className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="Step">
              {(id) => (
                <Select id={id} value={check.step} onChange={(e) => setCheck({ ...check, step: e.target.value })}>
                  {CHECK_STEPS.map((s) => <option key={s} value={s}>{STEP_LABELS[s]}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Result">
              {(id) => (
                <Select id={id} value={check.result} onChange={(e) => setCheck({ ...check, result: e.target.value })}>
                  <option value="pass">Pass</option><option value="fail">Fail</option><option value="inconclusive">Inconclusive</option>
                </Select>
              )}
            </Field>
          </div>
          <Field label="What was checked">
            {(id) => <Textarea id={id} value={check.note} maxLength={500} placeholder="e.g. Photo ID inspected; matches the student record" onChange={(e) => setCheck({ ...check, note: e.target.value })} />}
          </Field>
          <Button variant="secondary" disabled={check.note.trim().length < 5} loading={step.isPending} onClick={() => send('checks', { ...check, note: check.note.trim() }, 'Step recorded')}>Record step</Button>
        </div>
      )}
      {r.status === 'in_progress' && r.method === 'liveness_provider' && (
        <div className="flex flex-col gap-2 rounded-lg bg-blue-50 p-3 ring-1 ring-blue-100 sm:flex-row sm:items-end">
          <Field label={<span className="inline-flex items-center gap-1"><FlaskConical className="size-3" />Simulated test sample (no camera or images)</span>} className="flex-1">
            {(id) => (
              <Select id={id} value={sample} onChange={(e) => setSample(e.target.value)}>
                {(options.data?.simulated_samples ?? []).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </Select>
            )}
          </Field>
          <Button variant="secondary" loading={step.isPending} onClick={() => send('liveness', { sample_key: sample }, 'Simulated liveness check completed')}>Run simulated check</Button>
        </div>
      )}
      <div className="space-y-2 border-t border-navy-100 pt-4">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Outcome">
            {(id) => (
              <Select id={id} value={decision.outcome} onChange={(e) => setDecision({ ...decision, outcome: e.target.value })}>
                <option value="verified">Verified</option>
                <option value="failed">Failed</option>
                <option value="escalated">Escalate to investigator</option>
                <option value="additional_info_required">Additional information required</option>
              </Select>
            )}
          </Field>
          {decision.outcome === 'verified' && (
            <label className="flex items-center gap-2 self-end pb-2 text-sm text-slate-700">
              <input type="checkbox" className="size-4 rounded border-slate-300" checked={decision.restore_access} onChange={(e) => setDecision({ ...decision, restore_access: e.target.checked })} />
              Restore restricted access
            </label>
          )}
        </div>
        <Field label="Documented reason" hint="Minimum 10 characters. Required for every outcome.">
          {(id, describedBy) => <Textarea id={id} aria-describedby={describedBy} value={decision.reason} maxLength={1000} onChange={(e) => setDecision({ ...decision, reason: e.target.value })} />}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button icon={<UserCheck className="size-4" />} disabled={decision.reason.trim().length < 10} loading={step.isPending}
            onClick={() => send('decision', { ...decision, reason: decision.reason.trim() }, `Outcome recorded: ${label(decision.outcome)}`)}>
            Record outcome
          </Button>
          <Button variant="ghost" icon={<Send className="size-4" />} loading={step.isPending} onClick={() => send('notify', undefined, 'Notice re-sent (simulated)')}>Re-send notice</Button>
        </div>
      </div>
    </section>
  );
}
