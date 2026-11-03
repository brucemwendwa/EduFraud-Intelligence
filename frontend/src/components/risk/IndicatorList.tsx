import { ShieldAlert } from 'lucide-react';
import type { Indicator } from '@/api/types';
import { label } from '@/lib/format';

/** Triggered indicators on a transaction or security event, with each one's share of the score. */
export function IndicatorList({ indicators, empty = 'No risk indicators.' }: { indicators: Indicator[]; empty?: string }) {
  if (indicators.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <ul className="space-y-2">
      {indicators.map((i) => (
        <li key={i.code} className="flex gap-3 rounded-lg border border-slate-200 p-3">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-risk-high" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-900">{i.title}</p>
            {i.description && <p className="mt-0.5 text-sm text-slate-600">{i.description}</p>}
            <p className="mt-1 text-[11px] text-slate-500">
              {label(i.category)} · <code>{i.code}</code>
            </p>
          </div>
          <span className="tabular shrink-0 text-sm font-semibold text-slate-900">+{Math.round(i.points)}</span>
        </li>
      ))}
    </ul>
  );
}
