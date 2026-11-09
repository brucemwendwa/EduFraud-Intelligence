import { KeyRound, Laptop, ShieldAlert, ShieldCheck, Smartphone, UserX, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { DeviceOut } from '@/api/types';
import { IndicatorList } from '@/components/risk/IndicatorList';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog, Drawer } from '@/components/ui/Dialog';
import { Detail, DetailList, SectionTitle } from '@/components/ui/DetailList';
import { Select } from '@/components/ui/Field';
import { LocationText } from '@/components/ui/Location';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatCard } from '@/components/ui/StatCard';
import { CardSkeleton, EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { decisionTone, deviceTrustTone, securityEventLabel } from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useDevices, useSecurityEvent, useSecurityEvents, useSecuritySummary, useSetDeviceTrust } from './api';

const DEFAULTS = { tab: 'events', q: '', event_type: '', elevated: '', trust_status: '', shared: '', page: '1', selected: '' };

export default function AccessPage() {
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const summary = useSecuritySummary();
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Device & access intelligence"
        description="Sign-ins, devices, password resets and account-recovery events reported by the identity provider. A new phone or laptop alone is not suspicious: EduShield asks for additional authentication and only holds sensitive changes when several signals combine."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="New-device sign-ins (30 d)" value={s?.new_devices ?? '—'} icon={<Smartphone className="size-4" />} loading={summary.isLoading} to="/app/access?event_type=new_device_login" />
        <StatCard label="Failed sign-ins (30 d)" value={s?.failed_logins ?? '—'} icon={<UserX className="size-4" />} accent="warning" loading={summary.isLoading} to="/app/access?event_type=login_failed" />
        <StatCard label="Resets & recovery requests" value={s?.password_resets ?? '—'} icon={<KeyRound className="size-4" />} accent="blue" loading={summary.isLoading} to="/app/access?event_type=password_reset_requested" />
        <StatCard label="Devices shared across accounts" value={s?.shared_devices ?? '—'} footnote={s && `${s.elevated_events} elevated events`} icon={<ShieldAlert className="size-4" />} accent="critical" loading={summary.isLoading} to="/app/access?tab=devices&shared=true" />
      </div>
      <Card>
        <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4 pt-2" role="tablist" aria-label="Access views">
          {[{ key: 'events', label: 'Security events' }, { key: 'devices', label: 'Devices' }].map((t) => (
            <button key={t.key} role="tab" aria-selected={filters.tab === t.key} onClick={() => setFilters({ tab: t.key, selected: '' })}
              className={cn('-mb-px border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors',
                filters.tab === t.key ? 'border-navy-900 text-navy-900' : 'border-transparent text-slate-500 hover:text-slate-800')}>
              {t.label}
            </button>
          ))}
        </div>
        {filters.tab === 'devices' ? <DevicesTab filters={filters} setFilters={setFilters} reset={reset} /> : <EventsTab filters={filters} setFilters={setFilters} reset={reset} />}
      </Card>
      <EventDrawer id={filters.tab === 'events' ? filters.selected || null : null} onClose={() => setFilters({ selected: '', page: filters.page })} />
    </>
  );
}

type TabProps = { filters: typeof DEFAULTS; setFilters: (p: Partial<typeof DEFAULTS>) => void; reset: () => void };

