import type { ReactNode } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/States';

interface ChartCardProps {
  title: string;
  description?: string;
  loading?: boolean;
  empty?: boolean;
  /** Rows for the accessible data table (column headers come from `columns`). */
  table: { columns: string[]; rows: (string | number)[][] };
  legend?: { label: string; color: string }[];
  children: ReactNode;
  className?: string;
}

/** A chart with its legend and a "View data" table so values are never available by colour alone. */
export function ChartCard({ title, description, loading, empty, table, legend, children, className }: ChartCardProps) {
  return (
    <Card className={className}>
      <CardHeader
        title={title}
        description={description}
        actions={
          legend && legend.length > 1 ? (
            <ul className="flex flex-wrap justify-end gap-x-3 gap-y-1">
              {legend.map((l) => (
                <li key={l.label} className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                  <span aria-hidden className="size-2.5 rounded-sm" style={{ background: l.color }} />
                  {l.label}
                </li>
              ))}
            </ul>
          ) : undefined
        }
      />
      <div className="px-3 pb-2">
        {loading ? (
          <Skeleton className="mx-2 h-56 rounded-lg" />
        ) : empty ? (
          <p className="flex h-56 items-center justify-center text-sm text-slate-500">No data in this scope yet.</p>
        ) : (
          <div className="h-56" role="img" aria-label={`${title} chart. Values are listed in the data table below.`}>
            {children}
          </div>
        )}
      </div>
      {!loading && !empty && (
        <details className="group border-t border-slate-100 px-5 py-2.5 text-xs text-slate-500">
          <summary className="cursor-pointer select-none hover:text-slate-800">View data</summary>
          <div className="mt-2 max-h-56 overflow-auto">
            <table className="w-full text-left">
              <thead>
                <tr>{table.columns.map((c) => <th key={c} className="py-1 pr-3 font-medium text-slate-600">{c}</th>)}</tr>
              </thead>
              <tbody className="tabular">
                {table.rows.map((r, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    {r.map((v, j) => <td key={j} className="py-1 pr-3 text-slate-700">{v}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </Card>
  );
}

/** Series colours, checked for colour-vision separation and contrast on the white card surface. */
export const seriesColor = {
  primary: '#2563EB',
  secondary: '#0d9488',
  warning: '#d97706',
  flagged: '#ea580c',
  grid: '#e2e8f0',
  axis: '#64748b',
};

export const riskColor: Record<string, string> = {
  low: '#16a34a',
  medium: '#d97706',
  high: '#ea580c',
  critical: '#dc2626',
};
