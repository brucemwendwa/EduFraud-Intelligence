import { CheckCircle2, ClipboardList, FileClock, FileSearch, FolderOpen, MailQuestion, PauseCircle, XCircle } from 'lucide-react';
import { Link } from 'react-router';
import type { ApplicationActivity, ApplicationPipeline as Pipeline } from '@/api/types';
import { StatusBadge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { label, timeAgo } from '@/lib/format';
import { applicationStatusTone } from '@/lib/status';
import { useApplicationPipeline } from './api';

const RISK_BAR: Record<string, string> = {
  critical: 'bg-risk-critical',
  high: 'bg-risk-high',
  medium: 'bg-risk-medium',
  low: 'bg-risk-low',
};

/** Live application-processing figures for the signed-in user's institution. */
export function ApplicationPipeline() {
  const { data, isLoading, error, refetch } = useApplicationPipeline();
  if (error) return <Card className="mb-6"><ErrorState title="Application figures unavailable" error={error} onRetry={() => refetch()} /></Card>;
  const value = (n: number | undefined) => n?.toLocaleString() ?? '—';
  const tiles = [
    { label: 'Total applications', value: value(data?.total), to: '/app/applications', icon: <ClipboardList className="size-4" />, accent: 'navy' as const },
    { label: 'Awaiting review', value: value(data?.awaiting_review), to: '/app/applications?queue=awaiting_review', icon: <FileClock className="size-4" />, accent: 'blue' as const },
    { label: 'Under review', value: value(data?.in_review), to: '/app/applications?status=in_review', icon: <FileSearch className="size-4" />, accent: 'blue' as const },
    { label: 'Additional information requested', value: value(data?.additional_information_required), to: '/app/applications?status=additional_information_required', icon: <MailQuestion className="size-4" />, accent: 'warning' as const },
    { label: 'On hold', value: value(data?.on_hold), to: '/app/applications?status=on_hold', icon: <PauseCircle className="size-4" />, accent: 'warning' as const },
    { label: 'Approved', value: value(data?.approved), to: '/app/applications?status=approved', icon: <CheckCircle2 className="size-4" />, accent: 'success' as const },
    { label: 'Rejected', value: value(data?.rejected), to: '/app/applications?status=rejected', icon: <XCircle className="size-4" />, accent: 'critical' as const },
  ];

  return (
    <section aria-labelledby="application-pipeline" className="mb-8">
      <h2 id="application-pipeline" className="mb-3 text-sm font-semibold text-slate-900">Application pipeline</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {tiles.map((tile) => <StatCard key={tile.label} {...tile} loading={isLoading} />)}
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-5">
        <OpenRisk data={data} loading={isLoading} className="xl:col-span-2" />
        <RecentApplications items={data?.recent_activity} loading={isLoading} className="xl:col-span-3" />
      </div>
    </section>
  );
}

function OpenRisk({ data, loading, className }: { data?: Pipeline; loading: boolean; className?: string }) {
  const peak = Math.max(1, ...(data?.open_by_risk.map((r) => r.count) ?? []));
  return (
    <Card className={className}>
      <CardHeader title="Open applications by risk" description="Prioritises human review. A level is never a decision." icon={<FolderOpen className="size-4" />} />
      <div className="space-y-3 px-5 pb-5">
        {loading || !data ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-6" />)
        ) : (
          <>
            {data.open_by_risk.map((row) => (
              <Link key={row.level} to={`/app/applications?queue=open&risk_level=${row.level}`} className="grid grid-cols-[4.5rem_1fr_3rem] items-center gap-3 rounded text-sm hover:bg-slate-50">
                <span className="text-slate-700">{label(row.level)}</span>
                <span className="block h-2 rounded-full bg-slate-100">
                  <span className={`block h-2 rounded-full ${RISK_BAR[row.level]}`} style={{ width: `${(row.count / peak) * 100}%` }} />
                </span>
                <span className="tabular text-right font-medium text-slate-900">{row.count.toLocaleString()}</span>
              </Link>
            ))}
            <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
              {data.open_total.toLocaleString()} open · {data.open_unassessed.toLocaleString()} not yet assessed · {data.documents_awaiting_review.toLocaleString()} document{data.documents_awaiting_review === 1 ? '' : 's'} awaiting review
            </p>
          </>
        )}
      </div>
    </Card>
  );
}

function RecentApplications({ items, loading, className }: { items?: ApplicationActivity[]; loading: boolean; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader title="Recent application activity" description="Status changes, then the latest submissions." icon={<ClipboardList className="size-4" />} actions={<Link to="/app/applications?sort=submitted_at" className="text-xs font-medium text-brand-blue hover:underline">All applications</Link>} />
      {loading ? (
        <div className="space-y-2 px-5 pb-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>
      ) : !items || items.length === 0 ? (
        <EmptyState title="No application activity" description="Submitted applications and decisions will appear here." />
      ) : (
        <ul className="divide-y divide-slate-100 border-t border-slate-100">
          {items.slice(0, 8).map((item) => (
            <li key={`${item.application_id}-${item.occurred_at}`}>
              <Link to={`/app/applications/${item.application_id}`} className="flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-slate-50">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-slate-900">{item.reference}</span>
                  <span className="block truncate text-xs text-slate-500">
                    <span className="font-mono">{item.student_ref}</span>
                    {item.actor_role ? ` · by ${label(item.actor_role)}` : ''}
                  </span>
                </span>
                {item.risk_level && item.risk_level !== 'low' && <RiskBadge level={item.risk_level as RiskLevel} />}
                <StatusBadge value={item.to_status} map={applicationStatusTone} />
                <span className="hidden w-24 shrink-0 text-right text-xs text-slate-500 sm:block">{timeAgo(item.occurred_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
