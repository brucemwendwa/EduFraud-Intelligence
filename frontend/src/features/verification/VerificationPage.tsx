import { Fingerprint, FlaskConical, Lock, ScanFace, ShieldAlert, ShieldCheck, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Drawer } from '@/components/ui/Dialog';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { CardSkeleton, EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { verificationStatusTone } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useProviderInfo, useVerification, useVerificationStats, useVerifications } from './api';
import { VerificationResult } from './VerificationResult';
import { VerificationWizard } from './VerificationWizard';

const DEFAULTS = { status: '', trigger: '', q: '', page: '1', selected: '' };

export default function VerificationPage() {
  const { can } = useAuth();
  const [filters, setFilters] = useSearchState(DEFAULTS);
  const [wizard, setWizard] = useState(false);
  const { selected, ...rest } = filters;
  const list = useVerifications({ ...toParams(rest), page_size: '15' });
  const stats = useVerificationStats();
  const provider = useProviderInfo();
  const s = stats.data;

  return (
    <>
      <PageHeader
        title="Identity verification"
        description="Step-up checks protect accounts at risky moments, such as refund destination changes, account recovery and new devices. Students without biometric consent are verified in person instead."
        meta={<Badge tone="blue" icon={<FlaskConical className="size-3" />}>Simulated biometric provider</Badge>}
        actions={can(P.verificationsInitiate) && <Button icon={<Fingerprint className="size-4" />} onClick={() => setWizard(true)}>Start verification</Button>}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Verifications" value={s?.total ?? '—'} footnote={s?.biometric_share != null ? `${Math.round(s.biometric_share * 100)}% biometric` : undefined} icon={<ScanFace className="size-4" />} loading={stats.isLoading} />
        <StatCard label="Pass rate (decided)" value={s?.pass_rate != null ? `${Math.round(s.pass_rate * 100)}%` : '—'} footnote={s && `${s.passed} passed`} icon={<UserCheck className="size-4" />} accent="success" loading={stats.isLoading} />
        <StatCard label="Failed" value={s?.failed ?? '—'} footnote={s && `${s.review} inconclusive`} icon={<ShieldAlert className="size-4" />} accent="critical" loading={stats.isLoading} to="/app/verification?status=failed" />
        <StatCard label="Presentation attacks caught" value={s?.attacks_detected ?? '—'} footnote="Printed photos, screen replays" icon={<ShieldCheck className="size-4" />} accent="warning" loading={stats.isLoading} />
      </div>

      <div className="space-y-6">
        <PrivacyCard />
        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
            <div className="w-full sm:w-64">
              <SearchInput placeholder="Search IDV-, FA- or STU-" label="Search verifications" value={filters.q} onChange={(q) => setFilters({ q })} />
            </div>
            <Select aria-label="Result" value={filters.status} onChange={(e) => setFilters({ status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-36">
              <option value="">Result: all</option>
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
              <option value="review">Inconclusive</option>
            </Select>
            <Select aria-label="Trigger" value={filters.trigger} onChange={(e) => setFilters({ trigger: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-56">
              <option value="">Trigger: all</option>
              {(provider.data?.triggers ?? []).map((t) => <option key={t} value={t}>{label(t)}</option>)}
            </Select>
          </div>
          {list.isLoading ? (
            <TableSkeleton rows={6} cols={6} />
          ) : list.error ? (
            <ErrorState error={list.error} onRetry={() => list.refetch()} />
          ) : !list.data || list.data.items.length === 0 ? (
            <EmptyState icon={<ScanFace className="size-5" />} title="No verifications match" />
          ) : (
            <>
              <Table>
                <THead><tr><TH>Verification</TH><TH>Student</TH><TH>Trigger</TH><TH>Method</TH><TH>Face match</TH><TH>Result</TH><TH>When</TH></tr></THead>
                <tbody>
                  {list.data.items.map((v) => (
                    <TR key={v.id} onClick={() => setFilters({ selected: v.id, page: filters.page })}>
                      <TD className="whitespace-nowrap">
                        <button type="button" className="font-medium text-slate-900 hover:text-brand-blue" onClick={(e) => { e.stopPropagation(); setFilters({ selected: v.id, page: filters.page }); }}>
                          {v.reference}
                        </button>
                        <div className="font-mono text-[11px] text-slate-500">{v.application_ref}</div>
                      </TD>
                      <TD><span className="font-mono text-xs">{v.student.student_ref}</span></TD>
                      <TD className="text-xs">{label(v.trigger)}</TD>
                      <TD className="text-xs">{label(v.method)}</TD>
                      <TD className="tabular">{v.face_match_score != null ? v.face_match_score.toFixed(2) : '—'}</TD>
                      <TD>
                        <StatusBadge value={v.status} map={verificationStatusTone} />
                        {v.pad_attack_type && <div className="mt-1 text-[11px] font-medium text-red-700">{label(v.pad_attack_type)}</div>}
                      </TD>
                      <TD className="whitespace-nowrap text-xs text-slate-500">{dateTime(v.created_at)}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
              <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => setFilters({ page: String(p) })} />
            </>
          )}
        </Card>

      </div>

      <VerificationDrawer id={selected || null} onClose={() => setFilters({ selected: '', page: filters.page })} />
      <VerificationWizard open={wizard} onOpenChange={setWizard} />
    </>
  );
}

function PrivacyCard() {
  const provider = useProviderInfo();
  return (
    <Card>
      <CardHeader title="Privacy by design" description={provider.data?.name} icon={<Lock className="size-4" />} />
      <CardBody>
        {provider.isLoading ? (
          <CardSkeleton />
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr_auto]">
            <p className="rounded-lg bg-blue-50 p-3 text-xs leading-relaxed text-blue-900 ring-1 ring-blue-100">{provider.data?.disclaimer}</p>
            <ul className="space-y-2">
              {provider.data?.data_handling.map((d) => (
                <li key={d} className="flex gap-2 text-sm text-slate-700"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />{d}</li>
              ))}
            </ul>
            <dl className="grid grid-cols-3 gap-2 text-center text-xs lg:w-64 lg:grid-cols-1">
              {Object.entries(provider.data?.thresholds ?? {}).map(([k, v]) => (
                <div key={k} className="rounded-lg bg-slate-50 p-2">
                  <dt className="text-slate-500">{label(k)} threshold</dt>
                  <dd className="tabular mt-0.5 font-semibold text-slate-900">{v.toFixed(2)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function VerificationDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data, isLoading, error, refetch } = useVerification(id);
  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={data?.reference ?? 'Verification'} description={data ? `${data.organization.name} · ${data.student.student_ref}` : undefined}>
      {isLoading ? <CardSkeleton /> : error || !data ? <ErrorState error={error} onRetry={() => refetch()} /> : <VerificationResult v={data} />}
    </Drawer>
  );
}
