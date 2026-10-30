import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type Tone = 'neutral' | 'navy' | 'blue' | 'success' | 'warning' | 'high' | 'critical' | 'violet';

const tones: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
  navy: 'bg-navy-50 text-navy-800 ring-navy-100',
  blue: 'bg-blue-50 text-blue-700 ring-blue-100',
  success: 'bg-green-50 text-green-700 ring-green-100',
  warning: 'bg-amber-50 text-amber-800 ring-amber-100',
  high: 'bg-orange-50 text-orange-800 ring-orange-100',
  critical: 'bg-red-50 text-red-700 ring-red-100',
  violet: 'bg-violet-50 text-violet-700 ring-violet-100',
};

const dots: Record<Tone, string> = {
  neutral: 'bg-slate-400',
  navy: 'bg-navy-600',
  blue: 'bg-brand-blue',
  success: 'bg-risk-low',
  warning: 'bg-risk-medium',
  high: 'bg-risk-high',
  critical: 'bg-risk-critical',
  violet: 'bg-violet-500',
};

interface BadgeProps {
  tone?: Tone;
  dot?: boolean;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ tone = 'neutral', dot, icon, children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset',
        tones[tone],
        className,
      )}
    >
      {dot && <span aria-hidden className={cn('size-1.5 rounded-full', dots[tone])} />}
      {icon}
      {children}
    </span>
  );
}

/** Maps a backend status/enum value to a badge tone; unknown values fall back to neutral. */
export function StatusBadge({ value, map }: { value: string; map: Record<string, Tone> }) {
  return (
    <Badge tone={map[value] ?? 'neutral'} dot>
      {humanize(value)}
    </Badge>
  );
}

export function humanize(value: string) {
  return value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
