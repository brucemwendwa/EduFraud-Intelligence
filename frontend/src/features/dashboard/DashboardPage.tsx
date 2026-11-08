import {
  ArrowLeftRight,
  Banknote,
  Bell,
  CreditCard,
  FlaskConical,
  FolderKanban,
  GraduationCap,
  ScanFace,
  ShieldAlert,
  WalletCards,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ActivityItem, DashboardOverview } from '@/api/types';
import { ChartCard, riskColor, seriesColor } from '@/components/charts/ChartCard';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { StatCard, compact } from '@/components/ui/StatCard';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { RunDetectionButton } from '@/features/engine/RunDetectionButton';
import { useAuth } from '@/lib/auth';
import { dateTime, label, money, timeAgo } from '@/lib/format';
import { alertStatusLabel } from '@/lib/status';
import { P } from '@/lib/permissions';
import { ApplicationPipeline } from './ApplicationPipeline';
import { useDashboardOverview } from './api';
import { ScenarioLab } from './ScenarioLab';

const icons: Record<string, { icon: LucideIcon; accent: 'navy' | 'critical' | 'warning' | 'success' | 'blue' }> = {
  students: { icon: GraduationCap, accent: 'navy' },
  active_accounts: { icon: WalletCards, accent: 'blue' },
  aid_allocated: { icon: Banknote, accent: 'success' },
  transactions: { icon: ArrowLeftRight, accent: 'navy' },
  high_risk_alerts: { icon: Bell, accent: 'critical' },
  suspicious_transactions: { icon: ShieldAlert, accent: 'warning' },
  verification_requests: { icon: ScanFace, accent: 'blue' },
  open_cases: { icon: FolderKanban, accent: 'navy' },
  cards_blocked: { icon: CreditCard, accent: 'warning' },
};

const axis = { tick: { fill: seriesColor.axis, fontSize: 11 }, tickLine: false, axisLine: false } as const;
const tooltipStyle = {
  contentStyle: { borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12, boxShadow: '0 4px 16px -2px rgb(11 31 58 / 0.1)' },
  cursor: { fill: 'rgb(37 99 235 / 0.06)' },
} as const;
const shortDate = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

export default function DashboardPage() {
  const { user, can } = useAuth();
  const { data, isLoading, error, refetch } = useDashboardOverview();

  return (
    <>
      <PageHeader
        title="Financial aid protection overview"
        description="Aid applications, student ID-linked accounts, transactions, security events and investigations in your scope. Figures come from live records; the AI never decides an outcome, people do."
        meta={
          <>
            <Badge tone="blue" icon={<FlaskConical className="size-3" />}>Synthetic demonstration data</Badge>
            {data && <span className="text-xs text-slate-500">Updated {dateTime(data.generated_at as string)}</span>}
            <span className="text-xs text-slate-500">Signed in as {user?.full_name}</span>
          </>
        }
        actions={<RunDetectionButton size="sm" />}
      />

      {can(P.applicationsRead) && <ApplicationPipeline />}

      {error ? (
        <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>
      ) : (
        <>
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Accounts and security</h2>
          <Metrics data={data} loading={isLoading} />
          <Charts data={data} loading={isLoading} />
          <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
            <RecentActivity items={data?.recent_activity} loading={isLoading} className="xl:col-span-3" />
            <div className="xl:col-span-2"><ScenarioLab /></div>
          </div>
        </>
      )}
    </>
  );
}

function Metrics({ data, loading }: { data?: DashboardOverview; loading: boolean }) {
  const metrics = data?.metrics ?? Object.keys(icons).map((key) => ({ key, label: '', value: 0, link: null }));
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {metrics.map((m) => {
        const meta = icons[m.key] ?? icons.students!;
        const value = m.key === 'aid_allocated' ? money(m.value) : compact(m.value);
        return (
          <StatCard
            key={m.key}
            label={m.label || '…'}
            value={value}
            icon={<meta.icon className="size-4" />}
            accent={meta.accent}
            loading={loading}
            to={m.link ?? undefined}
          />
        );
      })}
    </div>
  );
}

