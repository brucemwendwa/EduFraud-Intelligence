import { cn } from '@/lib/cn';

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-8', className)} aria-hidden>
      <path d="M16 2 4 6.5v8.2C4 22.3 9.1 28.6 16 30c6.9-1.4 12-7.7 12-15.3V6.5L16 2Z" fill="currentColor" opacity=".18" />
      <path d="M16 4.6 6.4 8.2v6.5c0 6.3 4 11.5 9.6 12.8 5.6-1.3 9.6-6.5 9.6-12.8V8.2L16 4.6Z" fill="currentColor" />
      <path d="M11 13.2h10M11 16.7h10M11 20.2h6" stroke="var(--logo-stripe, #0B1F3A)" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="21.6" cy="20.2" r="2.1" fill="#B22234" />
    </svg>
  );
}

export function Logo({ tone = 'dark', className }: { tone?: 'dark' | 'light'; className?: string }) {
  const light = tone === 'light';
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark
        className={light ? 'text-white [--logo-stripe:#0B1F3A]' : 'text-navy-900 [--logo-stripe:#ffffff]'}
      />
      <span className={cn('text-[15px] font-semibold tracking-tight', light ? 'text-white' : 'text-navy-900')}>
        EduShield <span className={light ? 'text-blue-300' : 'text-brand-blue'}>AI</span>
      </span>
    </span>
  );
}
