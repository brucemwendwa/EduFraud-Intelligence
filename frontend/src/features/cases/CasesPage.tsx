import { AlarmClock, FolderKanban, ShieldAlert, UserX, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { cn } from '@/lib/cn';
import { date, label, timeAgo } from '@/lib/format';
import { caseStatusTone, findingMeta, priorityTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useCaseSummary, useCases } from './api';

const TABS = [
  { key: 'open', label: 'Open', statuses: ['new', 'under_review', 'escalated'] },
  { key: 'escalated', label: 'Escalated', statuses: ['escalated'] },
  { key: 'resolved', label: 'Resolved', statuses: ['resolved'] },
  { key: 'closed', label: 'Closed', statuses: ['closed'] },
  { key: 'all', label: 'All', statuses: [] as string[] },
];
const DEFAULTS = { tab: 'open', assignee: '', finding: '', q: '', page: '1' };

export default function CasesPage() {
  const navigate = useNavigate();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const tab = TABS.find((t) => t.key === filters.tab) ?? TABS[0]!;
  const { tab: _tab, ...rest } = filters;
  const list = useCases({ ...toParams(rest), page_size: '20', sort: tab.key === 'open' ? 'due_at' : 'updated_at', ...(tab.statuses.length ? { status: tab.statuses } : {}) });
  const summary = useCaseSummary();
  const s = summary.data;
  const filtered = Boolean(filters.assignee || filters.finding || filters.q);

  return (
    <>
      <PageHeader
        title="Investigations"
        description="Cases are where people decide. Alerts only flag suspicious activity; every escalation and resolution is a justified, recorded human decision."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Open cases" value={s?.open ?? '—'} icon={<FolderKanban className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Unassigned" value={s?.unassigned ?? '—'} icon={<UserX className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/cases?assignee=unassigned" />
        <StatCard label="Escalated (suspected fraud)" value={s?.escalated ?? '—'} icon={<ShieldAlert className="size-4" />} accent="critical" loading={summary.isLoading} to="/app/cases?tab=escalated" />
        <StatCard label="Past due date" value={s?.overdue ?? '—'} icon={<AlarmClock className="size-4" />} accent="blue" loading={summary.isLoading} />
      </div>

      <Card>
        <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4 pt-2" role="tablist" aria-label="Case status">
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
            <SearchInput placeholder="Search CASE-, FA- or title" label="Search cases" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Assignee" value={filters.assignee} onChange={(e) => setFilters({ assignee: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Assignee: anyone</option>
            <option value="me">Assigned to me</option>
            <option value="unassigned">Unassigned</option>
          </Select>
          <Select aria-label="Finding" value={filters.finding} onChange={(e) => setFilters({ finding: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-52">
            <option value="">Finding: any</option>
            {Object.entries(findingMeta).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>

        {list.isLoading ? (
          <TableSkeleton rows={6} cols={7} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : !list.data || list.data.items.length === 0 ? (
          <EmptyState
            icon={<FolderKanban className="size-5" />}
            title="No cases here"
            description="Open an investigation from a fraud alert or an application to start a case."
          />
        ) : (
          <div className={list.isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr><TH>Case</TH><TH>Application</TH><TH>Priority</TH><TH>Status</TH><TH>Finding</TH><TH>Assignee</TH><TH>Due</TH><TH>Updated</TH></tr>
              </THead>
              <tbody>
                {list.data.items.map((c) => {
                  const finding = findingMeta[c.finding];
                  return (
                    <TR key={c.id} onClick={() => navigate(`/app/cases/${c.id}`)}>
                      <TD className="max-w-sm">
                        <a href={`/app/cases/${c.id}`} onClick={(e) => { e.preventDefault(); navigate(`/app/cases/${c.id}`); }} className="font-medium text-slate-900 hover:text-brand-blue">
                          {c.title}
                        </a>
                        <div className="font-mono text-xs text-slate-500">{c.reference} · {label(c.fraud_category)}</div>
                      </TD>
                      <TD className="font-mono text-xs">{c.application_ref ?? '—'}</TD>
                      <TD><Badge tone={priorityTone[c.priority] ?? 'neutral'}>{label(c.priority)}</Badge></TD>
                      <TD><StatusBadge value={c.status} map={caseStatusTone} /></TD>
                      <TD>{finding ? <Badge tone={finding.tone} title={finding.help}>{finding.label}</Badge> : label(c.finding)}</TD>
                      <TD className="text-xs">{c.assigned_to?.full_name ?? <span className="text-amber-700">Unassigned</span>}</TD>
                      <TD className={cn('tabular text-xs whitespace-nowrap', c.overdue && 'font-semibold text-red-700')}>
                        {c.due_at ? date(c.due_at) : '—'}{c.overdue && ' · overdue'}
                      </TD>
                      <TD className="text-xs whitespace-nowrap text-slate-500">{timeAgo(c.updated_at)}</TD>
                    </TR>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
    </>
  );
}
