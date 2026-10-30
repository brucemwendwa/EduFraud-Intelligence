import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import {
  Bell,
  Building2,
  CalendarDays,
  CreditCard,
  EyeOff,
  FileText,
  Fingerprint,
  Globe,
  Laptop,
  Phone,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import { memo } from 'react';
import type { NetworkNode } from '@/api/types';
import { cn } from '@/lib/cn';

export const entityTypes: Record<string, { label: string; Icon: LucideIcon; tone: string }> = {
  application: { label: 'Application', Icon: FileText, tone: 'bg-white text-navy-900 border-navy-700' },
  student: { label: 'Student', Icon: UserRound, tone: 'bg-slate-50 text-slate-700 border-slate-300' },
  institution: { label: 'Institution', Icon: Building2, tone: 'bg-navy-900 text-white border-navy-900' },
  enrollment: { label: 'Enrollment', Icon: CalendarDays, tone: 'bg-slate-50 text-slate-600 border-slate-300' },
  destination: { label: 'Payment destination', Icon: CreditCard, tone: 'bg-red-50 text-flag-red border-flag-red' },
  device: { label: 'Device', Icon: Laptop, tone: 'bg-blue-50 text-brand-blue border-brand-blue' },
  network: { label: 'Network address', Icon: Globe, tone: 'bg-sky-50 text-sky-700 border-sky-500' },
  ssn: { label: 'SSN token', Icon: Fingerprint, tone: 'bg-violet-50 text-violet-700 border-violet-500' },
  phone: { label: 'Phone token', Icon: Phone, tone: 'bg-amber-50 text-amber-800 border-amber-500' },
  alert: { label: 'Alert', Icon: Bell, tone: 'bg-red-50 text-red-700 border-red-400' },
  external: { label: 'Other institution', Icon: EyeOff, tone: 'bg-white text-slate-500 border-slate-300 border-dashed' },
};

const riskRing: Record<string, string> = {
  critical: 'ring-4 ring-risk-critical/25 border-risk-critical',
  high: 'ring-4 ring-risk-high/25 border-risk-high',
  medium: 'ring-2 ring-risk-medium/25 border-risk-medium',
  low: 'border-risk-low',
};

export type EntityNodeData = NetworkNode & { dimmed?: boolean };
export type EntityFlowNode = Node<EntityNodeData, 'entity'>;

/** One graph entity: icon + label so type is never conveyed by colour alone. */
export const EntityNode = memo(function EntityNode({ data, selected }: NodeProps<EntityFlowNode>) {
  const meta = entityTypes[data.type] ?? entityTypes.application!;
  const risk = data.type === 'application' && data.risk_level ? riskRing[data.risk_level] : undefined;
  return (
    <div className={cn('flex max-w-48 items-center gap-2 transition-opacity', data.dimmed && 'opacity-25')}>
      <Handle type="target" position={Position.Top} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" style={{ top: '50%' }} />
      <span
        className={cn(
          'flex size-9 shrink-0 items-center justify-center rounded-full border-2 shadow-sm',
          meta.tone,
          risk,
          selected && 'outline-2 outline-offset-2 outline-brand-blue',
        )}
      >
        <meta.Icon className="size-4" aria-hidden />
      </span>
      <span className="min-w-0 rounded-md bg-white/90 px-1.5 py-0.5 shadow-sm ring-1 ring-slate-200/70">
        <span className="block truncate text-[11px] leading-tight font-semibold text-slate-900">{data.label}</span>
        {data.sublabel && <span className="block truncate text-[10px] leading-tight text-slate-500">{data.sublabel}</span>}
      </span>
      <Handle type="source" position={Position.Bottom} className="!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" style={{ top: '50%', left: 18 }} />
    </div>
  );
});
