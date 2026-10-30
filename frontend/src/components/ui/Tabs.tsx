import * as RTabs from '@radix-ui/react-tabs';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export const Tabs = RTabs.Root;
export const TabsContent = RTabs.Content;

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <RTabs.List
      className={cn('flex gap-1 overflow-x-auto border-b border-slate-200 [scrollbar-width:none]', className)}
    >
      {children}
    </RTabs.List>
  );
}

export function TabsTrigger({ value, children, count }: { value: string; children: ReactNode; count?: number }) {
  return (
    <RTabs.Trigger
      value={value}
      className={cn(
        '-mb-px inline-flex items-center gap-2 border-b-2 border-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap text-slate-500 transition-colors',
        'hover:text-slate-800 data-[state=active]:border-navy-900 data-[state=active]:text-navy-900',
      )}
    >
      {children}
      {count != null && (
        <span className="tabular rounded-full bg-slate-100 px-1.5 py-px text-[11px] text-slate-600">{count}</span>
      )}
    </RTabs.Trigger>
  );
}
