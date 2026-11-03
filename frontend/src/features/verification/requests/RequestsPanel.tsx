import { AlarmClock, Building2, Globe2, ScanFace, X } from 'lucide-react';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { dateTime, label } from '@/lib/format';
import { verificationRequestTone } from '@/lib/status';
import { toParams } from '@/lib/useSearchState';
import { useVerificationRequestSummary, useVerificationRequests } from './api';
import { RequestDrawer } from './RequestDrawer';

const OPEN = ['pending', 'in_progress', 'additional_info_required', 'escalated'];

interface Filters {
  rq: string;
  rstatus: string;
  pathway: string;
  rpage: string;
  selected: string;
}

/** Verification request queue: every re-verification from trigger to documented decision. */
export function RequestsPanel({ filters, setFilters }: { filters: Filters; setFilters: (patch: Partial<Filters>) => void }) {
  const summary = useVerificationRequestSummary();
  const status = filters.rstatus === 'open' ? OPEN : filters.rstatus ? [filters.rstatus] : [];
  const params = { ...toParams({ q: filters.rq, pathway: filters.pathway, page: filters.rpage }), page_size: '15', ...(status.length ? { status } : {}) };
  const { data, isLoading, isFetching, error, refetch } = useVerificationRequests(params);
  const s = summary.data;
  const filtered = Boolean(filters.rq || filters.rstatus || filters.pathway);

  return (
    <>
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Open requests" value={s?.open ?? '—'} icon={<ScanFace className="size-4" />} loading={summary.isLoading} />
        <StatCard label="On-campus visits" value={s?.by_pathway.on_campus ?? 0} footnote="Student services verification office" icon={<Building2 className="size-4" />} accent="blue" loading={summary.isLoading} />
        <StatCard label="Remote / international" value={s?.by_pathway.remote ?? 0} footnote="Video, documents, provider checks" icon={<Globe2 className="size-4" />} accent="navy" loading={summary.isLoading} />
        <StatCard label="Overdue" value={s?.overdue ?? '—'} footnote={s && `${s.by_status.verified ?? 0} verified · ${s.by_status.failed ?? 0} failed`} icon={<AlarmClock className="size-4" />} accent="warning" loading={summary.isLoading} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="Search VRQ-, STU- or SFA-" label="Search verification requests" value={filters.rq} onChange={(rq) => setFilters({ rq, rpage: '1' })} />
          </div>
          <Select aria-label="Status" value={filters.rstatus} onChange={(e) => setFilters({ rstatus: e.target.value, rpage: '1' })} className="w-[calc(50%-0.25rem)] sm:w-48">
            <option value="">Status: all</option>
            <option value="open">Open (needs action)</option>
            {['pending', 'in_progress', 'verified', 'failed', 'escalated', 'additional_info_required'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Pathway" value={filters.pathway} onChange={(e) => setFilters({ pathway: e.target.value, rpage: '1' })} className="w-[calc(50%-0.25rem)] sm:w-40">
            <option value="">Pathway: all</option>
            <option value="on_campus">On campus</option>
            <option value="remote">Remote</option>
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={() => setFilters({ rq: '', rstatus: '', pathway: '', rpage: '1' })}>Clear filters</Button>}
        </div>
        {isLoading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<ScanFace className="size-5" />} title="No verification requests" description={filtered ? 'Nothing matches these filters.' : 'Requests appear when a card is reported lost, an officer asks, or combined risk is high.'} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead><tr><TH>Request</TH><TH>Student</TH><TH>Trigger</TH><TH>Pathway</TH><TH>Status</TH><TH>Due</TH><TH>Opened</TH></tr></THead>
              <tbody>
                {data.items.map((r) => (
                  <TR key={r.id} onClick={() => setFilters({ selected: r.id })}>
                    <TD>
                      <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); setFilters({ selected: r.id }); }}>{r.reference}</button>
                      <div className="font-mono text-[11px] text-slate-500">{r.account_ref}</div>
                    </TD>
                    <TD><span className="font-mono text-xs">{r.student.student_ref}</span><p className="text-xs text-slate-500">{r.student.masked_name}</p></TD>
                    <TD className="text-xs">{label(r.trigger)}</TD>
                    <TD><Badge tone="navy">{label(r.pathway)}</Badge>{r.method && <p className="mt-1 text-[11px] text-slate-500">{label(r.method)}</p>}</TD>
                    <TD><StatusBadge value={r.status} map={verificationRequestTone} /></TD>
                    <TD className="tabular text-xs whitespace-nowrap">{OPEN.includes(r.status) ? dateTime(r.due_at) : '—'}</TD>
                    <TD className="tabular text-xs whitespace-nowrap text-slate-500">{dateTime(r.created_at)}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ rpage: String(p) })} />
          </div>
        )}
      </Card>
      <RequestDrawer id={filters.selected || null} onClose={() => setFilters({ selected: '' })} />
    </>
  );
}