function Charts({ data, loading }: { data?: DashboardOverview; loading: boolean }) {
  const allocation = data?.allocation_trend ?? [];
  const activity = data?.transaction_activity ?? [];
  const risk = data?.risk_distribution ?? [];
  const categories = data?.suspicious_categories ?? [];
  const verification = data?.verification_outcomes ?? [];
  const investigations = [
    ...(data?.investigation_status ?? []).map((r) => ({ name: `Case · ${label(String(r.status))}`, count: Number(r.count) })),
    ...(data?.alert_status ?? []).map((r) => ({ name: `Alert · ${alertStatusLabel[String(r.status)] ?? label(String(r.status))}`, count: Number(r.count) })),
  ];

  return (
    <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
      <ChartCard
        title="Financial aid allocation"
        description="Weekly totals credited to ID-linked accounts, scheduled, or on hold"
        loading={loading}
        empty={allocation.length === 0}
        legend={[
          { label: 'Credited', color: seriesColor.primary },
          { label: 'Scheduled', color: seriesColor.secondary },
          { label: 'On hold', color: seriesColor.warning },
        ]}
        table={{
          columns: ['Week of', 'Credited', 'Scheduled', 'On hold'],
          rows: allocation.map((r) => [shortDate(String(r.week)), money(Number(r.credited)), money(Number(r.scheduled)), money(Number(r.held))]),
        }}
      >
        <ResponsiveContainer>
          <BarChart data={allocation} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={seriesColor.grid} />
            <XAxis dataKey="week" tickFormatter={shortDate} {...axis} minTickGap={16} />
            <YAxis {...axis} width={48} tickFormatter={(v: number) => (v >= 1000 ? `$${Math.round(v / 1000)}K` : `$${v}`)} />
            <Tooltip {...tooltipStyle} labelFormatter={(v) => `Week of ${shortDate(String(v))}`} formatter={(v) => money(Number(v))} />
            <Bar dataKey="credited" name="Credited" stackId="a" fill={seriesColor.primary} stroke="#fff" strokeWidth={2} maxBarSize={24} />
            <Bar dataKey="scheduled" name="Scheduled" stackId="a" fill={seriesColor.secondary} stroke="#fff" strokeWidth={2} maxBarSize={24} />
            <Bar dataKey="held" name="On hold" stackId="a" fill={seriesColor.warning} stroke="#fff" strokeWidth={2} maxBarSize={24} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Transaction activity"
        description="Daily card transactions monitored, last 30 days"
        loading={loading}
        empty={activity.every((d) => !d.total)}
        legend={[
          { label: 'All transactions', color: seriesColor.primary },
          { label: 'Flagged (medium+)', color: seriesColor.flagged },
        ]}
        table={{
          columns: ['Date', 'Transactions', 'Flagged', 'Declined'],
          rows: activity.map((d) => [shortDate(String(d.date)), Number(d.total), Number(d.flagged), Number(d.declined)]),
        }}
      >
        <ResponsiveContainer>
          <LineChart data={activity} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={seriesColor.grid} />
            <XAxis dataKey="date" tickFormatter={shortDate} {...axis} minTickGap={24} />
            <YAxis {...axis} width={36} allowDecimals={false} />
            <Tooltip {...tooltipStyle} cursor={{ stroke: '#cbd5e1' }} labelFormatter={(v) => shortDate(String(v))} />
            <Line type="monotone" dataKey="total" name="All transactions" stroke={seriesColor.primary} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} />
            <Line type="monotone" dataKey="flagged" name="Flagged" stroke={seriesColor.flagged} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Account risk distribution"
        description="Current risk level of every ID-linked account (bands 0–29 / 30–59 / 60–79 / 80–100)"
        loading={loading}
        empty={risk.every((r) => !r.accounts)}
        table={{ columns: ['Risk level', 'Accounts'], rows: risk.map((r) => [label(String(r.level)), Number(r.accounts)]) }}
      >
        <ResponsiveContainer>
          <BarChart data={risk} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={seriesColor.grid} />
            <XAxis dataKey="level" tickFormatter={(v: string) => label(v)} {...axis} />
            <YAxis {...axis} width={36} allowDecimals={false} />
            <Tooltip {...tooltipStyle} labelFormatter={(v) => `${label(String(v))} risk`} />
            <Bar dataKey="accounts" name="Accounts" maxBarSize={48} radius={[4, 4, 0, 0]} label={{ position: 'top', fill: '#334155', fontSize: 11 }}>
              {risk.map((r) => <Cell key={String(r.level)} fill={riskColor[String(r.level)]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Suspicious transaction indicators"
        description="Why flagged transactions were flagged (last 30 days)"
        loading={loading}
        empty={categories.length === 0}
        table={{ columns: ['Indicator', 'Transactions'], rows: categories.map((c) => [String(c.category), Number(c.count)]) }}
      >
        <ResponsiveContainer>
          <BarChart data={categories} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
            <CartesianGrid horizontal={false} stroke={seriesColor.grid} />
            <XAxis type="number" {...axis} allowDecimals={false} />
            <YAxis type="category" dataKey="category" {...axis} width={170} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey="count" name="Transactions" fill={seriesColor.primary} maxBarSize={18} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Identity verification outcomes"
        description="Verification requests by status"
        loading={loading}
        empty={verification.length === 0}
        table={{ columns: ['Status', 'Requests'], rows: verification.map((v) => [label(String(v.status)), Number(v.count)]) }}
      >
        <ResponsiveContainer>
          <BarChart data={verification} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={seriesColor.grid} />
            <XAxis dataKey="status" tickFormatter={(v: string) => label(v)} {...axis} />
            <YAxis {...axis} width={32} allowDecimals={false} />
            <Tooltip {...tooltipStyle} labelFormatter={(v) => label(String(v))} />
            <Bar dataKey="count" name="Requests" fill={seriesColor.primary} maxBarSize={36} radius={[4, 4, 0, 0]} label={{ position: 'top', fill: '#334155', fontSize: 11 }} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Investigations and alerts"
        description="Cases and alerts by status"
        loading={loading}
        empty={investigations.length === 0}
        table={{ columns: ['Status', 'Count'], rows: investigations.map((i) => [i.name, i.count]) }}
      >
        <ResponsiveContainer>
          <BarChart data={investigations} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
            <CartesianGrid horizontal={false} stroke={seriesColor.grid} />
            <XAxis type="number" {...axis} allowDecimals={false} />
            <YAxis type="category" dataKey="name" {...axis} width={170} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey="count" name="Count" fill={seriesColor.primary} maxBarSize={16} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

function RecentActivity({ items, loading, className }: { items?: ActivityItem[]; loading: boolean; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader
        title="Recent security activity"
        description="Notable sign-in, recovery, card and transaction events. Repeated events on one account are grouped."
        icon={<ShieldAlert className="size-4" />}
        actions={<Link to="/app/access" className="text-xs font-medium text-brand-blue hover:underline">All events</Link>}
      />
      {loading ? (
        <div className="space-y-2 px-5 pb-5">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
      ) : !items || items.length === 0 ? (
        <EmptyState icon={<ShieldAlert className="size-5" />} title="No notable activity" description="Nothing unusual has happened in this scope." />
      ) : (
        <ul className="divide-y divide-slate-100 border-t border-slate-100">
          {items.map((a) => (
            <li key={`${a.kind}-${a.reference}`}>
              <Link to={a.link} className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-slate-50">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
                  {a.kind === 'transaction' ? <ArrowLeftRight className="size-4" aria-hidden /> : <ShieldAlert className="size-4" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-slate-900">{a.title}</span>
                  <span className="block truncate text-xs text-slate-500">
                    <span className="font-mono">{a.student_ref}</span> · {a.detail} · {a.reference}
                  </span>
                </span>
                {a.risk_level && a.risk_level !== 'low' && <RiskBadge level={a.risk_level as RiskLevel} />}
                <span className="hidden w-24 shrink-0 text-right text-xs text-slate-500 sm:block" title={String(a.occurred_at)}>{timeAgo(String(a.occurred_at))}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
