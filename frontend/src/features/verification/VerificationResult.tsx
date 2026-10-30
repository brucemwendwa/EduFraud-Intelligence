import { ArrowUpRight, CheckCircle2, CircleDashed, FileScan, HelpCircle, ScanFace, ShieldAlert, Sparkles, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import type { Verification } from '@/api/types';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { cn } from '@/lib/cn';
import { dateTime, label } from '@/lib/format';
import { verificationStatusTone } from '@/lib/status';

const stageMeta: Record<string, { title: string; Icon: typeof FileScan }> = {
  document: { title: 'Identity document', Icon: FileScan },
  face_match: { title: 'Face comparison', Icon: ScanFace },
  liveness: { title: 'Liveness', Icon: Sparkles },
  presentation_attack: { title: 'Presentation attack detection', Icon: ShieldAlert },
};

const outcomeIcon = {
  pass: <CheckCircle2 className="size-5 text-risk-low" aria-label="Passed" />,
  fail: <XCircle className="size-5 text-risk-critical" aria-label="Failed" />,
  inconclusive: <HelpCircle className="size-5 text-risk-medium" aria-label="Inconclusive" />,
  not_performed: <CircleDashed className="size-5 text-slate-300" aria-label="Not performed" />,
} as const;

/** Stage-by-stage verification outcome. `animate` reveals stages one by one after a live run. */
export function VerificationResult({ v, animate = false }: { v: Verification; animate?: boolean }) {
  const [shown, setShown] = useState(animate ? 0 : v.stages.length);
  useEffect(() => {
    if (shown >= v.stages.length) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const t = window.setTimeout(() => setShown((n) => n + 1), reduce ? 0 : 450);
    return () => window.clearTimeout(t);
  }, [shown, v.stages.length]);
  const done = shown >= v.stages.length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={v.status} map={verificationStatusTone} />
        <Badge tone={v.provider_mode === 'simulation' ? 'blue' : 'neutral'}>
          {v.provider_mode === 'simulation' ? 'Simulated provider' : 'Recorded by staff'}
        </Badge>
        <span className="text-xs text-slate-500">
          {v.reference} · {label(v.trigger)} · {dateTime(v.completed_at ?? v.created_at)}
        </span>
      </div>

      {v.stages.length > 0 ? (
        <ol className="space-y-2" aria-live="polite">
          {v.stages.map((s, i) => {
            const meta = stageMeta[s.stage] ?? { title: label(s.stage), Icon: FileScan };
            const visible = i < shown;
            return (
              <li
                key={s.stage}
                className={cn(
                  'flex items-center gap-3 rounded-lg border px-3.5 py-3 transition-opacity',
                  visible ? 'opacity-100' : 'opacity-40',
                  visible && s.outcome === 'fail' ? 'border-red-200 bg-red-50/50' : 'border-slate-200',
                )}
              >
                <meta.Icon className="size-4 shrink-0 text-navy-600" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">{meta.title}</p>
                  <p className="text-xs text-slate-500">{visible ? s.detail : 'Checking…'}</p>
                </div>
                {visible ? outcomeIcon[s.outcome as keyof typeof outcomeIcon] : <CircleDashed className="size-5 animate-spin text-slate-300" aria-hidden />}
              </li>
            );
          })}
        </ol>
      ) : (
        v.notes && <p className="rounded-lg bg-slate-50 p-3.5 text-sm text-slate-700">“{v.notes}” · {v.initiated_by}</p>
      )}

      {done && (
        <>
          {v.risk_indicators.length > 0 && (
            <ul className="space-y-1.5">
              {v.risk_indicators.map((r) => (
                <li key={r} className="flex gap-2 text-sm text-red-800">
                  <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{r}
                </li>
              ))}
            </ul>
          )}
          <div
            className={cn(
              'rounded-lg px-3.5 py-3 text-sm ring-1',
              v.status === 'passed' ? 'bg-green-50 text-green-900 ring-green-100' : 'bg-amber-50 text-amber-900 ring-amber-100',
            )}
          >
            <span className="font-medium">Recommended next action:</span> {v.recommended_action}
          </div>
          {v.application_id && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3.5 py-3">
              <div className="flex items-center gap-2 text-sm text-slate-700">
                Application risk after this check
                <RiskBadge level={v.resulting_risk_level as RiskLevel | null} score={v.resulting_risk_score} />
              </div>
              <Link to={`/app/applications/${v.application_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">
                {v.application_ref} <ArrowUpRight className="size-3.5" />
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}