function EventsTab({ filters, setFilters, reset }: TabProps) {
  const { q, event_type, elevated, page } = filters;
  const { data, isLoading, isFetching, error, refetch } = useSecurityEvents({ ...toParams({ q, event_type, elevated, page }), page_size: '25' });
  const filtered = Boolean(q || event_type || elevated);
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
        <div className="w-full sm:w-64"><SearchInput placeholder="SEV-, SFA- or STU-" label="Search events" value={q} onChange={(v) => setFilters({ q: v })} /></div>
        <Select aria-label="Event type" value={event_type} onChange={(e) => setFilters({ event_type: e.target.value })} className="w-full sm:w-64">
          <option value="">Event: all</option>
          {Object.entries(securityEventLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select aria-label="Risk" value={elevated} onChange={(e) => setFilters({ elevated: e.target.value })} className="w-full sm:w-44">
          <option value="">Risk: all</option>
          <option value="true">Elevated (medium+)</option>
          <option value="false">Low</option>
        </Select>
        {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
      </div>
      {isLoading ? <TableSkeleton rows={10} cols={7} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data || data.items.length === 0 ? (
        <EmptyState icon={<ShieldCheck className="size-5" />} title="No security events match" />
      ) : (
        <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
          <Table>
            <THead><tr><TH>Event</TH><TH>Student</TH><TH>Device</TH><TH>Location</TH><TH>When</TH><TH>Outcome</TH><TH>Decision</TH><TH>Account risk</TH></tr></THead>
            <tbody>
              {data.items.map((e) => (
                <TR key={e.id} onClick={() => setFilters({ selected: e.id, page })}>
                  <TD>
                    <button type="button" className="text-left text-sm font-medium text-slate-900 hover:text-brand-blue" onClick={(ev) => { ev.stopPropagation(); setFilters({ selected: e.id, page }); }}>{securityEventLabel[e.event_type] ?? label(e.event_type)}</button>
                    <p className="font-mono text-[11px] text-slate-500">{e.reference}</p>
                  </TD>
                  <TD><span className="font-mono text-xs">{e.student.student_ref}</span><p className="font-mono text-[11px] text-slate-500">{e.account_ref}</p></TD>
                  <TD className="text-xs">{e.device ? <span className="flex flex-col gap-1">{e.device.label}<StatusBadge value={e.device.trust_status} map={deviceTrustTone} /></span> : '—'}</TD>
                  <TD className="text-xs"><LocationText location={e.location} restricted={e.location_restricted} /></TD>
                  <TD className="tabular whitespace-nowrap text-xs">{dateTime(e.occurred_at)}</TD>
                  <TD className="text-xs">{label(e.outcome)}</TD>
                  <TD>{e.decision ? <StatusBadge value={e.decision} map={decisionTone} /> : <span className="text-xs text-slate-400">—</span>}</TD>
                  <TD>{e.risk_level ? <RiskBadge level={e.risk_level as RiskLevel} score={e.risk_score} /> : <span className="text-xs text-slate-400">—</span>}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
        </div>
      )}
    </>
  );
}

function DevicesTab({ filters, setFilters, reset }: TabProps) {
  const { can } = useAuth();
  const { q, trust_status, shared, page } = filters;
  const { data, isLoading, isFetching, error, refetch } = useDevices({ ...toParams({ q, trust_status, shared, page }), page_size: '25' });
  const setTrust = useSetDeviceTrust();
  const [target, setTarget] = useState<{ device: DeviceOut; to: 'trusted' | 'suspicious' } | null>(null);
  const filtered = Boolean(q || trust_status || shared);

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
        <div className="w-full sm:w-64"><SearchInput placeholder="STU- reference or device" label="Search devices" value={q} onChange={(v) => setFilters({ q: v })} /></div>
        <Select aria-label="Trust" value={trust_status} onChange={(e) => setFilters({ trust_status: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-40">
          <option value="">Trust: all</option>
          {['trusted', 'unfamiliar', 'suspicious'].map((v) => <option key={v} value={v}>{label(v)}</option>)}
        </Select>
        <Select aria-label="Shared" value={shared} onChange={(e) => setFilters({ shared: e.target.value })} className="w-[calc(50%-0.25rem)] sm:w-56">
          <option value="">Sharing: all</option>
          <option value="true">Used on several student accounts</option>
        </Select>
        {filtered && <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>Clear filters</Button>}
      </div>
      {isLoading ? <TableSkeleton rows={10} cols={6} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data || data.items.length === 0 ? (
        <EmptyState icon={<Laptop className="size-5" />} title="No devices match" />
      ) : (
        <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
          <Table>
            <THead><tr><TH>Device</TH><TH>Student</TH><TH>Trust</TH><TH>First seen</TH><TH>Last seen</TH><TH>Other student accounts</TH>{can(P.accountsRestrict) && <TH className="text-right">Action</TH>}</tr></THead>
            <tbody>
              {data.items.map((d) => {
                const shared = d.other_accounts_in_scope + d.other_accounts_other_institutions;
                return (
                  <TR key={d.id}>
                    <TD><span className="flex items-center gap-2 text-sm"><Smartphone className="size-4 text-slate-400" aria-hidden />{d.label}</span><code className="text-[11px] text-slate-500">{d.handle}</code></TD>
                    <TD><span className="font-mono text-xs">{d.student.student_ref}</span></TD>
                    <TD><StatusBadge value={d.trust_status} map={deviceTrustTone} />{d.trust_reason && <p className="mt-1 max-w-48 truncate text-[11px] text-slate-500" title={d.trust_reason}>{d.trust_reason}</p>}</TD>
                    <TD className="tabular text-xs">{dateTime(d.first_seen_at)}</TD>
                    <TD className="tabular text-xs">{dateTime(d.last_seen_at)}</TD>
                    <TD>{shared > 0 ? <Badge tone="critical">{d.other_accounts_in_scope} here · {d.other_accounts_other_institutions} elsewhere</Badge> : <span className="text-xs text-slate-400">None</span>}</TD>
                    {can(P.accountsRestrict) && (
                      <TD className="text-right">
                        {d.trust_status !== 'suspicious' ? (
                          <Button size="sm" variant="ghost" onClick={() => setTarget({ device: d, to: 'suspicious' })}>Mark suspicious</Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => setTarget({ device: d, to: 'trusted' })}>Mark trusted</Button>
                        )}
                      </TD>
                    )}
                  </TR>
                );
              })}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
        </div>
      )}
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(o) => !o && setTarget(null)}
        title={target?.to === 'suspicious' ? 'Mark this device as suspicious?' : 'Mark this device as trusted?'}
        description="The change is audited and the student's account is re-scored. It does not sign anyone out or block the card."
        reasonLabel="Reason"
        tone={target?.to === 'suspicious' ? 'danger' : 'primary'}
        confirmLabel="Save"
        loading={setTrust.isPending}
        onConfirm={(reason) =>
          target &&
          setTrust.mutate(
            { id: target.device.id, trust_status: target.to, reason },
            {
              onSuccess: () => { toast.success('Device updated', { description: `${target.device.label} · ${target.to}` }); setTarget(null); },
              onError: (err) => toast.error('Update failed', { description: errorMessage(err) }),
            },
          )
        }
      />
    </>
  );
}

function EventDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data: e, isLoading, error, refetch } = useSecurityEvent(id);
  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={e ? securityEventLabel[e.event_type] ?? label(e.event_type) : 'Security event'} description={e ? `${e.reference} · ${e.organization.name}` : undefined}>
      {isLoading ? <CardSkeleton /> : error || !e ? <ErrorState error={error} onRetry={() => refetch()} /> : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            {e.risk_level && <RiskBadge level={e.risk_level as RiskLevel} score={e.risk_score} />}
            {e.decision && <StatusBadge value={e.decision} map={decisionTone} />}
            <Badge tone="neutral">{label(e.outcome)}</Badge>
          </div>
          <DetailList>
            <Detail label="Account">{e.account_id ? <Link className="text-brand-blue hover:underline" to={`/app/accounts/${e.account_id}`}>{e.account_ref}</Link> : '—'}</Detail>
            <Detail label="Student">{e.student.student_ref} · {e.student.masked_name}</Detail>
            <Detail label="When">{dateTime(e.occurred_at)}</Detail>
            <Detail label="Source">{label(e.source)}</Detail>
            <Detail label="Device">{e.device ? `${e.device.label} (${e.device.trust_status})` : '—'}</Detail>
            <Detail label="Location"><LocationText location={e.location} restricted={e.location_restricted} /></Detail>
            {e.card_ref && <Detail label="Card">{e.card_ref}</Detail>}
            {e.destination && <Detail label="Requested destination"><code className="text-xs">{e.destination.handle}</code></Detail>}
          </DetailList>
          {e.note && <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{e.note}</p>}
          <section>
            <SectionTitle>Signals raised by this event</SectionTitle>
            <IndicatorList indicators={e.indicators} empty="This event did not raise a signal on its own. The account risk shown is the combined score at that moment." />
          </section>
        </div>
      )}
    </Drawer>
  );
}
