import { ArrowLeftRight, Ban, ClipboardCheck, ShieldAlert, X } from 'lucide-react';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { LocationText } from '@/components/ui/Location';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, SortableTH, TD, TH, THead, TR, Table, type SortDir } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { dateTime, label, money } from '@/lib/format';
import { transactionReviewTone, transactionStatusTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useTransactionSummary, useTransactions } from './api';
import { TransactionDrawer } from './TransactionDrawer';

const DEFAULTS = { q: '', flagged: '', risk_level: '', status: '', review_status: '', category: '', indicator: '', sort: 'occurred_at', direction: 'desc', page: '1', selected: '' };
const CATEGORIES = ['dining', 'groceries', 'bookstore', 'transport', 'campus_services', 'health', 'fuel', 'cash_withdrawal', 'subscriptions', 'electronics', 'gift_cards', 'money_transfer', 'crypto_exchange', 'retail'];
const INDICATORS: Record<string, string> = {
  UNUSUAL_LOCATION: 'Unusual location',
  IMPOSSIBLE_TRAVEL: 'Implausible travel',
  SPENDING_SPIKE: 'Spending spike',
  HIGH_RISK_CATEGORY_NEW: 'New high-risk category',
  RAPID_SEQUENCE: 'Burst of transactions',
  TXN_AFTER_SUSPICIOUS_AUTH: 'After suspicious sign-in',
  TXN_AFTER_CARD_LOST: 'Card used after reported lost',
  DESTINATION_SHARED_ACCOUNTS: 'Shared destination',
};

export default function TransactionsPage() {
  const { user, activeOrgId } = useAuth();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const { selected, ...rest } = filters;
  const summary = useTransactionSummary();
  const { data, isLoading, isFetching, error, refetch } = useTransactions({ ...toParams(rest), page_size: '25' });
  const showInstitution = Boolean(user?.is_platform_admin && !activeOrgId);
  const filtered = Boolean(filters.q || filters.flagged || filters.risk_level || filters.status || filters.review_status || filters.category || filters.indicator);
  const s = summary.data;
  const onSort = (field: string) =>
    setFilters({ sort: field, direction: filters.sort === field && filters.direction === 'desc' ? 'asc' : 'desc' });

  return (
    <>
      <PageHeader
        title="Transaction intelligence"
        description="Authorised transaction events from the payment provider, each judged against the student's own pattern. Indicators explain every flag; lack of spending or a new place alone is never treated as fraud."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Transactions (30 days)" value={s ? s.total.toLocaleString() : '—'} footnote={s && `${money(s.amount_total)} approved`} icon={<ArrowLeftRight className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Flagged (medium+)" value={s?.flagged ?? '—'} icon={<ShieldAlert className="size-4" />} accent="critical" loading={summary.isLoading} to="/app/transactions?flagged=true&sort=risk_score" />
        <StatCard label="Awaiting review" value={s?.unreviewed_flagged ?? '—'} footnote="Flagged, no human decision yet" icon={<ClipboardCheck className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/transactions?flagged=true&review_status=unreviewed" />
        <StatCard label="Declined by provider" value={s?.declined ?? '—'} footnote="Blocked card or held money movement" icon={<Ban className="size-4" />} accent="blue" loading={summary.isLoading} to="/app/transactions?status=declined" />
      </div>
      {s && Object.keys(s.by_indicator).length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span className="font-medium">Top indicators (30 days):</span>
          {Object.entries(s.by_indicator).map(([k, v]) => <Badge key={k} tone="neutral">{k} · {v}</Badge>)}
        </div>
      )}
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="TXN-, SFA-, STU- or merchant" label="Search transactions" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Flagged" value={filters.flagged} onChange={(e) => setFilters({ flagged: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
            <option value="">Risk: all</option>
            <option value="true">Flagged only</option>
            <option value="false">Not flagged</option>
          </Select>
          <Select aria-label="Risk level" value={filters.risk_level} onChange={(e) => setFilters({ risk_level: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
            <option value="">Level: all</option>
            {['critical', 'high', 'medium', 'low'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Indicator" value={filters.indicator} onChange={(e) => setFilters({ indicator: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-52">
            <option value="">Indicator: all</option>
            {Object.entries(INDICATORS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select aria-label="Category" value={filters.category} onChange={(e) => setFilters({ category: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Category: all</option>
            {CATEGORIES.map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Status" value={filters.status} onChange={(e) => setFilters({ status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
            <option value="">Status: all</option>
            {['approved', 'declined', 'pending', 'reversed'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Review" value={filters.review_status} onChange={(e) => setFilters({ review_status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-40">
            <option value="">Review: all</option>
            {['unreviewed', 'cleared', 'suspicious'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>
        {isLoading ? (
          <TableSkeleton rows={10} cols={8} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<ArrowLeftRight className="size-5" />} title="No transactions match these filters" action={filtered ? <Button variant="secondary" size="sm" onClick={reset}>Clear filters</Button> : undefined} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr>
                  <TH>Transaction</TH>
                  <TH>Student</TH>
                  {showInstitution && <TH>Institution</TH>}
                  <TH>Merchant</TH>
                  <SortableTH label="Amount" field="amount" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} className="text-right" />
                  <SortableTH label="Date & time" field="occurred_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Location</TH>
                  <TH>Status</TH>
                  <SortableTH label="Risk" field="risk_score" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Indicators</TH>
                </tr>
              </THead>
              <tbody>
                {data.items.map((t) => (
                  <TR key={t.id} onClick={() => setFilters({ selected: t.id, page: filters.page })}>
                    <TD>
                      <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); setFilters({ selected: t.id, page: filters.page }); }}>{t.reference}</button>
                      <p className="font-mono text-[11px] text-slate-500">{t.account_ref}</p>
                    </TD>
                    <TD><span className="font-mono text-xs">{t.student.student_ref}</span></TD>
                    {showInstitution && <TD className="text-xs">{t.organization.name}</TD>}
                    <TD><span className="block max-w-44 truncate text-sm">{t.merchant_name}</span><span className="text-xs text-slate-500">{label(t.merchant_category)}</span></TD>
                    <TD className="tabular text-right font-medium text-slate-900">{money(t.amount, true)}</TD>
                    <TD className="tabular whitespace-nowrap text-xs">{dateTime(t.occurred_at)}</TD>
                    <TD className="text-xs"><LocationText location={t.location} restricted={t.location_restricted} /></TD>
                    <TD>
                      <span className="flex flex-col items-start gap-1">
                        <StatusBadge value={t.status} map={transactionStatusTone} />
                        {t.review_status !== 'unreviewed' && <StatusBadge value={t.review_status} map={transactionReviewTone} />}
                      </span>
                    </TD>
                    <TD>{t.risk_level && t.risk_level !== 'low' ? <RiskBadge level={t.risk_level as RiskLevel} score={t.risk_score} /> : <span className="text-xs text-slate-400">Low</span>}</TD>
                    <TD className="max-w-56 text-xs text-slate-600">{t.indicators.length ? t.indicators.slice(0, 2).map((i) => i.title).join(' · ') : '—'}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
      <TransactionDrawer id={selected || null} onClose={() => setFilters({ selected: '', page: filters.page })} />
    </>
  );
}
