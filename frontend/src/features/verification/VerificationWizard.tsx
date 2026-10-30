import { useQuery } from '@tanstack/react-query';
import { Check, Fingerprint, FlaskConical, ShieldCheck, UserRound } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import type { ApplicationDetail, ApplicationRow, Page, Verification } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Select, Textarea } from '@/components/ui/Field';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { Spinner } from '@/components/ui/Spinner';
import { api, errorMessage } from '@/lib/api';
import { cn } from '@/lib/cn';
import { label } from '@/lib/format';
import { useProviderInfo, useRecordAlternative, useRunBiometric } from './api';
import { VerificationResult } from './VerificationResult';

const TRIGGERS: Record<string, string> = {
  payment_destination_change: 'Someone asked to change where refunds are paid',
  account_recovery: 'Password reset or account recovery request',
  new_device_login: 'Sign-in from an unrecognised device',
  pre_disbursement: 'Routine check before funds are released',
  risk_review: 'Requested by staff during a risk review',
};

const STEPS = ['Subject', 'Context', 'Verify', 'Result'];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-selects the application (wizard opened from an application). */
  applicationId?: string;
}

export function VerificationWizard({ open, onOpenChange, applicationId }: Props) {
  const [step, setStep] = useState(applicationId ? 1 : 0);
  const [appId, setAppId] = useState<string | null>(applicationId ?? null);
  const [trigger, setTrigger] = useState('payment_destination_change');
  const [mode, setMode] = useState<'biometric' | 'alternative'>('biometric');
  const [sample, setSample] = useState('enrolled_student');
  const [altMethod, setAltMethod] = useState<'in_person_id_check' | 'officer_video_call' | 'mailed_code'>('in_person_id_check');
  const [altOutcome, setAltOutcome] = useState<'passed' | 'failed'>('passed');
  const [notes, setNotes] = useState('');
  const [result, setResult] = useState<Verification | null>(null);
  const provider = useProviderInfo();
  const biometric = useRunBiometric();
  const alternative = useRecordAlternative();

  const subject = useQuery({
    queryKey: ['applications', 'detail', appId],
    queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${appId}`)).data,
    enabled: Boolean(appId) && open,
  });
  const consent = subject.data?.student_detail.biometric_consent ?? false;
  const effectiveMode = consent ? mode : 'alternative';

  const reset = () => {
    setStep(applicationId ? 1 : 0);
    setAppId(applicationId ?? null);
    setResult(null);
    setNotes('');
    setMode('biometric');
  };

  const submit = () => {
    if (!appId) return;
    const onSuccess = (v: Verification) => {
      setResult(v);
      setStep(3);
      if (v.status === 'failed') toast.error('Verification failed', { description: `${v.reference}: risk re-assessed and alert updated.` });
      else toast.success(`Verification ${label(v.status).toLowerCase()}`, { description: v.reference });
    };
    const onError = (err: unknown) => toast.error('Verification could not run', { description: errorMessage(err) });
    if (effectiveMode === 'biometric') {
      biometric.mutate({ application_id: appId, trigger: trigger as never, sample_key: sample }, { onSuccess, onError });
    } else {
      alternative.mutate(
        { application_id: appId, trigger: trigger as never, method: altMethod, outcome: altOutcome, notes: notes.trim() },
        { onSuccess, onError },
      );
    }
  };

  const pending = biometric.isPending || alternative.isPending;
  const canNext =
    (step === 0 && Boolean(appId)) ||
    step === 1 ||
    (step === 2 && (effectiveMode === 'biometric' || notes.trim().length >= 10));

  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
      size="lg"
      title="Identity verification"
      description="Step-up verification for a claimed student identity."
      footer={
        step === 3 ? (
          <>
            <Button variant="secondary" onClick={reset}>Verify another</Button>
            <Button onClick={() => { reset(); onOpenChange(false); }}>Done</Button>
          </>
        ) : (
          <>
            {step > (applicationId ? 1 : 0) && <Button variant="secondary" onClick={() => setStep((s) => s - 1)} disabled={pending}>Back</Button>}
            {step < 2 ? (
              <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Continue</Button>
            ) : (
              <Button onClick={submit} loading={pending} disabled={!canNext} icon={<Fingerprint className="size-4" />}>
                {effectiveMode === 'biometric' ? 'Run verification' : 'Record outcome'}
              </Button>
            )}
          </>
        )
      }
    >
      <div className="mb-5 flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-800 ring-1 ring-blue-100">
        <FlaskConical className="size-4 shrink-0" aria-hidden />
        Simulated provider: no camera and no images. Choose a synthetic test sample to see how each attack is handled.
      </div>
      <ol className="mb-6 flex items-center gap-2" aria-label="Progress">
        {STEPS.map((name, i) => (
          <li key={name} className="flex flex-1 items-center gap-2">
            <span
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                i < step ? 'bg-navy-900 text-white' : i === step ? 'bg-navy-100 text-navy-900 ring-2 ring-navy-900' : 'bg-slate-100 text-slate-500',
              )}
              aria-current={i === step ? 'step' : undefined}
            >
              {i < step ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={cn('hidden text-xs font-medium sm:inline', i === step ? 'text-slate-900' : 'text-slate-500')}>{name}</span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-slate-200" aria-hidden />}
          </li>
        ))}
      </ol>

      {step === 0 && <SubjectPicker selected={appId} onSelect={setAppId} />}

      {step >= 1 && step < 3 && subject.data && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3.5 py-3">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-full bg-navy-50 text-navy-700"><UserRound className="size-4" /></span>
            <div>
              <p className="text-sm font-medium text-slate-900">Claimed identity: {subject.data.student.masked_name}</p>
              <p className="font-mono text-xs text-slate-500">{subject.data.student.student_ref} · {subject.data.reference}</p>
            </div>
          </div>
          {consent ? (
            <Badge tone="success" icon={<Fingerprint className="size-3" />}>Biometric consent on file</Badge>
          ) : (
            <Badge tone="neutral" icon={<ShieldCheck className="size-3" />}>No biometric consent</Badge>
          )}
        </div>
      )}
      {step >= 1 && step < 3 && subject.isLoading && <Spinner className="size-5 text-navy-700" />}

      {step === 1 && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-900">Why is verification needed?</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(TRIGGERS).map(([key, text]) => (
              <OptionCard key={key} selected={trigger === key} onClick={() => setTrigger(key)} title={label(key)} body={text} />
            ))}
          </div>
        </fieldset>
      )}

      {step === 2 && (
        <div className="space-y-4">
          {consent && (
            <div className="inline-flex rounded-lg bg-slate-100 p-1" role="tablist">
              {(['biometric', 'alternative'] as const).map((m) => (
                <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
                  className={cn('rounded-md px-3 py-1.5 text-sm font-medium', mode === m ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600')}>
                  {m === 'biometric' ? 'Biometric (simulated)' : 'Alternative method'}
                </button>
              ))}
            </div>
          )}
          {!consent && (
            <p className="rounded-lg bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700">
              This student has not consented to biometric checks. Verify them with an alternative method and record the outcome.
            </p>
          )}
          {effectiveMode === 'biometric' ? (
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-slate-900">Synthetic test sample presented</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {provider.data?.samples.map((s) => (
                  <OptionCard key={s.key} selected={sample === s.key} onClick={() => setSample(s.key)} title={s.label} body={s.description} tag={s.expected} />
                ))}
              </div>
            </fieldset>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Method">
                {(id) => (
                  <Select id={id} value={altMethod} onChange={(e) => setAltMethod(e.target.value as typeof altMethod)}>
                    <option value="in_person_id_check">In-person photo ID check</option>
                    <option value="officer_video_call">Officer video call</option>
                    <option value="mailed_code">Code mailed to address on file</option>
                  </Select>
                )}
              </Field>
              <Field label="Outcome">
                {(id) => (
                  <Select id={id} value={altOutcome} onChange={(e) => setAltOutcome(e.target.value as typeof altOutcome)}>
                    <option value="passed">Identity confirmed</option>
                    <option value="failed">Identity not confirmed</option>
                  </Select>
                )}
              </Field>
              <Field label="What did you check?" hint="Minimum 10 characters. Stored with the verification and the audit trail." className="sm:col-span-2">
                {(id, d) => <Textarea id={id} aria-describedby={d} value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} />}
              </Field>
            </div>
          )}
        </div>
      )}

      {step === 3 && result && <VerificationResult v={result} animate />}
    </Modal>
  );
}

function OptionCard({ selected, onClick, title, body, tag }: { selected: boolean; onClick: () => void; title: string; body: string; tag?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'rounded-lg border p-3 text-left transition-colors',
        selected ? 'border-navy-900 bg-navy-50/60 ring-1 ring-navy-900' : 'border-slate-200 hover:border-slate-300',
      )}
    >
      <p className="text-sm font-medium text-slate-900">{title}</p>
      <p className="mt-0.5 text-xs text-slate-600">{body}</p>
      {tag && <p className="mt-1.5 text-[11px] font-medium text-slate-500">Expected: {tag}</p>}
    </button>
  );
}

function SubjectPicker({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const [q, setQ] = useState('');
  const results = useQuery({
    queryKey: ['applications', 'list', { q, page_size: '6', sort: 'risk_score' }],
    queryFn: async () => (await api.get<Page<ApplicationRow>>('/applications', { params: { q, page_size: 6, sort: 'risk_score' } })).data,
  });
  return (
    <div className="space-y-3">
      <SearchInput label="Find application" placeholder="Search FA- or STU- reference" value={q} onChange={setQ} />
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {results.isLoading && <li className="px-3.5 py-3"><Spinner /></li>}
        {results.data?.items.map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => onSelect(a.id)} aria-pressed={selected === a.id}
              className={cn('flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-sm', selected === a.id ? 'bg-navy-50' : 'hover:bg-slate-50')}>
              <span>
                <span className="font-medium text-slate-900">{a.reference}</span>
                <span className="ml-2 font-mono text-xs text-slate-500">{a.student.student_ref} · {a.student.masked_name}</span>
              </span>
              <RiskBadge level={a.risk_level as RiskLevel | null} score={a.risk_score} />
            </button>
          </li>
        ))}
        {results.data && results.data.items.length === 0 && <li className="px-3.5 py-3 text-sm text-slate-500">No applications found.</li>}
      </ul>
    </div>
  );
}
