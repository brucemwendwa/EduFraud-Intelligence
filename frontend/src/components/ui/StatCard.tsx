import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { cn } from '@/lib/cn';
import { Card } from './Card';
import { Skeleton } from './States';

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  /** Signed change vs. a named period, e.g. { value: 12, period: 'vs. prior 30 days' }. */
  delta?: { value: number; period: string; upIsGood?: boolean };
  footnote?: ReactNode;
  to?: string;
  loading?: boolean;
  accent?: 'navy' | 'critical' | 'warning' | 'success' | 'blue';
}

const accents = {
  navy: 'bg-navy-50 text-navy-700',
  critical: 'bg-red-50 text-risk-critical',
  warning: 'bg-amber-50 text-risk-medium',
  success: 'bg-green-50 text-risk-low',
  blue: 'bg-blue-50 text-brand-blue',
};

export function StatCard({ label, value, icon, delta, footnote, to, loading, accent = 'navy' }: StatCardProps) {
  const body = (
    <Card className={cn('h-full p-5', to && 'transition-shadow hover:shadow-raised')}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        {icon && <div className={cn('flex size-8 items-center justify-center rounded-lg', accents[accent])}>{icon}</div>}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-24" />
      ) : (
        <p className="tabular mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      )}
      <div className="mt-2 flex min-h-5 flex-wrap items-center gap-x-2 text-xs text-slate-500">
        {delta && !loading && <Delta {...delta} />}
        {footnote}
      </div>
    </Card>
  );
  return to ? (
    <Link to={to} className="block rounded-xl focus-visible:outline-2">
      {body}
    </Link>
  ) : (
    body
  );
}

function Delta({ value, period, upIsGood = true }: { value: number; period: string; upIsGood?: boolean }) {
  const up = value >= 0;
  const good = up === upIsGood;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn('inline-flex items-center font-medium', good ? 'text-green-700' : 'text-red-700')}>
        <Icon className="size-3.5" aria-hidden />
        {up ? '+' : '−'}
        {Math.abs(value)}%
      </span>
      <span>{period}</span>
    </span>
  );
}

/** Compact number formatting for tiles: 1,284 / 12.9K / 4.2M. */
export function compact(n: number) {
  return new Intl.NumberFormat('en-US', { notation: n >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(n);
}
