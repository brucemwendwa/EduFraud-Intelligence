import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/** Compact label/value grid used in drawers and record headers. */
export function DetailList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn('grid grid-cols-2 gap-x-4 gap-y-3 text-sm', className)}>{children}</dl>;
}

export function Detail({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0', className)}>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-slate-800">{children ?? '—'}</dd>
    </div>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h3 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">{children}</h3>
      {action}
    </div>
  );
}
