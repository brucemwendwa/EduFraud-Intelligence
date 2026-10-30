import { AlertTriangle, Banknote, CalendarClock, CreditCard, Landmark, PauseCircle, X } from 'lucide-react';
import { useState } from 'react';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, riskLevelOf } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, SortableTH, TD, TH, THead, TR, Table, type SortDir } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { date, label, money } from '@/lib/format';
import { disbursementStatusTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useDisbursementSummary, useDisbursements } from './api';
import { DisbursementDrawer } from './DisbursementDrawer';

const DEFAULTS = { q: '', status: '', fund_type: '', flagged: '', sort: 'disbursed_at', direction: 'desc', page: '1' };

export default function DisbursementsPage() {
  const { user, activeOrgId } = useAuth();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const [selected, setSelected] = useState<string | null>(null);
  const summary = useDisbursementSummary();
  const { data, isLoading, isFetching, error, refetch } = useDisbursements({ ...toParams(filters), page_size: '20' });
  const showInstitution = Boolean(user?.is_platform_admin && !activeOrgId);
  const filtered = Boolean(filters.q || filters.status || filters.fund_type || filters.flagged);
  const s = summary.data;

  const onSort = (field: string) =>
    setFilters({ sort: field, direction: filters.sort === field && filters.direction === 'desc' ? 'asc' : 'desc' });

  return (
    <>
      <PageHeader
        title="Disbursement monitoring"
        description="Watch funds before and after they move. The system detects repeated payment destinations, unusual amounts and bursts of payments. Holds are always placed by a person."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Disbursements in scope" value={s ? s.total_count.toLocaleString() : '—'} footnote={s && money(s.total_amount)} icon={<Banknote className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Flagged for review" value={s ? s.flagged_count.toLocaleString() : '—'} footnote={s && `${money(s.flagged_amount)} at risk`} icon={<AlertTriangle className="size-4" />} accent="critical" loading={summary.isLoading}
          to="/app/disbursements?flagged=true&sort=risk_score" />
        <StatCard label="On hold" value={s ? s.held_count.toLocaleString() : '—'} footnote={s && money(s.held_amount)} icon={<PauseCircle className="size-4" />} accent="warning" loading={summary.isLoading}
          to="/app/disbursements?status=held" />
        <StatCard label="Scheduled" value={s ? s.scheduled_count.toLocaleString() : '—'} footnote="Can still be held" icon={<CalendarClock className="size-4" />} accent="blue" loading={summary.isLoading}
          to="/app/disbursements?status=scheduled" />
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="Search DSB- or STU- reference" label="Search disbursements" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Status" value={filters.status} onChange={(e) => setFilters({ status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-40">
            <option value="">Status: all</option>
            {['scheduled', 'released', 'held', 'reversed'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Fund type" value={filters.fund_type} onChange={(e) => setFilters({ fund_type: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-52">
            <option value="">Fund: all</option>
            {['pell_grant', 'direct_subsidized', 'direct_unsubsidized', 'institutional_grant', 'credit_balance_refund'].map((v) => (
              <option key={v} value={v}>{label(v)}</option>
            ))}
          </Select>
          <Select aria-label="Risk" value={filters.flagged} onChange={(e) => setFilters({ flagged: e.target.value })} className="w-full sm:w-44">
            <option value="">Risk: all</option>
            <option value="true">Flagged only</option>
            <option value="false">Not flagged</option>
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>

        {isLoading ? (
          <TableSkeleton rows={8} cols={7} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<Banknote className="size-5" />} title="No disbursements match these filters" action={filtered ? <Button variant="secondary" size="sm" onClick={reset}>Clear filters</Button> : undefined} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr>
                  <TH>Reference</TH>
                  <TH>Student</TH>
                  {showInstitution && <TH>Institution</TH>}
                  <TH>Fund</TH>
                  <SortableTH label="Amount" field="amount" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} className="text-right" />
                  <SortableTH label="Date" field="disbursed_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Destination</TH>
                  <TH>Status</TH>
                  <SortableTH label="Risk" field="risk_score" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                </tr>
              </THead>
              <tbody>
                {data.items.map((d) => (
                  <TR key={d.id} onClick={() => setSelected(d.id)}>
                    <TD>
                      <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); setSelected(d.id); }}>
                        {d.reference}
                      </button>
                    </TD>
                    <TD><span className="font-mono text-xs">{d.student.student_ref}</span></TD>
                    {showInstitution && <TD className="text-xs">{d.organization.name}</TD>}
                    <TD className="whitespace-nowrap">{label(d.fund_type)}</TD>
                    <TD className="tabular text-right font-medium text-slate-900">{money(d.amount, true)}</TD>
                    <TD className="tabular whitespace-nowrap">{date(d.disbursed_at)}</TD>
                    <TD>
                      <span className="inline-flex items-center gap-1.5">
                        {d.destination.destination_type === 'prepaid_card' ? <CreditCard className="size-3.5 text-slate-400" aria-label="Prepaid card" /> : <Landmark className="size-3.5 text-slate-400" aria-label="Bank account" />}
                        <code className="text-xs">{d.destination.handle}</code>
                      </span>
                      {d.destination_changed_at && <Badge tone="warning" className="mt-1">Changed {date(d.destination_changed_at)}</Badge>}
                    </TD>
                    <TD><StatusBadge value={d.status} map={disbursementStatusTone} /></TD>
                    <TD>{d.risk_score != null ? <RiskBadge level={riskLevelOf(d.risk_score)} score={d.risk_score} /> : <span className="text-xs text-slate-400">Not scored</span>}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
      <DisbursementDrawer id={selected} onClose={() => setSelected(null)} />
    </>
  );
}
