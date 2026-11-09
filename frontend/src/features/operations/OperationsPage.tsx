import { AlertTriangle, CheckCircle2, CircleSlash, FlaskConical, ScrollText, ServerCog, XCircle, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router';
import type { OperationsOverview, ServiceHealth } from '@/api/types';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { dateTime, label, timeAgo } from '@/lib/format';
import { P } from '@/lib/permissions';
import { useOperationsOverview } from './api';

const HEALTH: Record<ServiceHealth['status'], { tone: Tone; icon: LucideIcon; text: string }> = {
  ok: { tone: 'success', icon: CheckCircle2, text: 'Healthy' },
  degraded: { tone: 'warning', icon: AlertTriangle, text: 'Degraded' },
  down: { tone: 'critical', icon: XCircle, text: 'Down' },
  not_configured: { tone: 'neutral', icon: CircleSlash, text: 'Not configured' },
  simulated: { tone: 'violet', icon: FlaskConical, text: 'Simulated' },
};
const outcomeTone: Record<string, Tone> = { success: 'success', failure: 'critical', denied: 'warning' };

function HealthBadge({ status }: { status: ServiceHealth['status'] }) {
  const { tone, icon: Icon, text } = HEALTH[status];
  return <Badge tone={tone} icon={<Icon className="size-3" aria-hidden />}>{text}</Badge>;
}

export default function OperationsPage() {
  const { can, user } = useAuth();
  const { data, isLoading, error, refetch } = useOperationsOverview();
  return (
    <>
      <PageHeader
        title="Operations"
        description={`Service health and processing activity for ${data?.scope === 'platform' ? 'all institutions' : user?.organization?.name ?? 'your institution'}. Counts only: no student names or document contents.`}
        meta={data && <span className="text-xs text-slate-500">Updated {dateTime(data.generated_at)} · Environment: {label(data.environment)}</span>}
      />
      {error ? (
        <Card><ErrorState title="Operations data unavailable" error={error} onRetry={() => refetch()} /></Card>
      ) : (
        <div className="space-y-8">
          <Health data={data} loading={isLoading} />
          <Performance data={data} loading={isLoading} />
          <Processing data={data} loading={isLoading} />
          <Jobs data={data} loading={isLoading} />
          {can(P.auditRead) && <AuditEvents data={data} loading={isLoading} />}
        </div>
      )}
    </>
  );
}

function Health({ data, loading }: { data?: OperationsOverview; loading: boolean }) {
  const limited = data?.health.filter((h) => h.status === 'not_configured' || h.status === 'simulated').length ?? 0;
  return (
    <section aria-labelledby="service-health">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 id="service-health" className="text-sm font-semibold text-slate-900">Service health</h2>
        {data && <HealthBadge status={data.overall_health} />}
        {limited > 0 && <span className="text-xs text-slate-500">{limited} service{limited === 1 ? '' : 's'} not live</span>}
      </div>
      <Card>
        {loading || !data ? (
          <TableSkeleton rows={6} cols={3} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.health.map((check) => (
              <li key={check.key} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-5 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{check.name}</p>
                  <p className="text-xs text-slate-500">{check.detail}</p>
                </div>
                <HealthBadge status={check.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  );
}

function Performance({ data, loading }: { data?: OperationsOverview; loading: boolean }) {
  const api = data?.api_performance;
  const audit = data?.audit_signals;
  const milliseconds = (value: number | null | undefined) => (value == null ? '—' : `${Math.round(value)} ms`);
  const tiles = [
    { label: 'API response time, median', value: milliseconds(api?.p50_ms), footnote: 'This API instance only' },
    { label: 'API response time, 95th percentile', value: milliseconds(api?.p95_ms), footnote: api ? `Last ${api.sample_size.toLocaleString()} requests` : undefined },
    { label: 'API server errors', value: api?.server_error_rate == null ? '—' : `${(api.server_error_rate * 100).toFixed(1)}%` },
    ...(audit ? [{ label: 'Permission denials / failed sign-ins (24 h)', value: `${audit.denied_24h} / ${audit.failed_logins_24h}`, to: '/app/audit?outcome=denied' }] : []),
  ];
  return (
    <section aria-labelledby="api-performance">
      <h2 id="api-performance" className="mb-3 text-sm font-semibold text-slate-900">Performance and security signals</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((tile) => <StatCard key={tile.label} {...tile} loading={loading} />)}
      </div>
    </section>
  );
}

function Processing({ data, loading }: { data?: OperationsOverview; loading: boolean }) {
  const a = data?.applications;
  const r = data?.risk;
  const d = data?.documents;
  const tiles = [
    { label: 'Submitted (24 h / 7 d)', value: a ? `${a.submitted_24h} / ${a.submitted_7d}` : '—' },
    { label: 'Decisions (24 h / 7 d)', value: a ? `${a.decisions_24h} / ${a.decisions_7d}` : '—' },
    { label: 'Awaiting review', value: a?.awaiting_review ?? '—', to: '/app/applications?queue=awaiting_review', footnote: a?.oldest_waiting_since ? `Oldest ${timeAgo(a.oldest_waiting_since)}` : undefined },
    { label: 'Risk assessments (24 h / 7 d)', value: r ? `${r.assessments_24h} / ${r.assessments_7d}` : '—' },
    { label: 'Open elevated risk', value: r?.open_elevated ?? '—', to: '/app/applications?queue=open&risk_level=high&risk_level=critical' },
    { label: 'Open, not yet assessed', value: r?.open_unassessed ?? '—' },
    { label: 'Evidence waiting for a scan', value: d ? d.pending_scan + d.scanning : '—' },
    { label: 'Evidence awaiting staff review', value: d?.awaiting_staff_review ?? '—' },
  ];
  return (
    <section aria-labelledby="processing-activity">
      <h2 id="processing-activity" className="mb-3 text-sm font-semibold text-slate-900">Processing activity</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((tile) => <StatCard key={tile.label} {...tile} loading={loading} />)}
      </div>
      {d && (
        <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-3 lg:grid-cols-6">
          {([['Pending scan', d.pending_scan], ['Scanning', d.scanning], ['Clean', d.available], ['Malware found', d.rejected], ['Scan failed', d.failed], ['Superseded', d.superseded]] as const).map(([name, count]) => (
            <div key={name}><dt className="text-xs text-slate-500">{name}</dt><dd className="tabular mt-0.5 font-medium text-slate-900">{count.toLocaleString()}</dd></div>
          ))}
        </dl>
      )}
    </section>
  );
}

function Jobs({ data, loading }: { data?: OperationsOverview; loading: boolean }) {
  const jobs = data?.jobs;
  const summary = jobs && `Scans: ${jobs.scan_queued} queued, ${jobs.scan_running} running, ${jobs.scan_retrying} retrying, ${jobs.scan_failed} failed · Cleanup failures: ${jobs.cleanup_failed} · Stalled: ${jobs.stalled} · Last detection run: ${data.risk.last_run_status ? label(data.risk.last_run_status) : 'none'} · Email: ${data.email.sent_24h} sent in 24 h, ${data.email.queued + data.email.retrying} pending, ${data.email.failed} failed${data.email.suppressed ? `, ${data.email.suppressed} not sent (development mode)` : ''}`;
  return (
    <Card>
      <CardHeader title="Background jobs" description={summary} icon={<ServerCog className="size-4" />} />
      {loading || !jobs ? (
        <TableSkeleton rows={3} cols={4} />
      ) : jobs.recent_failures.length === 0 ? (
        <EmptyState title="No failed or retrying jobs" className="py-8" />
      ) : (
        <Table>
          <THead><tr><TH>Job</TH><TH>Status</TH><TH>Error code</TH><TH>Attempts</TH><TH>When</TH></tr></THead>
          <tbody>
            {jobs.recent_failures.map((failure, index) => (
              <TR key={`${failure.kind}-${failure.occurred_at}-${index}`}>
                <TD className="font-medium text-slate-900">{label(failure.kind)}</TD>
                <TD><Badge tone={failure.status === 'retry' ? 'warning' : 'critical'}>{label(failure.status)}</Badge></TD>
                <TD><code className="text-xs">{failure.error_code ?? '—'}</code></TD>
                <TD className="tabular">{failure.attempts ?? '—'}</TD>
                <TD className="tabular whitespace-nowrap text-xs">{dateTime(failure.occurred_at)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

function AuditEvents({ data, loading }: { data?: OperationsOverview; loading: boolean }) {
  return (
    <Card>
      <CardHeader title="Recent audit events" description="Actions and outcomes only. Open the audit log for details." icon={<ScrollText className="size-4" />} actions={<Link to="/app/audit" className="text-xs font-medium text-brand-blue hover:underline">Audit logs</Link>} />
      {loading || !data?.recent_audit ? (
        <TableSkeleton rows={5} cols={4} />
      ) : data.recent_audit.length === 0 ? (
        <EmptyState title="No audit events in scope" className="py-8" />
      ) : (
        <Table>
          <THead><tr><TH>When</TH><TH>Action</TH><TH>Role</TH><TH>Outcome</TH></tr></THead>
          <tbody>
            {data.recent_audit.map((event) => (
              <TR key={event.sequence}>
                <TD className="tabular whitespace-nowrap text-xs">{dateTime(event.occurred_at)}</TD>
                <TD><code className="text-xs">{event.action}</code><span className="block text-[11px] text-slate-500">{label(event.category)}</span></TD>
                <TD className="text-xs">{event.actor_role ? label(event.actor_role) : 'System'}</TD>
                <TD><Badge tone={outcomeTone[event.outcome] ?? 'neutral'}>{label(event.outcome)}</Badge></TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
