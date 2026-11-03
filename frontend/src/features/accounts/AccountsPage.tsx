import { Lock, ShieldAlert, Wallet, WalletCards, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, SortableTH, TD, TH, THead, TR, Table, type SortDir } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { date, label, money } from '@/lib/format';
import { accountStatusTone, cardStatusTone, verificationRequestTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useAccountSummary, useAccounts } from './api';

const DEFAULTS = {
  q: '',
  status: '',
  risk_level: '',
  card_status: '',
  verification_status: '',
  restricted: '',
  sort: 'risk_score',
  direction: 'desc',
  page: '1',
};

export default function AccountsPage() {
  const navigate = useNavigate();
  const { user, activeOrgId } = useAuth();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const summary = useAccountSummary();
  const { data, isLoading, isFetching, error, refetch } = useAccounts({ ...toParams(filters), page_size: '20' });
  const showInstitution = Boolean(user?.is_platform_admin && !activeOrgId);
  const filtered = Boolean(filters.q || filters.status || filters.risk_level || filters.card_status || filters.verification_status || filters.restricted);
  const s = summary.data;
  const onSort = (field: string) =>
    setFilters({ sort: field, direction: filters.sort === field && filters.direction === 'desc' ? 'asc' : 'desc' });

  return (
    <>
      <PageHeader
        title="Student financial aid accounts"
        description="Aid is held by the payment-provider partner in an account the student unlocks with their university ID card. EduShield monitors these accounts; it never holds funds or card credentials."
        meta={<Badge tone="blue">Provider: sandbox (simulated)</Badge>}
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="ID-linked accounts" value={s ? s.total.toLocaleString() : '—'} footnote={s && `${s.by_status.active ?? 0} active`} icon={<WalletCards className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Aid allocated" value={s ? money(s.allocated_total) : '—'} footnote="Credited or scheduled to accounts" icon={<Wallet className="size-4" />} accent="success" loading={summary.isLoading} to="/app/disbursements" />
        <StatCard label="Sensitive actions on hold" value={s?.restricted ?? '—'} footnote="Spending continues; changes need verification" icon={<Lock className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/accounts?restricted=true" />
        <StatCard label="High or critical risk" value={s ? (s.by_risk.high ?? 0) + (s.by_risk.critical ?? 0) : '—'} footnote={s && `${s.verification_open} verification request(s) open`} icon={<ShieldAlert className="size-4" />} accent="critical" loading={summary.isLoading} to="/app/accounts?risk_level=critical" />
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput placeholder="Search SFA-, STU- or CRD- reference" label="Search accounts" value={filters.q} onChange={(q) => setFilters({ q })} />
          </div>
          <Select aria-label="Account status" value={filters.status} onChange={(e) => setFilters({ status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Status: all</option>
            {['active', 'pending_verification', 'restricted', 'suspended', 'closed'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Risk level" value={filters.risk_level} onChange={(e) => setFilters({ risk_level: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
            <option value="">Risk: all</option>
            {['critical', 'high', 'medium', 'low'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Card status" value={filters.card_status} onChange={(e) => setFilters({ card_status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Card: all</option>
            {['active', 'reported_lost', 'blocked', 'replacement_requested', 'replaced'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          <Select aria-label="Verification" value={filters.verification_status} onChange={(e) => setFilters({ verification_status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-52">
            <option value="">Verification: all</option>
            {['not_required', 'pending', 'in_progress', 'verified', 'failed', 'escalated', 'additional_info_required'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>

        {isLoading ? (
          <TableSkeleton rows={8} cols={7} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState icon={<WalletCards className="size-5" />} title="No accounts match these filters" action={filtered ? <Button variant="secondary" size="sm" onClick={reset}>Clear filters</Button> : undefined} />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr>
                  <SortableTH label="Account" field="reference" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Student</TH>
                  {showInstitution && <TH>Institution</TH>}
                  <TH>ID card</TH>
                  <TH>Status</TH>
                  <SortableTH label="Allocated" field="allocated_total" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} className="text-right" />
                  <TH className="text-right">Balance</TH>
                  <SortableTH label="Last activity" field="last_transaction_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Verification</TH>
                  <SortableTH label="Risk" field="risk_score" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                </tr>
              </THead>
              <tbody>
                {data.items.map((a) => (
                  <TR key={a.id} onClick={() => navigate(`/app/accounts/${a.id}`)}>
                    <TD>
                      <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); navigate(`/app/accounts/${a.id}`); }}>
                        {a.reference}
                      </button>
                      <p className="mt-0.5 max-w-48 truncate text-xs text-slate-500" title={a.department ?? undefined}>{a.department ?? '—'}</p>
                    </TD>
                    <TD>
                      <span className="font-mono text-xs">{a.student.student_ref}</span>
                      <p className="text-xs text-slate-500">{a.student.masked_name}</p>
                    </TD>
                    {showInstitution && <TD className="text-xs">{a.organization.name}</TD>}
                    <TD>
                      {a.card ? (
                        <span className="flex flex-col gap-1">
                          <code className="text-xs">{a.card.masked_number}</code>
                          {a.card.status !== 'active' && <StatusBadge value={a.card.status} map={cardStatusTone} />}
                        </span>
                      ) : <span className="text-xs text-slate-400">No card linked</span>}
                    </TD>
                    <TD>
                      <span className="flex flex-col items-start gap-1">
                        <StatusBadge value={a.status} map={accountStatusTone} />
                        {a.sensitive_actions_restricted && a.status !== 'restricted' && <Badge tone="warning">Changes on hold</Badge>}
                      </span>
                    </TD>
                    <TD className="tabular text-right font-medium text-slate-900">{money(a.allocated_total)}</TD>
                    <TD className="tabular text-right text-slate-600">{a.available_balance != null ? money(a.available_balance) : '—'}</TD>
                    <TD className="tabular whitespace-nowrap text-xs">{date(a.last_transaction_at)}</TD>
                    <TD><StatusBadge value={a.verification_status} map={verificationRequestTone} /></TD>
                    <TD>{a.risk_level ? <RiskBadge level={a.risk_level as RiskLevel} score={a.risk_score} /> : <span className="text-xs text-slate-400">Not scored</span>}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
    </>
  );
}
