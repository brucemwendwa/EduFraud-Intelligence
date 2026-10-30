import { History, RefreshCw, ShieldAlert, ShieldQuestion, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import type { ApplicationDetail } from '@/api/types';
import { SignalList } from '@/components/risk/SignalList';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { RiskBadge, RiskScoreRing, type RiskLevel } from '@/components/ui/Risk';
import { EmptyState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { useAssessApplication } from './api';

/** The explainable risk assessment: score, drivers with point contributions, method, versions, recommendation. */
export function RiskPanel({ app }: { app: ApplicationDetail }) {
  const { can } = useAuth();
  const assess = useAssessApplication(app.id);
  const [showHistory, setShowHistory] = useState(false);
  const a = app.assessment;

  const reassess = () =>
    assess.mutate(undefined, {
      onSuccess: (res) =>
        toast.success('Assessment refreshed', {
          description: `${res.reference} scored ${Math.round(res.risk_score ?? 0)}/100 (${res.risk_level}).`,
        }),
      onError: (err) => toast.error('Assessment failed', { description: errorMessage(err) }),
    });

  const action = can(P.applicationsAssess) && (
    <Button variant="secondary" size="sm" icon={<RefreshCw className="size-3.5" />} loading={assess.isPending} onClick={reassess}>
      Re-assess
    </Button>
  );

  if (!a) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldQuestion className="size-5" />}
          title="Not yet assessed"
          description="The detection engine has not scored this application yet."
          action={action || undefined}
        />
      </Card>
    );
  }

  const elevated = a.level === 'high' || a.level === 'critical';
  return (
    <Card>
      <CardHeader
        title="Explainable risk assessment"
        description={`Assessed ${dateTime(a.created_at)} · triggered by ${label(a.triggered_by)}`}
        icon={<ShieldAlert className="size-4" />}
        actions={action}
      />
      <CardBody className="space-y-5">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <RiskScoreRing score={a.score} level={a.level as RiskLevel} size={104} />
          <div className="min-w-0 flex-1 space-y-2">
            <RiskBadge level={a.level as RiskLevel} score={a.score} />
            <p className="text-sm leading-relaxed text-slate-700">{a.explanation}</p>
            <div
              className={
                elevated
                  ? 'flex gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-100'
                  : 'flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700'
              }
            >
              <UserCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                <span className="font-medium">Recommended:</span> {a.recommended_action}
              </span>
            </div>
          </div>
        </div>

        {a.signals.length > 0 ? (
          <div>
            <h3 className="mb-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">
              Detection signals · points add up to the score
            </h3>
            <SignalList signals={a.signals} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">No risk signals were detected for this application.</p>
        )}

        <dl className="grid gap-3 rounded-lg bg-slate-50 p-3.5 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-slate-500">Method</dt>
            <dd className="mt-0.5 font-medium text-slate-800">{a.method}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Rule version</dt>
            <dd className="mt-0.5 font-mono text-slate-800">{a.rules_version}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Model version</dt>
            <dd className="mt-0.5 font-mono text-slate-800">{a.model_version ?? 'not applied'}</dd>
          </div>
        </dl>

        {app.assessment_history.length > 1 && (
          <div>
            <Button variant="ghost" size="sm" icon={<History className="size-3.5" />} onClick={() => setShowHistory((v) => !v)}>
              {showHistory ? 'Hide' : 'Show'} assessment history ({app.assessment_history.length})
            </Button>
            {showHistory && (
              <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                {app.assessment_history.map((h) => (
                  <li key={h.id} className="flex items-center justify-between gap-3 px-3.5 py-2 text-sm">
                    <span className="tabular text-slate-600">{dateTime(h.created_at)}</span>
                    <span className="text-xs text-slate-500">{label(h.triggered_by)}</span>
                    <RiskBadge level={h.level as RiskLevel} score={h.score} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
