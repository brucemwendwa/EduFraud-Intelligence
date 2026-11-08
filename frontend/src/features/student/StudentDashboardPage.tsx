import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  FilePen,
  FilePlus2,
  Inbox,
  Search,
  Send,
  XCircle,
} from 'lucide-react';
import { Link } from 'react-router';
import type { StudentPortalApplication } from '@/api/types';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Spinner } from '@/components/ui/Spinner';
import { dateTime, money, timeAgo } from '@/lib/format';
import { applicationStatusTone } from '@/lib/status';
import { useStudentDashboard } from './studentApplications';

function applicationAction(app: StudentPortalApplication) {
  if (app.status === 'draft') return 'Continue draft';
  if (app.status === 'additional_information_required') return 'Respond';
  return 'View';
}

export default function StudentDashboardPage() {
  const dashboard = useStudentDashboard();
  if (dashboard.isLoading) {
    return <main className="flex justify-center py-16"><Spinner label="Loading your aid information" className="size-6" /></main>;
  }
  if (!dashboard.data) {
    return <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6"><ErrorState title="Unable to load your aid information" error={dashboard.error} onRetry={() => void dashboard.refetch()} /></main>;
  }
  const { profile, counts, information_requests: requests, recent_activity: activity, applications } = dashboard.data;
  const tiles = [
    { label: 'All applications', value: counts.total, to: '/student/applications', icon: <ClipboardList className="size-4" />, accent: 'navy' as const },
    { label: 'Drafts', value: counts.draft, to: '/student/applications?status=draft', icon: <FilePen className="size-4" />, accent: 'navy' as const },
    { label: 'Submitted', value: counts.submitted, to: '/student/applications?status=submitted', icon: <Send className="size-4" />, accent: 'blue' as const },
    { label: 'Under review', value: counts.under_review, to: '/student/applications?status=under_review', icon: <Search className="size-4" />, accent: 'blue' as const },
    { label: 'Action needed', value: counts.additional_information, to: '/student/applications?status=additional_information', icon: <AlertTriangle className="size-4" />, accent: 'warning' as const },
    { label: 'Approved', value: counts.approved, to: '/student/applications?status=approved', icon: <CheckCircle2 className="size-4" />, accent: 'success' as const },
    { label: 'Not approved', value: counts.rejected, to: '/student/applications?status=rejected', icon: <XCircle className="size-4" />, accent: 'critical' as const },
  ];

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader
        title={`Welcome, ${profile.full_name}`}
        description={`${profile.institution} · Student reference ${profile.student_ref}`}
        actions={<Link to="/student/applications/new"><Button icon={<FilePlus2 className="size-4" />}>New application</Button></Link>}
      />

      {requests.length > 0 && (
        <section aria-labelledby="action-needed" className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h2 id="action-needed" className="flex items-center gap-2 text-sm font-semibold text-amber-900">
            <AlertTriangle className="size-4" aria-hidden /> Your financial aid office needs more information
          </h2>
          <ul className="mt-3 space-y-3">
            {requests.map((request) => (
              <li key={request.application_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white p-3 ring-1 ring-amber-100">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{request.program || 'Application'} · {request.reference}</p>
                  <p className="mt-0.5 text-sm text-slate-700">{request.message ?? 'Open the application to see what is needed.'}</p>
                </div>
                <Link to={`/student/applications/${request.application_id}`}><Button size="sm">Respond <ArrowRight className="size-3.5" aria-hidden /></Button></Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {tiles.map((tile) => <StatCard key={tile.label} {...tile} />)}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="My applications" icon={<ClipboardList className="size-4" />} actions={<Link to="/student/applications" className="text-xs font-medium text-brand-blue hover:underline">View all</Link>} />
          {applications.length === 0 ? (
            <EmptyState icon={<FilePlus2 className="size-5" />} title="No applications yet" description="Start an application when you are ready. You can save a draft before submitting it." action={<Link to="/student/applications/new"><Button>Start application</Button></Link>} />
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {applications.slice(0, 5).map((app) => (
                <li key={app.id}>
                  <Link to={`/student/applications/${app.id}`} className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-slate-50">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-900">{app.program || 'Untitled application'}</span>
                      <span className="block text-xs text-slate-500">{app.reference} · {money(app.requested_amount)}</span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <StatusBadge value={app.status} map={applicationStatusTone} />
                      <span className="text-xs font-medium text-brand-blue">{applicationAction(app)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Recent activity" icon={<Inbox className="size-4" />} />
          {activity.length === 0 ? (
            <CardBody><p className="text-sm text-slate-500">Updates to your applications and documents will appear here.</p></CardBody>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {activity.map((item) => (
                <li key={`${item.kind}-${item.application_id}-${item.occurred_at}`}>
                  <Link to={`/student/applications/${item.application_id}`} className="block px-5 py-3 transition-colors hover:bg-slate-50">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="text-sm font-medium text-slate-900">{item.title}</span>
                      <span className="shrink-0 text-xs text-slate-500" title={dateTime(item.occurred_at)}>{timeAgo(item.occurred_at)}</span>
                    </span>
                    <span className="block text-xs text-slate-500">{item.reference}{item.detail ? ` · ${item.detail}` : ''}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </main>
  );
}
