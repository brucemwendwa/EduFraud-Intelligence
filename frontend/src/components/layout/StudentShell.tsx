import { LogOut, UserRound } from 'lucide-react';
import { Suspense } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/cn';
import { useAuth } from '@/lib/auth';
import { PageSkeleton } from './AppShell';
import { Logo } from './Logo';

const links = [
  { to: '/student', label: 'Dashboard', end: true },
  { to: '/student/applications', label: 'Applications', end: false },
  { to: '/student/profile', label: 'Profile', end: false },
];

/** Student portal frame: navigation limited to the student's own records, plus sign-out. */
export function StudentShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const signOut = async () => {
    await logout();
    toast.success('Signed out', { description: 'Your session has ended.' });
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Link to="/student" aria-label="EduShield AI student portal home">
            <Logo />
          </Link>
          <nav aria-label="Student portal" className="order-3 flex w-full gap-1 sm:order-none sm:w-auto">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive ? 'bg-navy-50 text-navy-900' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-1.5 text-sm text-slate-600 md:inline-flex">
              <UserRound className="size-4" aria-hidden /> {user?.full_name}
            </span>
            <Button variant="secondary" size="sm" icon={<LogOut className="size-3.5" />} onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-8 sm:px-6"><PageSkeleton /></div>}>
        <Outlet />
      </Suspense>
    </div>
  );
}
