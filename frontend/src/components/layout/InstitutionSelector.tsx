import { Building2, Check, ChevronsUpDown, Globe2 } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/Menu';

/** Platform administrators switch institution scope; everyone else sees their own institution. */
export function InstitutionSelector() {
  const { user, activeOrgId, setActiveOrgId } = useAuth();
  if (!user) return null;

  if (!user.is_platform_admin) {
    return (
      <div className="hidden items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 md:flex">
        <Building2 className="size-4 text-navy-600" aria-hidden />
        <span className="max-w-48 truncate font-medium">{user.organization?.name}</span>
      </div>
    );
  }

  const active = user.accessible_organizations.find((o) => o.id === activeOrgId);
  return (
    <Menu>
      <MenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 shadow-sm hover:border-slate-300"
          aria-label="Select institution scope"
        >
          {active ? (
            <Building2 className="size-4 text-navy-600" aria-hidden />
          ) : (
            <Globe2 className="size-4 text-navy-600" aria-hidden />
          )}
          <span className="hidden max-w-44 truncate font-medium sm:inline">{active?.name ?? 'All institutions'}</span>
          <ChevronsUpDown className="size-3.5 text-slate-400" aria-hidden />
        </button>
      </MenuTrigger>
      <MenuContent align="end" className="w-72">
        <MenuLabel>Institution scope</MenuLabel>
        <MenuItem icon={<Globe2 className="size-4" />} onSelect={() => setActiveOrgId(null)}>
          <span className="flex-1">All institutions</span>
          {!activeOrgId && <Check className="size-4 text-brand-blue" />}
        </MenuItem>
        <MenuSeparator />
        {user.accessible_organizations.map((org) => (
          <MenuItem key={org.id} icon={<Building2 className="size-4" />} onSelect={() => setActiveOrgId(org.id)}>
            <span className="flex-1 truncate">{org.name}</span>
            {org.id === activeOrgId && <Check className="size-4 text-brand-blue" />}
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}
