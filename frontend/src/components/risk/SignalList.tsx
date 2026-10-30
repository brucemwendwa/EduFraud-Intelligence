import { BrainCircuit, Fingerprint, Network, ScrollText, type LucideIcon } from 'lucide-react';
import type { FraudSignal } from '@/api/types';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Tooltip } from '@/components/ui/Menu';
import { cn } from '@/lib/cn';
import { label } from '@/lib/format';

const methods: Record<string, { label: string; Icon: LucideIcon }> = {
  rule: { label: 'Rule', Icon: ScrollText },
  graph: { label: 'Graph analysis', Icon: Network },
  anomaly_model: { label: 'Anomaly model', Icon: BrainCircuit },
  biometric: { label: 'Biometric check', Icon: Fingerprint },
};

const severityTone: Record<string, Tone> = {
  info: 'neutral',
  low: 'neutral',
  medium: 'warning',
  high: 'high',
  critical: 'critical',
};

const barColor: Record<string, string> = {
  info: 'bg-slate-300',
  low: 'bg-slate-400',
  medium: 'bg-risk-medium',
  high: 'bg-risk-high',
  critical: 'bg-risk-critical',
};

/** Explainable signals: each row shows how many points it contributed to the final score. */
export function SignalList({ signals, compact }: { signals: FraudSignal[]; compact?: boolean }) {
  const max = Math.max(1, ...signals.map((s) => s.points));
  return (
    <ol className="space-y-3">
      {signals.map((s) => {
        const method = methods[s.method] ?? methods.rule!;
        return (
          <li key={s.code} className="rounded-lg border border-slate-200 p-3.5">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-navy-50 text-navy-700">
                <method.Icon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <p className="text-sm font-medium text-slate-900">{s.title}</p>
                  <Badge tone={severityTone[s.severity] ?? 'neutral'}>{label(s.severity)}</Badge>
                </div>
                {!compact && <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.description}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                  <span>{method.label}</span>
                  <code>{s.code}</code>
                  <span>{s.version}</span>
                </div>
              </div>
              <Tooltip content={`Contributes ${s.points.toFixed(1)} of the score (signal strength ${s.weight.toFixed(2)})`}>
                <div className="w-24 shrink-0 text-right" tabIndex={0}>
                  <p className="tabular text-sm font-semibold text-slate-900">+{s.points.toFixed(0)}</p>
                  <div className="mt-1.5 h-1.5 rounded-full bg-slate-100">
                    <div
                      className={cn('ml-auto h-1.5 rounded-full', barColor[s.severity] ?? 'bg-slate-400')}
                      style={{ width: `${Math.max(4, (s.points / max) * 100)}%` }}
                    />
                  </div>
                </div>
              </Tooltip>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
