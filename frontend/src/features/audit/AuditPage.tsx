import { CheckCircle2, Link2, Lock, ScrollText, ShieldX, X, XCircle } from 'lucide-react';
import { Fragment, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { errorMessage } from '@/lib/api';
import { dateTime, label } from '@/lib/format';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useAuditEvents, useAuditSummary, useVerifyChain } from './api';

const DEFAULTS = { q: '', category: '', outcome: '', page: '1' };
const CATEGORIES = ['account', 'card', 'transaction', 'security', 'verification', 'investigation', 'data_access', 'authentication', 'permission', 'detection', 'disbursement', 'application', 'system'];
const outcomeTone = { success: 'success', failure: 'critical', denied: 'warning' } as const;

export default function AuditPage() {
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const summary = useAuditSummary();
  const { data, isLoading, isFetching, error, refetch } = useAuditEvents({ ...toParams(filters), page_size: '30' });
  const verify = useVerifyChain();
  const [open, setOpen] = useState<string | null>(null);
  const filtered = Boolean(filters.q || filters.category || filters.outcome);
  const s = summary.data;
  const result = verify.data;

  const runVerify = () =>
    verify.mutate(undefined, {
      onSuccess: (r) =>
        r.valid
          ? toast.success('Audit chain intact', { description: `${r.events_checked.toLocaleString()} events verified` })
          : toast.error('Audit chain broken', { description: `First inconsistency at event #${r.first_broken_sequence}` }),
      onError: (err) => toast.error('Verification failed', { description: errorMessage(err) }),
    });

  return (
    <>
      <PageHeader
        title="Audit logs"
        description="Append-only, hash-chained record of every sensitive action: account access, card blocks and replacements, verification steps, alert and case decisions, permission denials. Application users cannot edit or delete entries; database triggers reject it."
        actions={<Button variant="secondary" icon={<Link2 className="size-4" />} loading={verify.isPending} onClick={runVerify}>Verify chain integrity</Button>}
        meta={
          result && (
            <Badge tone={result.valid ? 'success' : 'critical'} icon={result.valid ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}>
              {result.valid ? `Chain verified · ${result.events_checked.toLocaleString()} events · ${dateTime(result.verified_at)}` : `Broken at #${result.first_broken_sequence}`}
            </Badge>
          )
        }
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Audit events in scope" value={s ? s.total_events.toLocaleString() : '—'} icon={<ScrollText className="size-4" />} loading={summary.isLoading} />
        <StatCard label="Account & card actions" value={s ? (s.by_category.account ?? 0) + (s.by_category.card ?? 0) : '—'} icon={<Lock className="size-4" />} accent="blue" loading={summary.isLoading} to="/app/audit?category=card" />
        <StatCard label="Permission denials (7 d)" value={s?.denied_last_7_days ?? '—'} icon={<ShieldX className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/audit?outcome=denied" />
        <StatCard label="Failed sign-ins (7 d)" value={s?.failed_logins_last_7_days ?? '—'} icon={<XCircle className="size-4" />} accent="critical" loading={summary.isLoading} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-72"><SearchInput placeholder="Action, actor email or reference" label="Search audit events" value={filters.q} onChange={(q) => setFilters({ q })} /></div>
          <Select aria-label="Category" value={filters.category} onChange={(e) => setFilters({ category: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-44">
            <option value="">Category: all</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </Select>
          <Select aria-label="Outcome" value={filters.outcome} onChange={(e) => setFilters({ outcome: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
            <option value="">Outcome: all</option>
            {['success', 'failure', 'denied'].map((o) => <option key={o} value={o}>{label(o)}</option>)}
          </Select>
          {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
        </div>
        {isLoading ? <TableSkeleton rows={12} cols={6} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data || data.items.length === 0 ? (
          <EmptyState icon={<ScrollText className="size-5" />} title="No audit events match" />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead><tr><TH>#</TH><TH>When</TH><TH>Actor</TH><TH>Action</TH><TH>Target</TH><TH>Outcome</TH></tr></THead>
              <tbody>
                {data.items.map((e) => (
                  <Fragment key={e.id}>
                    <TR onClick={() => setOpen(open === e.id ? null : e.id)}>
                      <TD className="tabular text-xs text-slate-500">{e.sequence}</TD>
                      <TD className="tabular whitespace-nowrap text-xs">{dateTime(e.occurred_at)}</TD>
                      <TD className="text-xs"><span className="block max-w-56 truncate">{e.actor_email ?? 'system'}</span><span className="text-slate-500">{e.actor_role ? label(e.actor_role) : ''}</span></TD>
                      <TD><code className="text-xs">{e.action}</code><span className="block text-[11px] text-slate-500">{label(e.category)}</span></TD>
                      <TD className="text-xs">{e.target_ref ?? e.target_type ?? '—'}</TD>
                      <TD><Badge tone={outcomeTone[e.outcome as keyof typeof outcomeTone] ?? 'neutral'}>{label(e.outcome)}</Badge></TD>
                    </TR>
                    {open === e.id && (
                      <tr className="bg-slate-50/70">
                        <td colSpan={6} className="px-4 py-3">
                          <pre className="max-h-48 overflow-auto rounded-lg bg-white p-3 text-[11px] leading-relaxed text-slate-700 ring-1 ring-slate-200">{JSON.stringify(e.details, null, 2)}</pre>
                          <p className="mt-2 font-mono text-[10px] break-all text-slate-500">hash {e.hash} · prev {e.prev_hash}</p>
                        </td>
                      </tr>
                    )}
                  </Fragment>
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
