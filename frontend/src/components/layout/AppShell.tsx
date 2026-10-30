import * as RDialog from '@radix-ui/react-dialog';
import { FlaskConical, Menu as MenuIcon } from 'lucide-react';
import { Suspense, useState, type ReactNode } from 'react';
import { Outlet } from 'react-router';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/States';
import { InstitutionSelector } from './InstitutionSelector';
import { Sidebar } from './Sidebar';
import { UserMenu } from './UserMenu';

interface AppShellProps {
  search?: ReactNode;
  notifications?: ReactNode;
  badges?: Partial<Record<string, number>>;
}

export function AppShell({ search, notifications, badges }: AppShellProps) {
  const { can } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-white px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar can={can} badges={badges} />
      </aside>

      <RDialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <RDialog.Portal>
          <RDialog.Overlay className="fixed inset-0 z-40 bg-navy-950/50 lg:hidden" />
          <RDialog.Content className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] lg:hidden" aria-describedby={undefined}>
            <RDialog.Title className="sr-only">Navigation</RDialog.Title>
            <Sidebar can={can} badges={badges} onNavigate={() => setMobileOpen(false)} />
          </RDialog.Content>
        </RDialog.Portal>
      </RDialog.Root>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 backdrop-blur-md">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <MenuIcon className="size-5" />
            </Button>
            <div className="min-w-0 flex-1">{search}</div>
            <span className="hidden items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-100 xl:inline-flex">
              <FlaskConical className="size-3.5" aria-hidden />
              Synthetic data
            </span>
            <InstitutionSelector />
            {notifications}
            <UserMenu />
          </div>
        </header>
        <main id="main" className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Suspense fallback={<PageSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading page">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-xl" />
    </div>
  );
}
