import { AlertOctagon, Bell, BellRing, Flag, ScanFace, X } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { cn } from '@/lib/cn';
import { label, timeAgo } from '@/lib/format';
import { alertCategoryLabel } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { OpenCaseButton } from '@/features/cases/OpenCaseButton';
import { AlertDrawer, AlertStatusBadge } from './AlertDrawer';
import { useAlertSummary, useAlerts } from './api';

const TABS = [
  { key: 'live', label: 'Needs attention', statuses: ['open', 'acknowledged', 'escalated'] },
  { key: 'verification', label: 'Verification requested', statuses: ['verification_requested'] },
  { key: 'escalated', label: 'Escalated', statuses: ['escalated'] },
  { key: 'in_investigation', label: 'In investigation', statuses: ['in_investigation'] },
  { key: 'closed', label: 'Resolved & false positives', statuses: ['resolved', 'false_positive', 'dismissed'] },
  { key: 'all', label: 'All', statuses: [] as string[] },
];
const ACCOUNT_CATEGORIES = ['lost_stolen_card', 'suspicious_login', 'new_device', 'password_reset', 'account_takeover', 'unusual_transaction', 'suspicious_location', 'aid_redirection', 'verification_required', 'coordinated_fraud'];
const APPLICATION_CATEGORIES = ['biometric', 'identity', 'network', 'disbursement', 'enrollment', 'application'];

const DEFAULTS = { tab: 'live', severity: '', category: '', kind: '', assigned: '', q: '', page: '1', selected: '' };

export default function AlertsPage() {
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const tab = TABS.find((t) => t.key === filters.tab) ?? TABS[0]!;
  const { tab: _tab, selected, ...rest } = filters;
  const params = { ...toParams(rest), page_size: '20', ...(tab.statuses.length ? { status: tab.statuses } : {}) };
  const { data, isLoading, isFetching, error, refetch } = useAlerts(params);
  const summary = useAlertSummary();
  const s = summary.data;
  const filtered = Boolean(filters.severity || filters.category || filters.q || filters.kind || filters.assigned);

  return (
    <>
      <PageHeader
        title="Security & fraud alerts"
        description="Lost cards, suspicious sign-ins, account takeover, unusual transactions, aid redirection and coordinated patterns, each with its evidence and a recommended next step. People review, assign, verify, escalate and resolve; every action is audited."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="New alerts" value={s?.open ?? '—'} footnote={s && `${s.acknowledged} under review`} icon={<Bell className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Critical, unresolved" value={s?.critical_open ?? '—'} icon={<AlertOctagon className="size-4" />} accent="critical" loading={summary.isLoading} />
        <StatCard label="Awaiting identity verification" value={s?.verification_requested ?? '—'} icon={<ScanFace className="size-4" />} accent="blue" loading={summary.isLoading} to="/app/alerts?tab=verification" />
        <StatCard label="Escalated" value={s?.escalated ?? '—'} footnote={s && `${s.assigned_to_me} assigned to you`} icon={<Flag className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/alerts?tab=escalated" />
      </div>

      <Card>
        <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4 pt-2" role="tablist" aria-label="Alert status">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab.key === t.key}
              onClick={() => setFilters({ tab: t.key })}
              className={cn(
                '-mb-px border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors',
                tab.key === t.key ? 'border-navy-900 text-navy-900' : 'border-transparent text-slate-500 hover:text-slate-800',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="Search ALT-, SFA- or FA- reference" label="Search alerts" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Severity" value={filters.severity} onChange={(e) => setFilters({ severity: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-40">
            <option value="">Severity: all</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
          </Select>
          <Select aria-label="Category" value={filters.category} onChange={(e) => setFilters({ category: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-56">
            <option value="">Category: all</option>
            <optgroup label="Account protection">
              {ACCOUNT_CATEGORIES.map((c) => <option key={c} value={c}>{alertCategoryLabel[c]}</option>)}
            </optgroup>
            <optgroup label="Aid applications">
              {APPLICATION_CATEGORIES.map((c) => <option key={c} value={c}>{alertCategoryLabel[c] ?? label(c)}</option>)}
            </optgroup>
          </Select>
          <Select aria-label="Source" value={filters.kind} onChange={(e) => setFilters({ kind: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Source: all</option>
            <option value="account">ID-linked accounts</option>
            <option value="application">Aid applications</option>
          </Select>
          <Select aria-label="Assignment" value={filters.assigned} onChange={(e) => setFilters({ assigned: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-40">
            <option value="">Assigned: anyone</option>
            <option value="me">Assigned to me</option>
            <option value="unassigned">Unassigned</option>
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>

        {isLoading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<BellRing className="size-5" />} title="No alerts here" description={tab.key === 'live' ? 'Nothing needs attention right now.' : 'No alerts match this view.'} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr><TH>Alert</TH><TH>Severity</TH><TH>Subject</TH><TH>Category</TH><TH>Assigned</TH><TH>Status</TH><TH>Raised</TH></tr>
              </THead>
              <tbody>
                {data.items.map((a) => (
                  <TR key={a.id} onClick={() => setFilters({ selected: a.id, page: filters.page })}>
                    <TD className="max-w-md">
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setFilters({ selected: a.id, page: filters.page }); }}
                        className="text-left font-medium text-slate-900 hover:text-brand-blue"
                      >
                        {a.title}
                      </button>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                        <span className="font-mono">{a.reference}</span>
                        {a.case_ref && <Badge tone="blue">{a.case_ref}</Badge>}
                      </div>
                    </TD>
                    <TD><RiskBadge level={a.severity as RiskLevel} score={a.risk_score} /></TD>
                    <TD className="text-xs">
                      <span className="font-mono">{a.account_ref ?? a.application_ref ?? '—'}</span>
                      {a.student_ref && <span className="block font-mono text-[11px] text-slate-500">{a.student_ref}</span>}
                    </TD>
                    <TD className="text-sm">{alertCategoryLabel[a.category] ?? label(a.category)}</TD>
                    <TD className="text-xs text-slate-600">{a.assigned_to?.full_name ?? '—'}</TD>
                    <TD><AlertStatusBadge status={a.status} /></TD>
                    <TD className="whitespace-nowrap text-xs text-slate-500" title={a.created_at}>{timeAgo(a.created_at)}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p), selected: '' })} />
          </div>
        )}
      </Card>
      <AlertDrawer
        id={selected || null}
        onClose={() => setFilters({ selected: '', page: filters.page })}
        extraActions={(alertId, applicationId, _status, caseId, caseRef) => (
          <OpenCaseButton alertId={alertId} applicationId={applicationId} caseId={caseId} caseRef={caseRef} />
        )}
      />
    </>
  );
}
