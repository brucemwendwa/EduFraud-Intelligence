import {
  ArrowLeftRight,
  Ban,
  Banknote,
  CreditCard,
  History,
  Lock,
  Network,
  PlayCircle,
  RefreshCw,
  ScanFace,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  Unlock,
  UserCheck,
  WalletCards,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import type { AccountDetail } from '@/api/types';
import { SignalList } from '@/components/risk/SignalList';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Detail, DetailList } from '@/components/ui/DetailList';
import { LocationText } from '@/components/ui/Location';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, RiskScoreRing, riskLevelOf, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, EmptyState, ErrorState } from '@/components/ui/States';
import { TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { RequestVerificationDialog } from '@/features/verification/requests/RequestVerificationDialog';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { date, dateTime, label, money } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  accountStatusTone,
  alertStatusLabel,
  alertStatusTone,
  cardStatusTone,
  caseStatusTone,
  decisionTone,
  deviceTrustTone,
  disbursementStatusTone,
  securityEventLabel,
  studyModeLabel,
  transactionStatusTone,
  verificationRequestTone,
  verificationStatusTone,
} from '@/lib/status';
import { useAccount, useAccountAction } from './api';

type Action = 'restrict' | 'lift-restriction' | 'suspend' | 'reactivate';

const actionCopy: Record<Action, { title: string; description: string; confirm: string; tone: 'danger' | 'primary' }> = {
  restrict: {
    title: 'Hold sensitive changes?',
    description: 'The provider will hold payout redirection, credential changes, card replacement and money transfers out. Everyday card spending continues.',
    confirm: 'Request restriction',
    tone: 'danger',
  },
  'lift-restriction': {
    title: 'Lift the restriction?',
    description: 'Security holds can only be lifted after the student’s identity has been re-verified.',
    confirm: 'Lift restriction',
    tone: 'primary',
  },
  suspend: {
    title: 'Ask the provider to suspend this account?',
    description: 'All card use stops until the provider reactivates the account. Use only after human review; the student must be informed.',
    confirm: 'Request suspension',
    tone: 'danger',
  },
  reactivate: {
    title: 'Ask the provider to reactivate this account?',
    description: 'Requires a verified identity after the suspension.',
    confirm: 'Request reactivation',
    tone: 'primary',
  },
};

