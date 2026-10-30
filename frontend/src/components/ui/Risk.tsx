import { AlertOctagon, AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Badge, type Tone } from './Badge';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export const riskMeta: Record<RiskLevel, { label: string; tone: Tone; color: string; Icon: typeof ShieldCheck }> =
  {
    low: { label: 'Low', tone: 'success', color: 'var(--color-risk-low)', Icon: ShieldCheck },
    medium: { label: 'Medium', tone: 'warning', color: 'var(--color-risk-medium)', Icon: AlertTriangle },
    high: { label: 'High', tone: 'high', color: 'var(--color-risk-high)', Icon: ShieldAlert },
    critical: { label: 'Critical', tone: 'critical', color: 'var(--color-risk-critical)', Icon: AlertOctagon },
  };

export function riskLevelOf(score: number): RiskLevel {
  if (score >= 80) return 'critical';
  if (score >= 60) return 'high';
  if (score >= 30) return 'medium';
  return 'low';
}

/** Risk level always ships with an icon + label so it never relies on colour alone. */
export function RiskBadge({ level, score }: { level: RiskLevel | null | undefined; score?: number | null }) {
  if (!level) return <Badge tone="neutral">Not assessed</Badge>;
  const meta = riskMeta[level];
  return (
    <Badge tone={meta.tone} icon={<meta.Icon className="size-3.5" aria-hidden />}>
      {meta.label}
      {score != null && <span className="tabular font-semibold">· {Math.round(score)}</span>}
    </Badge>
  );
}

interface RingProps {
  score: number;
  level?: RiskLevel;
  size?: number;
  className?: string;
}

export function RiskScoreRing({ score, level, size = 96, className }: RingProps) {
  const lvl = level ?? riskLevelOf(score);
  const stroke = Math.max(6, size / 12);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(100, Math.max(0, score)) / 100;
  return (
    <div
      className={cn('relative inline-flex items-center justify-center', className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Risk score ${Math.round(score)} of 100, ${riskMeta[lvl].label} risk`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-slate-100)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={riskMeta[lvl].color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
          className="transition-[stroke-dasharray] duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="tabular font-semibold text-slate-900" style={{ fontSize: size / 3.6 }}>
          {Math.round(score)}
        </span>
        <span className="text-[10px] font-medium tracking-wide text-slate-500 uppercase">of 100</span>
      </div>
    </div>
  );
}
