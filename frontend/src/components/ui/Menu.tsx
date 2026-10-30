import * as RMenu from '@radix-ui/react-dropdown-menu';
import * as RTooltip from '@radix-ui/react-tooltip';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export const Menu = RMenu.Root;
export const MenuTrigger = RMenu.Trigger;

export function MenuContent({ children, align = 'end', className }: { children: ReactNode; align?: 'start' | 'end'; className?: string }) {
  return (
    <RMenu.Portal>
      <RMenu.Content
        align={align}
        sideOffset={6}
        className={cn('z-50 min-w-52 rounded-xl border border-slate-200 bg-white p-1 shadow-raised', className)}
      >
        {children}
      </RMenu.Content>
    </RMenu.Portal>
  );
}

export function MenuItem({ children, onSelect, icon, danger }: { children: ReactNode; onSelect?: () => void; icon?: ReactNode; danger?: boolean }) {
  return (
    <RMenu.Item
      onSelect={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm outline-none select-none',
        danger ? 'text-red-700 data-[highlighted]:bg-red-50' : 'text-slate-700 data-[highlighted]:bg-slate-100',
      )}
    >
      {icon && <span className="text-slate-400">{icon}</span>}
      {children}
    </RMenu.Item>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <RMenu.Label className="px-2.5 py-1.5 text-xs font-medium text-slate-500">{children}</RMenu.Label>;
}

export function MenuSeparator() {
  return <RMenu.Separator className="my-1 h-px bg-slate-100" />;
}

export const TooltipProvider = RTooltip.Provider;

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <RTooltip.Root delayDuration={250}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg bg-navy-900 px-2.5 py-1.5 text-xs text-white shadow-raised"
        >
          {content}
          <RTooltip.Arrow className="fill-navy-900" />
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}
