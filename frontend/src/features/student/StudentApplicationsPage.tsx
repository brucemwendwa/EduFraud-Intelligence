import { FilePlus2, GraduationCap } from 'lucide-react';
import { Link, Navigate } from 'react-router';
import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorState, EmptyState } from '@/components/ui/States';
import { StatusBadge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { applicationStatusTone } from '@/lib/status';
import { useAuth } from '@/lib/auth';
import { useStudentApplications } from './studentApplications';

export default function StudentApplicationsPage() {
  const { user } = useAuth();
  const apps = useStudentApplications();
  if (user?.role.key !== 'student') return <Navigate to="/app" replace />;
  if (apps.isLoading) return <Spinner label="Loading applications" className="size-6" />;
  if (!apps.data) return <ErrorState error={apps.error} onRetry={() => void apps.refetch()} />;
  return <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
    <PageHeader title="My financial aid applications" description="Create, save, submit and track your aid request." actions={<Link to="/student/applications/new"><Button><FilePlus2 className="size-4" /> New application</Button></Link>} />
    {apps.data.length === 0 ? <EmptyState icon={<GraduationCap className="size-6" />} title="No applications yet" description="Start an application when you are ready. You can save a draft before submitting it." action={<Link to="/student/applications/new"><Button>Start application</Button></Link>} /> : <div className="mt-6 space-y-3">{apps.data.map((app) => <Link key={app.id} to={`/student/applications/${app.id}`} className="block"><Card className="transition hover:border-slate-300"><CardBody className="flex items-center justify-between gap-4"><div><p className="font-semibold text-slate-900">{app.program || 'Untitled application'}</p><p className="mt-1 text-sm text-slate-500">{app.reference} · {app.award_year || 'Award year not set'}</p></div><StatusBadge value={app.status} map={applicationStatusTone} /></CardBody></Card></Link>)}</div>}
  </main>;
}
