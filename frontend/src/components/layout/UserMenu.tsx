import { LogOut, Settings, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/Menu';

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('');
}

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const signOut = async () => {
    await logout();
    toast.success('Signed out', { description: 'Your session has ended.' });
    navigate('/login', { replace: true });
  };

  return (
    <Menu>
      <MenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2.5 rounded-lg py-1 pr-2 pl-1 hover:bg-slate-100"
          aria-label={`Account menu for ${user.full_name}`}
        >
          <span className="flex size-8 items-center justify-center rounded-full bg-navy-800 text-xs font-semibold text-white">
            {initials(user.full_name)}
          </span>
          <span className="hidden text-left lg:block">
            <span className="block text-sm leading-tight font-medium text-slate-900">{user.full_name}</span>
            <span className="block text-xs leading-tight text-slate-500">{user.role.name}</span>
          </span>
        </button>
      </MenuTrigger>
      <MenuContent>
        <MenuLabel>
          <span className="block text-sm font-medium text-slate-900">{user.full_name}</span>
          <span className="block truncate font-normal">{user.email}</span>
        </MenuLabel>
        <div className="mx-2.5 mb-1.5 inline-flex items-center gap-1.5 rounded-md bg-navy-50 px-2 py-0.5 text-xs font-medium text-navy-800">
          <ShieldCheck className="size-3.5" aria-hidden />
          {user.role.name}
        </div>
        <MenuSeparator />
        <MenuItem icon={<Settings className="size-4" />} onSelect={() => navigate('/app/settings')}>
          Settings
        </MenuItem>
        <MenuItem icon={<LogOut className="size-4" />} onSelect={signOut} danger>
          Sign out
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}
