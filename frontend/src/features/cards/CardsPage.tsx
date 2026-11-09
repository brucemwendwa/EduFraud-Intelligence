import { Ban, CreditCard, PackageCheck, Siren, X } from 'lucide-react';
import { Link } from 'react-router';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, SortableTH, TD, TH, THead, TR, Table, type SortDir } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { date, dateTime, label } from '@/lib/format';
import { cardStatusTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useCardSummary, useCards } from './api';
import { CardDrawer } from './CardDrawer';

const DEFAULTS = { q: '', status: '', sort: 'issued_at', direction: 'desc', page: '1', selected: '' };

export default function CardsPage() {
  const { user, activeOrgId } = useAuth();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const { selected, ...rest } = filters;
  const summary = useCardSummary();
  const { data, isLoading, isFetching, error, refetch } = useCards({ ...toParams(rest), page_size: '20' });
  const showInstitution = Boolean(user?.is_platform_admin && !activeOrgId);
  const filtered = Boolean(filters.q || filters.status);
  const s = summary.data?.by_status;
  const onSort = (field: string) =>
    setFilters({ sort: field, direction: filters.sort === field && filters.direction === 'desc' ? 'asc' : 'desc' });

  return (
    <>
      <PageHeader
        title="Student ID card management"
        description="University ID cards are the credential students use to access their provider-held aid. Blocks and replacements are requested from the payment provider and recorded with its acknowledgement; a blocked card is never re-activated here."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Active cards" value={s?.active ?? '—'} icon={<CreditCard className="size-4" />} loading={summary.isLoading} to="/app/cards?status=active" />
        <StatCard label="Reported lost" value={s?.reported_lost ?? 0} footnote="Awaiting provider block" icon={<Siren className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/cards?status=reported_lost" />
        <StatCard label="Blocked at provider" value={s?.blocked ?? 0} icon={<Ban className="size-4" />} accent="critical" loading={summary.isLoading} to="/app/cards?status=blocked" />
        <StatCard label="Replacements requested" value={s?.replacement_requested ?? 0} footnote="Issued after identity verification" icon={<PackageCheck className="size-4" />} accent="blue" loading={summary.isLoading} to="/app/cards?status=replacement_requested" />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="Search CRD-, STU- or SFA-" label="Search cards" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Card status" value={filters.status} onChange={(e) => setFilters({ status: e.target.value })} className="w-full sm:w-52">
            <option value="">Status: all</option>
            {['active', 'reported_lost', 'blocked', 'replacement_requested', 'replaced'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>
        {isLoading ? (
          <TableSkeleton rows={8} cols={6} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<CreditCard className="size-5" />} title="No cards match these filters" action={filtered ? <Button variant="secondary" size="sm" onClick={reset}>Clear filters</Button> : undefined} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr>
                  <SortableTH label="Card" field="reference" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Student</TH>
                  {showInstitution && <TH>Institution</TH>}
                  <TH>Linked account</TH>
                  <TH>Status</TH>
                  <SortableTH label="Issued" field="issued_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <SortableTH label="Reported lost" field="reported_lost_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Provider acknowledgement</TH>
                </tr>
              </THead>
              <tbody>
                {data.items.map((c) => (
                  <TR key={c.id} onClick={() => setFilters({ selected: c.id, page: filters.page })}>
                    <TD>
                      <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); setFilters({ selected: c.id, page: filters.page }); }}>{c.reference}</button>
                      <code className="block text-xs text-slate-500">{c.masked_number}</code>
                    </TD>
                    <TD><span className="font-mono text-xs">{c.student.student_ref}</span><p className="text-xs text-slate-500">{c.student.masked_name}</p></TD>
                    {showInstitution && <TD className="text-xs">{c.organization.name}</TD>}
                    <TD>{c.account_id ? <Link className="font-mono text-xs text-brand-blue hover:underline" to={`/app/accounts/${c.account_id}`} onClick={(e) => e.stopPropagation()}>{c.account_ref}</Link> : <span className="text-xs text-slate-400">Not linked</span>}</TD>
                    <TD><StatusBadge value={c.status} map={cardStatusTone} /></TD>
                    <TD className="tabular text-xs">{date(c.issued_at)}</TD>
                    <TD className="tabular text-xs">{c.reported_lost_at ? dateTime(c.reported_lost_at) : '—'}</TD>
                    <TD className="text-xs text-slate-500">{c.block_confirmation ?? '—'}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
      <CardDrawer id={selected || null} onClose={() => setFilters({ selected: '', page: filters.page })} />
    </>
  );
}
