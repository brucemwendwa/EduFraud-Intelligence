import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import type { StudentApplication, StudentApplicationDraft } from '@/api/types';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Field, Input, Select, Textarea } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorState } from '@/components/ui/States';
import { Spinner } from '@/components/ui/Spinner';
import { StudentDocumentPanel } from '@/features/documents/StudentDocumentPanel';
import { ApiError, errorMessage } from '@/lib/api';
import { dateTime, label } from '@/lib/format';
import { applicationStatusTone } from '@/lib/status';
import { useStudentApplication, useStudentApplicationActions } from './studentApplications';

/** Adds the names of the affected fields to the API's message. */
function problemText(err: unknown): string {
  const message = errorMessage(err);
  if (err instanceof ApiError && Array.isArray(err.details)) {
    const fields = (err.details as { field?: string }[]).map((d) => d.field?.replaceAll('_', ' ')).filter(Boolean);
    if (fields.length > 0) return `${message} Check: ${fields.join(', ')}.`;
  }
  return message;
}

function readForm(form: HTMLFormElement): StudentApplicationDraft {
  const fields = new FormData(form);
  const text = (name: string) => String(fields.get(name) ?? '').trim() || null;
  const aidIndex = text('student_aid_index');
  return {
    award_year: text('award_year'),
    dependency_status: text('dependency_status') as StudentApplicationDraft['dependency_status'],
    enrollment_intensity: text('enrollment_intensity') as StudentApplicationDraft['enrollment_intensity'],
    program: text('program'),
    requested_amount: text('requested_amount'),
    student_aid_index: aidIndex === null ? null : Number(aidIndex),
  };
}

function StatusNotice({ app }: { app: StudentApplication }) {
  const message = app.status_message;
  if (app.status === 'additional_information_required') {
    return (
      <Notice tone="amber" icon={<AlertTriangle className="size-5" aria-hidden />} title="Your financial aid office needs more information">
        <p>{message?.message ?? 'Contact your financial aid office for details.'}</p>
        <p className="mt-1 text-xs">Update your details or upload documents below, then resubmit.</p>
      </Notice>
    );
  }
  if (app.status === 'approved') {
    return (
      <Notice tone="green" icon={<CheckCircle2 className="size-5" aria-hidden />} title="Your application was approved">
        {message?.message && <p>{message.message}</p>}
      </Notice>
    );
  }
  if (app.status === 'rejected') {
    return (
      <Notice tone="red" icon={<XCircle className="size-5" aria-hidden />} title="Your application was not approved">
        {message?.message && <p>{message.message}</p>}
        <p className="mt-1 text-xs">Contact your financial aid office if you have questions about this decision.</p>
      </Notice>
    );
  }
  return null;
}

const noticeTones = {
  amber: 'border-amber-200 bg-amber-50 text-amber-900',
  green: 'border-green-200 bg-green-50 text-green-900',
  red: 'border-red-200 bg-red-50 text-red-900',
};

function Notice({ tone, icon, title, children }: { tone: keyof typeof noticeTones; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className={`mt-6 flex gap-3 rounded-xl border p-4 text-sm ${noticeTones[tone]}`}>
      <span className="shrink-0">{icon}</span>
      <div><h2 className="font-semibold">{title}</h2><div className="mt-1">{children}</div></div>
    </section>
  );
}

