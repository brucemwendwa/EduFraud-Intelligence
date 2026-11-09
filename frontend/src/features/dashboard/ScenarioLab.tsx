import { CheckCircle2, FlaskConical, Play, ShieldCheck, XCircle } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { SimulationResult } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { P } from '@/lib/permissions';
import { useRunScenario, useScenarioChecks, useScenarios } from './api';

/** Replays a synthetic scenario through the real ingestion, risk and verification services (demo mode only). */
export function ScenarioLab() {
  const { can } = useAuth();
  const scenarios = useScenarios();
  const checks = useScenarioChecks();
  const run = useRunScenario();
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const allowed = can(P.simulationsRun);

  const play = (key: string) => {
    setPending(key);
    run.mutate(key, {
      onSuccess: (res) => {
        setResult(res);
        toast.success(`${res.label} replayed`, { description: `${res.events.length} provider events processed · synthetic data` });
      },
      onError: (err) => toast.error('Scenario could not run', { description: errorMessage(err) }),
      onSettled: () => setPending(null),
    });
  };

  const live = (scenarios.data ?? []).filter((s) => s.live);
  const checkFor = (key: string) => checks.data?.find((c) => c.key === key);

  return (
    <Card>
      <CardHeader
        title="Scenario lab"
        description="Replay a synthetic scenario on untouched demo accounts. Events go through the same webhooks, rules and workflows as live provider data."
        icon={<FlaskConical className="size-4" />}
      />
      <CardBody className="space-y-4">
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {live.map((s) => {
            const check = checkFor(s.key);
            return (
              <li key={s.key} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900">{s.label}</p>
                    <Badge tone={s.kind === 'fraud' ? 'high' : 'success'}>{s.kind === 'fraud' ? 'Fraud pattern' : 'Legitimate control'}</Badge>
                    {check && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500" title="Seeded scenario coverage check">
                        {check.passed ? <CheckCircle2 className="size-3.5 text-risk-low" aria-hidden /> : <XCircle className="size-3.5 text-risk-critical" aria-hidden />}
                        {check.passed ? 'Seeded check passes' : 'Seeded check failing'}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">Expected: {s.expected}</p>
                </div>
                {allowed && (
                  <Button size="sm" variant="secondary" icon={<Play className="size-3.5" />} loading={pending === s.key} disabled={pending !== null} onClick={() => play(s.key)}>
                    Run
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
        {!allowed && <p className="text-xs text-slate-500">Your role can view scenario coverage but not replay scenarios.</p>}
        {result && (
          <div className="rounded-lg bg-navy-50/60 p-3.5 text-sm ring-1 ring-navy-100" aria-live="polite">
            <p className="font-medium text-slate-900">{result.label}: result</p>
            <ul className="mt-2 space-y-1.5">
              {result.accounts.map((a) => (
                <li key={String(a.id)} className="flex flex-wrap items-center gap-2">
                  <Link to={`/app/accounts/${String(a.id)}`} className="font-mono text-xs text-brand-blue hover:underline">{String(a.reference)}</Link>
                  <RiskBadge level={a.risk_level as RiskLevel} score={Number(a.risk_score)} />
                  {a.restricted ? <Badge tone="warning">Sensitive actions on hold</Badge> : <Badge tone="neutral"><ShieldCheck className="size-3" />No restriction</Badge>}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-600">
              {result.alerts.length} alert(s){result.alerts[0] && <> · <Link className="text-brand-blue hover:underline" to={`/app/alerts?selected=${String(result.alerts[0].id)}`}>open {String(result.alerts[0].reference)}</Link></>}
              {' · '}
              {result.verification_requests.length ? `verification ${result.verification_requests.join(', ')}` : 'no verification requested'}
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
