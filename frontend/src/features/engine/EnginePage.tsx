import { BrainCircuit, CheckCircle2, Cpu, FlaskConical, Scale, ScrollText, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { dateTime, label, timeAgo } from '@/lib/format';
import { useDetectionStatus, useScenarioValidation } from './api';
import { RunDetectionButton } from './RunDetectionButton';

const runTone = { completed: 'success', running: 'blue', queued: 'neutral', failed: 'critical' } as const;

export default function EnginePage() {
  const status = useDetectionStatus();
  const scenarios = useScenarioValidation();
  const s = status.data;

  return (
    <>
      <PageHeader
        title="Detection engine"
        description="How EduShield scores risk: versioned rules, graph analysis and a capped anomaly model. Every component and its limits are documented here."
        actions={<RunDetectionButton />}
      />
      {status.isLoading ? (
        <Card><CardSkeleton /></Card>
      ) : status.error || !s ? (
        <ErrorState error={status.error} onRetry={() => status.refetch()} />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Fact icon={<Cpu className="size-4" />} label="Method" value={s.method} />
            <Fact icon={<ScrollText className="size-4" />} label="Rules · graph" value={`${s.rules_version} · ${s.graph_version}`} mono />
            <Fact icon={<BrainCircuit className="size-4" />} label="Anomaly model" value={s.model_version} mono />
            <Fact
              icon={<FlaskConical className="size-4" />}
              label="Last run"
              value={s.last_run ? `${timeAgo(s.last_run.finished_at ?? s.last_run.created_at)} · ${s.last_run.applications_scored} scored` : 'Never'}
              note={`Jobs: ${s.jobs_backend === 'celery' ? 'Celery worker' : 'inline (no broker configured)'}`}
            />
          </div>

          <Card>
            <CardHeader
              title="Scenario coverage check"
              description="Checks, against current assessments, that each documented synthetic scenario triggers what it should and that legitimate controls are not flagged. This is a regression check on synthetic data, not an accuracy measurement."
              icon={<CheckCircle2 className="size-4" />}
            />
            {scenarios.isLoading ? (
              <CardSkeleton />
            ) : scenarios.error ? (
              <ErrorState error={scenarios.error} onRetry={() => scenarios.refetch()} />
            ) : (
              <Table>
                <THead>
                  <tr><TH>Scenario</TH><TH>Type</TH><TH>Expectation</TH><TH>Observed</TH><TH>Result</TH></tr>
                </THead>
                <tbody>
                  {scenarios.data?.map((c) => (
                    <TR key={c.scenario}>
                      <TD className="font-medium text-slate-900">{c.label}<div className="text-xs font-normal text-slate-500">{c.applications} application(s)</div></TD>
                      <TD><Badge tone={c.kind === 'fraud' ? 'violet' : 'success'}>{c.kind === 'fraud' ? 'Fraud pattern' : 'Legitimate control'}</Badge></TD>
                      <TD className="max-w-xs text-xs">
                        {c.expected}
                        {c.expected_signals.length > 0 && <div className="mt-1 font-mono text-[11px] text-slate-500">{c.expected_signals.join(' · ')}</div>}
                      </TD>
                      <TD className="text-xs">
                        {Object.entries(c.observed_levels).map(([lvl, n]) => `${n} ${lvl}`).join(', ')}
                      </TD>
                      <TD>
                        {c.passed ? (
                          <span className="inline-flex items-center gap-1 text-sm font-medium text-green-700"><CheckCircle2 className="size-4" />Pass</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-sm font-medium text-red-700"><XCircle className="size-4" />Fail</span>
                        )}
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Principles" description="Constraints built into the engine." icon={<Scale className="size-4" />} />
              <CardBody>
                <ul className="space-y-2.5">
                  {s.principles.map((p) => (
                    <li key={p} className="flex gap-2.5 text-sm text-slate-700">
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />{p}
                    </li>
                  ))}
                </ul>
                <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-600">
                  {Object.entries(s.level_thresholds).map(([lvl, t]) => (
                    <span key={lvl} className="rounded-md bg-slate-100 px-2 py-1">{label(lvl)} ≥ {t}</span>
                  ))}
                  <span className="rounded-md bg-slate-100 px-2 py-1">Low &lt; 30</span>
                </div>
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Anomaly model card" description={s.model_card.algorithm} icon={<BrainCircuit className="size-4" />} />
              <CardBody>
                <dl className="space-y-3 text-sm">
                  <Row k="Training data">{s.model_card.trained_on}</Row>
                  <Row k="Evaluation"><span className="text-amber-800">{s.model_card.evaluation}</span></Row>
                  <Row k="Explanations">{s.model_card.explanation_method}</Row>
                  <Row k="Maximum influence">Signal weight capped at {s.model_card.max_weight}</Row>
                  <Row k="Excluded features">{s.model_card.excluded_features.join(', ')}</Row>
                  <Row k="Features">
                    <div className="flex flex-wrap gap-1.5">
                      {s.model_card.features.map((f) => <span key={f} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{f}</span>)}
                    </div>
                  </Row>
                </dl>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader title="Signal catalogue" description={`${s.rules.length} signals across rules, graph analysis, biometrics and the anomaly model.`} icon={<ScrollText className="size-4" />} />
            <Table>
              <THead><tr><TH>Signal</TH><TH>Category</TH><TH>Method</TH><TH className="text-right">Max weight</TH><TH>Meaning</TH></tr></THead>
              <tbody>
                {s.rules.map((r) => (
                  <TR key={r.code}>
                    <TD className="font-mono text-xs text-slate-900">{r.code}</TD>
                    <TD>{label(r.category)}</TD>
                    <TD>{label(r.method)}</TD>
                    <TD className="tabular text-right">{r.max_weight.toFixed(2)}</TD>
                    <TD className="text-xs">{r.description}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader title="Recent runs" icon={<FlaskConical className="size-4" />} />
            <Table>
              <THead><tr><TH>Started</TH><TH>Status</TH><TH>Mode</TH><TH className="text-right">Applications</TH><TH className="text-right">Alerts raised</TH><TH>Versions</TH></tr></THead>
              <tbody>
                {s.recent_runs.map((r) => (
                  <TR key={r.id}>
                    <TD className="tabular whitespace-nowrap">{dateTime(r.started_at ?? r.created_at)}</TD>
                    <TD><StatusBadge value={r.status} map={runTone} /></TD>
                    <TD>{label(r.mode)}</TD>
                    <TD className="tabular text-right">{r.applications_scored}</TD>
                    <TD className="tabular text-right">{r.alerts_created}</TD>
                    <TD className="font-mono text-[11px]">{r.rules_version}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}

function Fact({ icon, label: name, value, note, mono }: { icon: ReactNode; label: string; value: string; note?: string; mono?: boolean }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <span className="text-navy-600">{icon}</span>{name}
      </div>
      <p className={mono ? 'mt-2 font-mono text-sm text-slate-900' : 'mt-2 text-sm font-medium text-slate-900'}>{value}</p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </Card>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[9rem_1fr]">
      <dt className="text-xs font-medium text-slate-500">{k}</dt>
      <dd className="text-slate-800">{children}</dd>
    </div>
  );
}
