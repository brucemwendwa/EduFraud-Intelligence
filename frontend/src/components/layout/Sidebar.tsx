import { FlaskConical } from 'lucide-react';
import { NavLink } from 'react-router';
import { cn } from '@/lib/cn';
import type { Permission } from '@/lib/permissions';
import { Logo } from './Logo';
import { navSections } from './nav';

interface SidebarProps {
  can: (p: Permission) => boolean;
  onNavigate?: () => void;
  badges?: Partial<Record<string, number>>;
}

export function Sidebar({ can, onNavigate, badges = {} }: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-navy-900 text-navy-100">
      <div className="flex h-16 shrink-0 items-center px-5">
        <NavLink to="/app" onClick={onNavigate} aria-label="EduShield AI dashboard">
          <Logo tone="light" />
        </NavLink>
      </div>
      <nav aria-label="Primary" className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {navSections.map((section) => {
          const items = section.items.filter((i) => !i.permission || can(i.permission));
          if (items.length === 0) return null;
          return (
            <div key={section.title}>
              <p className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-navy-200/60 uppercase">
                {section.title}
              </p>
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <li key={item.to}>
                    {item.planned ? (
                      <span
                        aria-disabled="true"
                        title="Planned: not available in this prototype yet"
                        className="flex cursor-default items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-navy-200/40"
                      >
                        <item.icon className="size-4 shrink-0" aria-hidden />
                        <span className="flex-1 truncate">{item.label}</span>
                        <span className="rounded-full bg-white/5 px-1.5 py-px text-[10px] font-semibold tracking-wide text-navy-200/60 uppercase">
                          Planned
                        </span>
                      </span>
                    ) : (
                      <NavLink
                        to={item.to}
                        end={item.to === '/app'}
                        onClick={onNavigate}
                        className={({ isActive }) =>
                          cn(
                            'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                            isActive
                              ? 'bg-white/10 text-white'
                              : 'text-navy-200/80 hover:bg-white/5 hover:text-white',
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            {isActive && (
                              <span aria-hidden className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-blue-400" />
                            )}
                            <item.icon className="size-4 shrink-0" aria-hidden />
                            <span className="flex-1 truncate">{item.label}</span>
                            {badges[item.to] ? (
                              <span className="tabular rounded-full bg-flag-red px-1.5 py-px text-[11px] font-semibold text-white">
                                {badges[item.to]}
                              </span>
                            ) : null}
                          </>
                        )}
                      </NavLink>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>
      <div className="m-3 rounded-lg border border-white/10 bg-white/5 p-3">
        <div className="flex items-center gap-2 text-xs font-medium text-white">
          <FlaskConical className="size-3.5 text-blue-300" aria-hidden />
          Synthetic demonstration data
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-navy-200/70">
          All students, records and identifiers are fictional. No FSA or FAFSA systems are connected.
        </p>
      </div>
    </div>
  );
}
