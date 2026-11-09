import { useQuery } from '@tanstack/react-query';
import { Gauge, Plug, ScanFace, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import type { SystemSettings } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { api } from '@/lib/api';
import { label } from '@/lib/format';

export default function SettingsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['system', 'settings'],
    queryFn: async () => (await api.get<SystemSettings>('/system/settings')).data,
  });
  if (isLoading) return <div className="space-y-4"><CardSkeleton /><CardSkeleton /></div>;
  if (error || !data) return <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>;
  return (
    <>
      <PageHeader
        title="System settings"
        description="Read-only view of the risk configuration, integrations and privacy controls in force. Rule weights are changed through deployment configuration (ACCOUNT_RISK_WEIGHTS) so every change is reviewed and versioned."
        meta={<><Badge tone="navy">Environment: {data.environment}</Badge>{data.demo_mode && <Badge tone="blue">Demo mode</Badge>}{data.weights_overridden && <Badge tone="warning">Weights overridden by configuration</Badge>}</>}
      />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader title="Risk bands" icon={<Gauge className="size-4" />} description={data.risk_bands_note} />
          <CardBody>
            <ul className="space-y-2">
              {data.risk_bands.map((b) => (
                <li key={String(b.level)} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
                  <RiskBadge level={b.level as RiskLevel} />
                  <span className="tabular text-sm text-slate-700">{Math.round(Number(b.min))}–{Math.floor(Number(b.max))}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Integrations" icon={<Plug className="size-4" />} description="Nothing here connects to a real bank, card network, government system or biometric vendor." />
          <Table>
            <THead><tr><TH>Integration</TH><TH>Purpose</TH><TH>Mode</TH><TH>Status</TH></tr></THead>
            <tbody>
              {data.integrations.map((i) => (
                <TR key={String(i.name)}>
                  <TD className="font-medium">{String(i.name)}</TD>
                  <TD className="text-xs">{String(i.kind)}</TD>
                  <TD><Badge tone={i.mode === 'live' ? 'success' : 'blue'}>{String(i.mode)}</Badge></TD>
                  <TD className="text-xs text-slate-600">{String(i.status)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>
      <Card className="mt-6">
        <CardHeader title={`Account risk rules · ${data.account_rules_version}`} icon={<SlidersHorizontal className="size-4" />} description={`${data.account_engine_method}. Weight = strength of one signal on its own (0–1); signals combine by noisy-OR.`} />
        <Table>
          <THead><tr><TH>Rule</TH><TH>Category</TH><TH>Severity</TH><TH className="text-right">Weight</TH><TH>Description</TH></tr></THead>
          <tbody>
            {data.account_rules.map((r) => (
              <TR key={String(r.code)}>
                <TD><span className="block text-sm font-medium">{String(r.title)}</span><code className="text-[11px] text-slate-500">{String(r.code)}</code></TD>
                <TD className="text-xs">{label(String(r.category))}</TD>
                <TD className="text-xs">{label(String(r.severity))}{r.context_only ? <Badge tone="neutral" className="ml-1">Context only</Badge> : null}</TD>
                <TD className="tabular text-right">{Number(r.weight).toFixed(2)}</TD>
                <TD className="max-w-md text-xs text-slate-600">{String(r.description)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      </Card>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Identity verification" icon={<ScanFace className="size-4" />} description="Designated offices and formal embassy/consulate arrangements in your scope." />
          <CardBody className="space-y-3">
            {data.verification.map((v) => (
              <div key={String(v.institution)} className="rounded-lg border border-slate-200 p-3 text-sm">
                <p className="font-medium text-slate-900">{String(v.institution)}</p>
                <p className="text-xs text-slate-600">Office: {String(v.office ?? '—')}</p>
                <p className="mt-1 text-xs text-slate-600">
                  Embassy-assisted: {Object.keys(v.embassy_arrangements as object).length ? Object.entries(v.embassy_arrangements as Record<string, string>).map(([c, n]) => `${c} — ${n}`).join('; ') : 'no formal arrangements (method unavailable)'}
                </p>
              </div>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Privacy and security controls" icon={<ShieldCheck className="size-4" />} />
          <CardBody>
            <ul className="space-y-2">
              {data.privacy_controls.map((p) => <li key={p} className="flex gap-2 text-sm text-slate-700"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />{p}</li>)}
            </ul>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