export default function StudentApplicationPage() {
  const { id } = useParams();
  const creating = id === 'new';
  const navigate = useNavigate();
  const query = useStudentApplication(creating ? undefined : id);
  const actions = useStudentApplicationActions();
  const formRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [responseNote, setResponseNote] = useState('');
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);

  if (!creating && query.isLoading) return <main className="flex justify-center py-16"><Spinner label="Loading application" className="size-6" /></main>;
  if (!creating && !query.data) return <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6"><ErrorState title="Application unavailable" error={query.error} onRetry={() => void query.refetch()} /></main>;

  const app = creating ? undefined : query.data;
  const disabled = Boolean(app && !app.is_editable);
  const responding = app?.status === 'additional_information_required';
  const saving = actions.create.isPending || actions.save.isPending;

  /** Saves the form. A new draft moves to its own URL immediately, so a later failure cannot create a duplicate. */
  const persist = async (): Promise<StudentApplication> => {
    const body = readForm(formRef.current!);
    if (app) return actions.save.mutateAsync({ id: app.id, body });
    const created = await actions.create.mutateAsync(body);
    navigate(`/student/applications/${created.id}`, { replace: true });
    return created;
  };

  const saveDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await persist();
      toast.success(creating ? 'Draft created' : 'Draft saved');
    } catch (err) {
      setError(problemText(err));
    }
  };

  const submit = async () => {
    setError(null);
    try {
      const saved = await persist();
      await actions.submit.mutateAsync({ id: saved.id, responseNote: responseNote.trim() });
      setResponseNote('');
      toast.success(responding ? 'Application resubmitted' : 'Application submitted');
    } catch (err) {
      setError(problemText(err));
    }
  };

  const withdraw = async () => {
    if (!app) return;
    setError(null);
    try {
      await actions.withdraw.mutateAsync(app.id);
      toast.success('Application withdrawn');
    } catch (err) {
      setError(problemText(err));
    } finally {
      setConfirmWithdraw(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader
        title={creating ? 'New financial aid application' : app?.reference ?? 'Application'}
        description={creating ? 'Save a draft at any time. Required fields are checked when you submit.' : app?.program ?? undefined}
        actions={<Link to="/student/applications"><Button variant="secondary">All applications</Button></Link>}
      />

      {app && (
        <Card className="mt-6">
          <CardBody className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="mb-1 text-sm text-slate-500">Current status</p><StatusBadge value={app.status} map={applicationStatusTone} /></div>
            {app.submitted_at && <p className="text-sm text-slate-500">Submitted {dateTime(app.submitted_at)}</p>}
          </CardBody>
        </Card>
      )}
      {app && <StatusNotice app={app} />}

      <Card className="mt-6">
        <CardHeader title="Application information" />
        <CardBody>
          <form ref={formRef} key={app?.id ?? 'new'} className="grid gap-5 sm:grid-cols-2" onSubmit={saveDraft} noValidate>
            <Field label="Award year" hint="Format: 2026-2027">{(field, hint) => <Input id={field} aria-describedby={hint} name="award_year" defaultValue={app?.award_year ?? ''} placeholder="2026-2027" disabled={disabled} />}</Field>
            <Field label="Program">{(field) => <Input id={field} name="program" maxLength={120} defaultValue={app?.program ?? ''} disabled={disabled} />}</Field>
            <Field label="Dependency status">{(field) => <Select id={field} name="dependency_status" defaultValue={app?.dependency_status ?? ''} disabled={disabled}><option value="">Select</option><option value="dependent">Dependent</option><option value="independent">Independent</option></Select>}</Field>
            <Field label="Enrollment intensity">{(field) => <Select id={field} name="enrollment_intensity" defaultValue={app?.enrollment_intensity ?? ''} disabled={disabled}><option value="">Select</option><option value="full_time">Full time</option><option value="three_quarter_time">Three-quarter time</option><option value="half_time">Half time</option><option value="less_than_half_time">Less than half time</option></Select>}</Field>
            <Field label="Requested amount">{(field) => <Input id={field} name="requested_amount" type="number" min="0" step="0.01" defaultValue={app?.requested_amount ?? ''} disabled={disabled} />}</Field>
            <Field label="Student aid index">{(field) => <Input id={field} name="student_aid_index" type="number" defaultValue={app?.student_aid_index ?? ''} disabled={disabled} />}</Field>
            {responding && (
              <Field label="Note to your financial aid office (optional)" className="sm:col-span-2">
                {(field) => <Textarea id={field} value={responseNote} maxLength={1000} onChange={(event) => setResponseNote(event.target.value)} />}
              </Field>
            )}
            {error && <p role="alert" className="text-sm text-red-700 sm:col-span-2">{error}</p>}
            {!disabled && (
              <div className="flex flex-wrap gap-3 sm:col-span-2">
                <Button type="submit" variant="secondary" loading={saving}>{responding ? 'Save changes' : 'Save draft'}</Button>
                <Button type="button" loading={actions.submit.isPending} disabled={saving} onClick={() => void submit()}>{responding ? 'Resubmit application' : 'Submit application'}</Button>
              </div>
            )}
          </form>
        </CardBody>
      </Card>

      {app ? (
        <StudentDocumentPanel applicationId={app.id} isEditable={app.is_editable} />
      ) : (
        <p className="mt-6 rounded-lg bg-slate-50 p-4 text-sm text-slate-600">Save a draft first, then you can attach supporting documents.</p>
      )}

      {app && (
        <Card className="mt-6">
          <CardHeader title="Status history" />
          <CardBody>
            <ol className="space-y-3">
              {app.history.map((event) => (
                <li key={`${event.created_at}-${event.to_status}`} className="border-l-2 border-slate-200 pl-3 text-sm">
                  <strong>{label(event.to_status)}</strong>
                  <p className="text-slate-500">{dateTime(event.created_at)} · {event.actor_role === 'student' ? 'You' : 'Financial aid office'}</p>
                  {event.student_message && <p className="mt-1 text-slate-700">{event.student_message}</p>}
                </li>
              ))}
            </ol>
            {app.is_withdrawable && <Button variant="danger" className="mt-5" onClick={() => setConfirmWithdraw(true)}>Withdraw application</Button>}
          </CardBody>
        </Card>
      )}

      <ConfirmDialog
        open={confirmWithdraw}
        onOpenChange={setConfirmWithdraw}
        title="Withdraw this application?"
        description="A withdrawn application cannot be edited or resubmitted. You can start a new application at any time."
        confirmLabel="Withdraw application"
        tone="danger"
        loading={actions.withdraw.isPending}
        onConfirm={() => void withdraw()}
      />
    </main>
  );
}
