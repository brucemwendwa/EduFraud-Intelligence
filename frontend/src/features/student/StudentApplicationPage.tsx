import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Field, Input, Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorState } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { applicationStatusTone } from '@/lib/status';
import { type Draft, useStudentApplication, useStudentApplicationActions } from './studentApplications';
import { StudentDocumentPanel } from '@/features/documents/StudentDocumentPanel';

export default function StudentApplicationPage() {
  const { id } = useParams(); const creating = id === 'new'; const { user } = useAuth(); const navigate = useNavigate();
  const query = useStudentApplication(creating ? undefined : id); const actions = useStudentApplicationActions(creating ? undefined : id);
  const [error, setError] = useState<string | null>(null);
  if (user?.role.key !== 'student') return <Navigate to="/app" replace />;
  if (!creating && query.isLoading) return <Spinner label="Loading application" className="size-6" />;
  if (!creating && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const app = query.data;
  const save = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setError(null); const fields = new FormData(event.currentTarget); const body: Partial<Draft> = { award_year: String(fields.get('award_year') || '') || null, dependency_status: String(fields.get('dependency_status') || '') || null, enrollment_intensity: String(fields.get('enrollment_intensity') || '') || null, program: String(fields.get('program') || '') || null, requested_amount: String(fields.get('requested_amount') || '') || null, student_aid_index: fields.get('student_aid_index') === '' ? null : Number(fields.get('student_aid_index')) }; try { const result = creating ? await actions.create.mutateAsync(body) : await actions.save.mutateAsync(body); toast.success(creating ? 'Draft created' : 'Draft saved'); navigate(`/student/applications/${result.id}`, { replace: true }); } catch (err) { setError(errorMessage(err)); } };
  const submit = async () => { setError(null); try { await actions.submit.mutateAsync(); toast.success('Application submitted'); await query.refetch(); } catch (err) { setError(errorMessage(err)); } };
  const withdraw = async () => { try { await actions.withdraw.mutateAsync(); toast.success('Application withdrawn'); await query.refetch(); } catch (err) { setError(errorMessage(err)); } };
  return <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6"><PageHeader title={creating ? 'New financial aid application' : app?.reference || 'Application'} description={creating ? 'Save a draft at any time. Required fields are checked when you submit.' : undefined} actions={<Link to="/student/applications"><Button variant="secondary">All applications</Button></Link>} />
    {app && <Card className="mt-6"><CardBody className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-slate-500">Current status</p><StatusBadge value={app.status} map={applicationStatusTone} /></div>{app.outstanding_requirements.length > 0 && <p className="text-sm text-amber-800">Needs attention: {app.outstanding_requirements.join(', ')}.</p>}</CardBody></Card>}
    <Card className="mt-6"><CardHeader title="Application information" /><CardBody><form key={app?.id ?? 'new'} className="grid gap-5 sm:grid-cols-2" onSubmit={save}>
      <Field label="Award year">{(field) => <Input id={field} name="award_year" defaultValue={app?.award_year ?? ''} placeholder="2026-2027" disabled={Boolean(app && !app.is_editable)} />}</Field>
      <Field label="Program">{(field) => <Input id={field} name="program" defaultValue={app?.program ?? ''} disabled={Boolean(app && !app.is_editable)} />}</Field>
      <Field label="Dependency status">{(field) => <Select id={field} name="dependency_status" defaultValue={app?.dependency_status ?? ''} disabled={Boolean(app && !app.is_editable)}><option value="">Select</option><option value="dependent">Dependent</option><option value="independent">Independent</option></Select>}</Field>
      <Field label="Enrollment intensity">{(field) => <Select id={field} name="enrollment_intensity" defaultValue={app?.enrollment_intensity ?? ''} disabled={Boolean(app && !app.is_editable)}><option value="">Select</option><option value="full_time">Full time</option><option value="three_quarter_time">Three-quarter time</option><option value="half_time">Half time</option><option value="less_than_half_time">Less than half time</option></Select>}</Field>
      <Field label="Requested amount">{(field) => <Input id={field} name="requested_amount" type="number" min="0" step="0.01" defaultValue={app?.requested_amount ?? ''} disabled={Boolean(app && !app.is_editable)} />}</Field>
      <Field label="Student aid index">{(field) => <Input id={field} name="student_aid_index" type="number" defaultValue={app?.student_aid_index ?? ''} disabled={Boolean(app && !app.is_editable)} />}</Field>
      {error && <p role="alert" className="sm:col-span-2 text-sm text-red-700">{error}</p>}
      {(creating || app?.is_editable) && <div className="sm:col-span-2 flex flex-wrap gap-3"><Button type="submit" loading={actions.create.isPending || actions.save.isPending}>Save draft</Button>{!creating && <Button type="button" variant="primary" loading={actions.submit.isPending} onClick={() => void submit()}>Submit application</Button>}</div>}
    </form></CardBody></Card>
    {app && <StudentDocumentPanel applicationId={app.id} isEditable={app.is_editable} />}
    {app && <Card className="mt-6"><CardHeader title="Status history" /><CardBody><ol className="space-y-3">{app.history.map((event, index) => <li key={`${event.created_at}-${index}`} className="border-l-2 border-slate-200 pl-3 text-sm"><strong className="capitalize">{event.to_status.replaceAll('_', ' ')}</strong><p className="text-slate-500">{new Date(event.created_at).toLocaleString()} · {event.actor_role.replaceAll('_', ' ')}</p></li>)}</ol>{['draft', 'submitted', 'under_review', 'additional_information_required'].includes(app.status) && <Button variant="danger" className="mt-5" loading={actions.withdraw.isPending} onClick={() => void withdraw()}>Withdraw application</Button>}</CardBody></Card>}
  </main>;
}