export default function AccountDetailPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const { data: a, isLoading, error, refetch } = useAccount(id);
  const action = useAccountAction(id ?? '');
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [requesting, setRequesting] = useState(false);

  if (isLoading) return <div className="space-y-4"><CardSkeleton /><CardSkeleton /></div>;
  if (error || !a) return <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>;

  const run = (kind: Action | 'assess', reason?: string) =>
    action.mutate(
      { action: kind, reason },
      {
        onSuccess: (res) => {
          toast.success(kind === 'assess' ? 'Risk re-assessed' : 'Request recorded', {
            description: kind === 'assess' ? `${res.reference} scored ${Math.round(res.risk_score ?? 0)}/100` : `${res.reference} · provider acknowledgement stored in the audit trail`,
          });
          setConfirm(null);
        },
        onError: (err) => toast.error('Action not completed', { description: errorMessage(err) }),
      },
    );

  const restrictAllowed = can(P.accountsRestrict);
  const openRequest = a.verification_requests.find((r) => ['pending', 'in_progress', 'additional_info_required', 'escalated'].includes(r.status));
  const app = a.allocations.find((d) => d.application_id);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Student accounts', to: '/app/accounts' }, { label: a.reference }]}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {a.reference}
            <StatusBadge value={a.status} map={accountStatusTone} />
            {a.sensitive_actions_restricted && <Badge tone="warning" icon={<Lock className="size-3" />}>Sensitive changes on hold</Badge>}
          </span>
        }
        description={`${a.student.student_ref} · ${a.student.masked_name} · ${a.organization.name}${a.department ? ` · ${a.department}` : ''}`}
        meta={<Badge tone="blue">{a.provider_mode === 'sandbox' ? 'Sandbox provider (simulated)' : a.provider_key}</Badge>}
        actions={
          <>
            {can(P.detectionRun) && <Button variant="secondary" size="sm" icon={<RefreshCw className="size-3.5" />} loading={action.isPending && !confirm} onClick={() => run('assess')}>Re-assess</Button>}
            {can(P.verificationsInitiate) && !openRequest && <Button variant="secondary" size="sm" icon={<ScanFace className="size-3.5" />} onClick={() => setRequesting(true)}>Request verification</Button>}
            {restrictAllowed && !a.sensitive_actions_restricted && !['suspended', 'closed'].includes(a.status) && <Button variant="secondary" size="sm" icon={<Lock className="size-3.5" />} onClick={() => setConfirm('restrict')}>Restrict</Button>}
            {restrictAllowed && a.sensitive_actions_restricted && <Button variant="secondary" size="sm" icon={<Unlock className="size-3.5" />} onClick={() => setConfirm('lift-restriction')}>Lift restriction</Button>}
            {restrictAllowed && a.status === 'suspended' && <Button size="sm" icon={<PlayCircle className="size-3.5" />} onClick={() => setConfirm('reactivate')}>Reactivate</Button>}
            {restrictAllowed && !['suspended', 'closed'].includes(a.status) && <Button variant="danger" size="sm" icon={<Ban className="size-3.5" />} onClick={() => setConfirm('suspend')}>Suspend</Button>}
          </>
        }
      />

      {openRequest && (
        <div className="mb-6 flex flex-col gap-2 rounded-xl bg-violet-50 px-4 py-3 text-sm text-violet-900 ring-1 ring-violet-100 sm:flex-row sm:items-center">
          <ScanFace className="size-4 shrink-0" aria-hidden />
          <span className="flex-1">
            Identity verification <strong>{openRequest.reference}</strong> is {label(openRequest.status).toLowerCase()} ({label(openRequest.pathway).toLowerCase()} pathway). {openRequest.reason}
          </span>
          <Link to={`/app/verification?tab=requests&selected=${openRequest.id}`} className="font-medium text-violet-800 hover:underline">Open request</Link>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader title="Account" icon={<WalletCards className="size-4" />} description="Held by the payment-provider partner; the ID card is the access credential." />
          <CardBody className="space-y-5">
            <DetailList>
              <Detail label="Provider account">{a.provider_account_handle}</Detail>
              <Detail label="Study arrangement">{studyModeLabel[a.study_mode] ?? label(a.study_mode)}</Detail>
              <Detail label="Aid allocated">{money(a.allocated_total)}</Detail>
              <Detail label="Available balance">
                {a.available_balance != null ? money(a.available_balance, true) : '—'}
                {a.balance_as_of && <span className="block text-[11px] text-slate-500">Provider report · {dateTime(a.balance_as_of)}</span>}
              </Detail>
              <Detail label="Opened">{date(a.opened_at)}</Detail>
              <Detail label="Last transaction">{dateTime(a.last_transaction_at)}</Detail>
              <Detail label="Registered location"><LocationText location={a.registered_location} restricted={a.location_restricted} /></Detail>
              <Detail label="Identity verification"><StatusBadge value={a.verification_status} map={verificationRequestTone} /></Detail>
            </DetailList>
            {(a.restriction_reason || a.status_reason) && (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-100">{a.restriction_reason ?? a.status_reason}</p>
            )}
            <div className="space-y-2">
              {a.cards.slice(0, 2).map((c) => (
                <Link key={c.id} to={`/app/cards?selected=${c.id}`} className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 hover:border-navy-200">
                  <span className="flex h-9 w-14 items-center justify-center rounded-md bg-gradient-to-br from-navy-800 to-navy-600 text-white"><CreditCard className="size-4" aria-hidden /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-slate-900">University ID card {c.masked_number}</span>
                    <span className="block text-xs text-slate-500">{c.reference} · issued {date(c.issued_at)}</span>
                  </span>
                  <StatusBadge value={c.status} map={cardStatusTone} />
                </Link>
              ))}
            </div>
            {app?.application_id && can(P.networkRead) && (
              <Link to={`/app/network?focus=${app.application_id}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-blue hover:underline">
                <Network className="size-4" aria-hidden /> View relationships in Fraud Network
              </Link>
            )}
          </CardBody>
        </Card>
        <RiskCard a={a} className="xl:col-span-3" />
      </div>

      <Card className="mt-6">
        <Tabs defaultValue="transactions">
          <TabsList className="px-4">
            <TabsTrigger value="transactions" count={a.transactions.length}>Transactions</TabsTrigger>
            <TabsTrigger value="allocations" count={a.allocations.length}>Aid allocations</TabsTrigger>
            <TabsTrigger value="security" count={a.security_events.length}>Security events</TabsTrigger>
            <TabsTrigger value="verification" count={a.verification_requests.length}>Verification</TabsTrigger>
            <TabsTrigger value="alerts" count={a.alerts.length + a.cases.length}>Alerts & cases</TabsTrigger>
            <TabsTrigger value="devices" count={a.devices.length}>Devices</TabsTrigger>
            <TabsTrigger value="history" count={a.assessment_history.length}>Risk history</TabsTrigger>
          </TabsList>
          <TabsContent value="transactions"><Transactions a={a} /></TabsContent>
          <TabsContent value="allocations"><Allocations a={a} /></TabsContent>
          <TabsContent value="security"><SecurityEvents a={a} /></TabsContent>
          <TabsContent value="verification"><Verification a={a} /></TabsContent>
          <TabsContent value="alerts"><AlertsAndCases a={a} /></TabsContent>
          <TabsContent value="devices"><Devices a={a} /></TabsContent>
          <TabsContent value="history"><RiskHistory a={a} /></TabsContent>
        </Tabs>
      </Card>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? actionCopy[confirm].title : ''}
        description={confirm ? actionCopy[confirm].description : undefined}
        reasonLabel="Reason"
        tone={confirm ? actionCopy[confirm].tone : 'primary'}
        confirmLabel={confirm ? actionCopy[confirm].confirm : 'Confirm'}
        loading={action.isPending}
        onConfirm={(reason) => confirm && run(confirm, reason)}
      />
      <RequestVerificationDialog open={requesting} onOpenChange={setRequesting} accountId={a.id} accountRef={a.reference} />
    </>
  );
}

function RiskCard({ a, className }: { a: AccountDetail; className?: string }) {
  const r = a.assessment;
  if (!r) {
    return <Card className={className}><EmptyState icon={<ShieldAlert className="size-5" />} title="Not yet assessed" description="The account risk engine has not scored this account yet." /></Card>;
  }
  const elevated = r.level === 'high' || r.level === 'critical';
  return (
    <Card className={className}>
      <CardHeader title="Explainable risk assessment" icon={<ShieldAlert className="size-4" />} description={`${dateTime(r.created_at)} · triggered by ${label(r.triggered_by)} · ${r.rules_version}`} />
      <CardBody className="space-y-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <RiskScoreRing score={r.score} level={r.level as RiskLevel} size={104} />
          <div className="min-w-0 flex-1 space-y-2">
            <RiskBadge level={r.level as RiskLevel} score={r.score} />
            <p className="text-sm leading-relaxed text-slate-700">{r.explanation}</p>
            <div className={elevated ? 'flex gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-100' : 'flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700'}>
              <UserCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span><span className="font-medium">Recommended:</span> {r.recommended_action}</span>
            </div>
          </div>
        </div>
        {r.signals.length > 0 ? <SignalList signals={r.signals} /> : <p className="text-sm text-slate-500">No risk signals: activity matches this student’s usual pattern.</p>}
        <p className="text-[11px] text-slate-500">{r.method}. Scores prioritise human review; they never decide an outcome.</p>
      </CardBody>
    </Card>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="px-5 py-8 text-center text-sm text-slate-500">{children}</p>;
}

function Transactions({ a }: { a: AccountDetail }) {
  if (a.transactions.length === 0) return <Empty>No transactions. Saving aid is normal: lack of spending is never treated as fraud.</Empty>;
  return (
    <Table>
      <THead><tr><TH>Reference</TH><TH>Merchant</TH><TH className="text-right">Amount</TH><TH>When</TH><TH>Location</TH><TH>Status</TH><TH>Risk</TH></tr></THead>
      <tbody>
        {a.transactions.map((t) => (
          <TR key={t.id}>
            <TD><Link className="font-medium text-slate-900 hover:text-brand-blue" to={`/app/transactions?selected=${t.id}`}>{t.reference}</Link></TD>
            <TD><span className="block text-sm">{t.merchant_name}</span><span className="text-xs text-slate-500">{label(t.merchant_category)} · {label(t.channel)}</span></TD>
            <TD className="tabular text-right font-medium">{money(t.amount, true)}</TD>
            <TD className="tabular whitespace-nowrap text-xs">{dateTime(t.occurred_at)}</TD>
            <TD className="text-xs"><LocationText location={t.location} restricted={t.location_restricted} /></TD>
            <TD><StatusBadge value={t.status} map={transactionStatusTone} /></TD>
            <TD>{t.risk_level && t.risk_level !== 'low' ? <RiskBadge level={t.risk_level as RiskLevel} score={t.risk_score} /> : <span className="text-xs text-slate-400">Low</span>}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function Allocations({ a }: { a: AccountDetail }) {
  if (a.allocations.length === 0) return <Empty>No financial aid allocated to this account yet.</Empty>;
  return (
    <Table>
      <THead><tr><TH>Allocation</TH><TH>Fund</TH><TH className="text-right">Amount</TH><TH>Date</TH><TH>Credited to</TH><TH>Status</TH></tr></THead>
      <tbody>
        {a.allocations.map((d) => (
          <TR key={d.id}>
            <TD className="font-medium">{d.reference}</TD>
            <TD>{label(d.fund_type)}</TD>
            <TD className="tabular text-right font-medium">{money(d.amount, true)}</TD>
            <TD className="tabular text-xs">{date(d.disbursed_at)}</TD>
            <TD>
              {d.destination.destination_type === 'id_card_account' ? (
                <span className="inline-flex items-center gap-1.5 text-xs"><ShieldCheck className="size-3.5 text-risk-low" aria-hidden />ID-linked account</span>
              ) : (
                <span className="inline-flex flex-col gap-1 text-xs"><span className="inline-flex items-center gap-1.5"><Banknote className="size-3.5 text-risk-high" aria-hidden />External {label(d.destination.destination_type).toLowerCase()} <code>{d.destination.handle}</code></span><Badge tone="warning">Redirected away from the ID-linked account</Badge></span>
              )}
            </TD>
            <TD><StatusBadge value={d.status} map={disbursementStatusTone} /></TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function SecurityEvents({ a }: { a: AccountDetail }) {
  if (a.security_events.length === 0) return <Empty>No security events recorded.</Empty>;
  return (
    <Table>
      <THead><tr><TH>Event</TH><TH>When</TH><TH>Device</TH><TH>Location</TH><TH>Outcome</TH><TH>Decision</TH><TH>Risk at the time</TH></tr></THead>
      <tbody>
        {a.security_events.map((e) => (
          <TR key={e.id}>
            <TD><Link className="text-sm font-medium text-slate-900 hover:text-brand-blue" to={`/app/access?selected=${e.id}`}>{securityEventLabel[e.event_type] ?? label(e.event_type)}</Link><span className="block font-mono text-[11px] text-slate-500">{e.reference}</span></TD>
            <TD className="tabular whitespace-nowrap text-xs">{dateTime(e.occurred_at)}</TD>
            <TD className="text-xs">{e.device ? <span className="flex flex-col gap-1">{e.device.label}<StatusBadge value={e.device.trust_status} map={deviceTrustTone} /></span> : '—'}</TD>
            <TD className="text-xs"><LocationText location={e.location} restricted={e.location_restricted} /></TD>
            <TD className="text-xs">{label(e.outcome)}</TD>
            <TD>{e.decision ? <StatusBadge value={e.decision} map={decisionTone} /> : <span className="text-xs text-slate-400">—</span>}</TD>
            <TD>{e.risk_level ? <RiskBadge level={e.risk_level as RiskLevel} score={e.risk_score} /> : <span className="text-xs text-slate-400">—</span>}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function Verification({ a }: { a: AccountDetail }) {
  if (a.verification_requests.length === 0 && a.verification_attempts.length === 0) return <Empty>Identity verification has not been required for this student.</Empty>;
  return (
    <div className="space-y-4 p-4">
      {a.verification_requests.map((r) => (
        <Link key={r.id} to={`/app/verification?tab=requests&selected=${r.id}`} className="flex flex-col gap-2 rounded-lg border border-slate-200 p-3.5 hover:border-navy-200 sm:flex-row sm:items-center">
          <ScanFace className="size-4 shrink-0 text-navy-600" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-slate-900">{r.reference} · {label(r.trigger)}</span>
            <span className="block text-xs text-slate-500">{label(r.pathway)} pathway{r.method ? ` · ${label(r.method)}` : ''} · opened {dateTime(r.created_at)}</span>
          </span>
          <StatusBadge value={r.status} map={verificationRequestTone} />
        </Link>
      ))}
      {a.verification_attempts.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Verification attempts</p>
          <ul className="space-y-1.5 text-sm">
            {a.verification_attempts.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{v.reference}</span>
                <span className="text-slate-600">{label(v.method)} · {v.provider_mode}</span>
                <StatusBadge value={v.status} map={verificationStatusTone} />
                <span className="text-xs text-slate-500">{dateTime(v.created_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AlertsAndCases({ a }: { a: AccountDetail }) {
  if (a.alerts.length === 0 && a.cases.length === 0) return <Empty>No alerts or investigations involve this student.</Empty>;
  return (
    <ul className="divide-y divide-slate-100">
      {a.alerts.map((al) => (
        <li key={al.id}>
          <Link to={`/app/alerts?selected=${al.id}`} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50">
            <ShieldAlert className="size-4 text-risk-high" aria-hidden />
            <span className="min-w-0 flex-1"><span className="block text-sm font-medium text-slate-900">{al.title}</span><span className="text-xs text-slate-500">{al.reference} · {dateTime(al.created_at)}</span></span>
            <RiskBadge level={al.severity as RiskLevel} score={al.risk_score} />
            <StatusBadge value={al.status} map={alertStatusTone} />
            <span className="sr-only">{alertStatusLabel[al.status]}</span>
          </Link>
        </li>
      ))}
      {a.cases.map((c) => (
        <li key={String(c.id)} className="flex items-center gap-3 px-5 py-3">
          <History className="size-4 text-navy-600" aria-hidden />
          <span className="min-w-0 flex-1 text-sm"><span className="font-medium">{String(c.reference)}</span> · {String(c.title)}</span>
          <StatusBadge value={String(c.status)} map={caseStatusTone} />
        </li>
      ))}
    </ul>
  );
}

function Devices({ a }: { a: AccountDetail }) {
  if (a.devices.length === 0) return <Empty>No devices recorded.</Empty>;
  return (
    <Table>
      <THead><tr><TH>Device</TH><TH>Trust</TH><TH>First seen</TH><TH>Last seen</TH><TH>Other student accounts</TH></tr></THead>
      <tbody>
        {a.devices.map((d) => (
          <TR key={d.id}>
            <TD><span className="flex items-center gap-2"><Smartphone className="size-4 text-slate-400" aria-hidden />{d.label}</span><code className="text-[11px] text-slate-500">{d.handle}</code></TD>
            <TD><StatusBadge value={d.trust_status} map={deviceTrustTone} /><span className="block text-[11px] text-slate-500">{d.trust_reason}</span></TD>
            <TD className="text-xs">{date(d.first_seen_at)}</TD>
            <TD className="text-xs">{dateTime(d.last_seen_at)}</TD>
            <TD>{d.other_accounts_in_scope + d.other_accounts_other_institutions > 0 ? <Badge tone="critical">{d.other_accounts_in_scope} here · {d.other_accounts_other_institutions} elsewhere</Badge> : <span className="text-xs text-slate-400">None</span>}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function RiskHistory({ a }: { a: AccountDetail }) {
  if (a.assessment_history.length === 0) return <Empty>No assessments yet.</Empty>;
  return (
    <ul className="divide-y divide-slate-100">
      {a.assessment_history.map((h) => (
        <li key={h.id} className="flex items-center gap-3 px-5 py-3 text-sm">
          <ArrowLeftRight className="size-4 text-slate-400" aria-hidden />
          <span className="flex-1 text-slate-700">{dateTime(h.created_at)} · {label(h.triggered_by)}</span>
          <RiskBadge level={(h.level as RiskLevel) ?? riskLevelOf(h.score)} score={h.score} />
        </li>
      ))}
    </ul>
  );
}
