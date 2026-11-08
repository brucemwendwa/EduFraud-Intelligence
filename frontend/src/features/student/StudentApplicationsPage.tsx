import { FilePlus2, GraduationCap } from 'lucide-react';
import { Link, useSearchParams } from 'react-router';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/cn';
import { money } from '@/lib/format';
import { applicationStatusTone } from '@/lib/status';
import { isStatusGroup, STATUS_GROUPS, useStudentApplications } from './studentApplications';

const filterClass = (active: boolean) =>
  cn(
    'rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset transition-colors',
    active ? 'bg-navy-900 text-white ring-navy-900' : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50',
  );

export default function StudentApplicationsPage() {
  const apps = useStudentApplications();
  const [params] = useSearchParams();
  const requested = params.get('status');
  const group = isStatusGroup(requested) ? requested : null;
  if (apps.isLoading) return <main className="flex justify-center py-16"><Spinner label="Loading applications" className="size-6" /></main>;
  if (!apps.data) return <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6"><ErrorState error={apps.error} onRetry={() => void apps.refetch()} /></main>;
  const statuses: readonly string[] | null = group ? STATUS_GROUPS[group].statuses : null;
  const visible = statuses ? apps.data.filter((app) => statuses.includes(app.status)) : apps.data;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader title="My financial aid applications" description="Create, save, submit and track your aid requests." actions={<Link to="/student/applications/new"><Button icon={<FilePlus2 className="size-4" />}>New application</Button></Link>} />
      <nav aria-label="Filter applications" className="flex flex-wrap gap-2">
        <Link to="/student/applications" className={filterClass(!group)} aria-current={!group ? 'true' : undefined}>All</Link>
        {Object.entries(STATUS_GROUPS).map(([value, { label }]) => (
          <Link key={value} to={`/student/applications?status=${value}`} className={filterClass(group === value)} aria-current={group === value ? 'true' : undefined}>{label}</Link>
        ))}
      </nav>
      {visible.length === 0 ? (
        apps.data.length === 0 ? (
          <EmptyState icon={<GraduationCap className="size-6" />} title="No applications yet" description="Start an application when you are ready. You can save a draft before submitting it." action={<Link to="/student/applications/new"><Button>Start application</Button></Link>} />
        ) : (
          <EmptyState icon={<GraduationCap className="size-6" />} title="No applications in this group" action={<Link to="/student/applications"><Button variant="secondary">Show all applications</Button></Link>} />
        )
      ) : (
        <div className="mt-6 space-y-3">
          {visible.map((app) => (
            <Link key={app.id} to={`/student/applications/${app.id}`} className="block">
              <Card className="transition hover:border-slate-300">
                <CardBody className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">{app.program || 'Untitled application'}</p>
                    <p className="mt-1 text-sm text-slate-500">{app.reference} · {app.award_year || 'Award year not set'} · {money(app.requested_amount)}</p>
                  </div>
                  <StatusBadge value={app.status} map={applicationStatusTone} />
                </CardBody>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
