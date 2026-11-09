import { Activity, Building2, MailPlus, UserRoundCog } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { Role, UserRow } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Select } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { SearchInput } from '@/components/ui/SearchInput';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useInstitutions, useInvitations, useRevokeInvitation, useRoles, useUpdateUser, useUsers } from './api';
import { InviteStaffDialog } from './InviteStaffDialog';

const DEFAULTS = { q: '', kind: 'staff', page: '1' };
const NOT_ASSIGNABLE = new Set(['student', 'demo_presenter']);

function status(user: UserRow) {
  if (!user.is_active) return <Badge tone="neutral">Inactive</Badge>;
  if (user.locked_until && new Date(user.locked_until) > new Date()) return <Badge tone="warning">Locked</Badge>;
  return <Badge tone="success">Active</Badge>;
}

export default function AdministrationPage() {
  const { can, user, activeOrgId } = useAuth();
  const manage = can(P.usersManage);
  const roles = useRoles();
  const [inviting, setInviting] = useState(false);
  const assignable = useMemo(
    () => (roles.data ?? []).filter((role) => !role.is_platform_role && !NOT_ASSIGNABLE.has(role.key)),
    [roles.data],
  );
  const needsInstitution = Boolean(user?.is_platform_admin && !activeOrgId);

  return (
    <>
      <PageHeader
        title="Institutions and users"
        description="People and institutions in your scope. Every change is permission-checked and written to the audit trail."
        actions={manage && <Button icon={<MailPlus className="size-4" />} disabled={needsInstitution} title={needsInstitution ? 'Select an institution first' : undefined} onClick={() => setInviting(true)}>Invite staff</Button>}
      />
      <Card>
        <Tabs defaultValue="users">
          <div className="px-5 pt-2">
            <TabsList>
              <TabsTrigger value="users">Users</TabsTrigger>
              <TabsTrigger value="invitations">Invitations</TabsTrigger>
              <TabsTrigger value="institution">Institution</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="users"><Users assignable={assignable} manage={manage} /></TabsContent>
          <TabsContent value="invitations"><Invitations manage={manage} /></TabsContent>
          <TabsContent value="institution"><Institutions /></TabsContent>
        </Tabs>
      </Card>
      <InviteStaffDialog roles={assignable} open={inviting} onOpenChange={setInviting} />
    </>
  );
}

function Users({ assignable, manage }: { assignable: Role[]; manage: boolean }) {
  const { user: me } = useAuth();
  const [filters, setFilters] = useSearchState(DEFAULTS);
  const { data, isLoading, error, refetch } = useUsers({ ...toParams(filters), page_size: '25' });
  const update = useUpdateUser();
  const [confirming, setConfirming] = useState<UserRow | null>(null);

  const apply = (target: UserRow, body: Parameters<typeof update.mutate>[0]['body'], done: string) =>
    update.mutate(
      { id: target.id, body },
      {
        onSuccess: () => toast.success(done),
        onError: (err) => toast.error('Change not saved', { description: errorMessage(err) }),
        onSettled: () => setConfirming(null),
      },
    );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 p-4">
        <div className="w-full sm:w-72"><SearchInput placeholder="Name or email" label="Search users" value={filters.q} onChange={(q) => setFilters({ q })} /></div>
        <Select aria-label="Account type" value={filters.kind} onChange={(e) => setFilters({ kind: e.target.value })} className="w-40">
          <option value="staff">Staff</option>
          <option value="student">Students</option>
        </Select>
      </div>
      {isLoading ? <TableSkeleton rows={6} cols={5} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data || data.items.length === 0 ? <EmptyState icon={<UserRoundCog className="size-5" />} title="No users match" /> : (
        <>
          <Table>
            <THead><tr><TH>Person</TH><TH>Role</TH><TH>Status</TH><TH>Last sign-in</TH>{manage && <TH>Actions</TH>}</tr></THead>
            <tbody>
              {data.items.map((row) => {
                const editable = manage && row.id !== me?.id && !row.is_demo && row.role.key !== 'student' && row.role.key !== 'platform_admin';
                return (
                  <TR key={row.id}>
                    <TD><span className="block font-medium text-slate-900">{row.full_name}</span><span className="text-xs text-slate-500">{row.email}</span></TD>
                    <TD>
                      {editable ? (
                        <Select aria-label={`Role for ${row.full_name}`} value={row.role.key} disabled={update.isPending} onChange={(e) => apply(row, { role_key: e.target.value }, 'Role changed')} className="w-52">
                          {assignable.map((role) => <option key={role.key} value={role.key}>{role.name}</option>)}
                        </Select>
                      ) : row.role.name}
                      {row.is_demo && <Badge tone="blue" className="ml-1.5">Demo</Badge>}
                    </TD>
                    <TD>{status(row)}</TD>
                    <TD className="tabular text-xs whitespace-nowrap">{dateTime(row.last_login_at)}</TD>
                    {manage && (
                      <TD>
                        {editable && (
                          <div className="flex gap-2">
                            <Button size="sm" variant="secondary" onClick={() => (row.is_active ? setConfirming(row) : apply(row, { is_active: true }, 'Account activated'))}>{row.is_active ? 'Deactivate' : 'Activate'}</Button>
                            {row.locked_until && new Date(row.locked_until) > new Date() && <Button size="sm" variant="secondary" onClick={() => apply(row, { unlock: true }, 'Account unlocked')}>Unlock</Button>}
                          </div>
                        )}
                      </TD>
                    )}
                  </TR>
                );
              })}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(page) => setFilters({ page: String(page) })} />
        </>
      )}
      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={`Deactivate ${confirming?.full_name ?? 'this account'}?`}
        description="They lose access immediately, including any open sessions. You can reactivate the account later."
        confirmLabel="Deactivate account"
        tone="danger"
        loading={update.isPending}
        onConfirm={() => confirming && apply(confirming, { is_active: false }, 'Account deactivated')}
      />
    </div>
  );
}

function Invitations({ manage }: { manage: boolean }) {
  const { data, isLoading, error, refetch } = useInvitations();
  const revoke = useRevokeInvitation();
  if (isLoading) return <TableSkeleton rows={3} cols={4} />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || data.length === 0) return <EmptyState icon={<MailPlus className="size-5" />} title="No pending invitations" />;
  return (
    <Table>
      <THead><tr><TH>Person</TH><TH>Role</TH><TH>Expires</TH>{manage && <TH>Actions</TH>}</tr></THead>
      <tbody>
        {data.map((invitation) => (
          <TR key={invitation.id}>
            <TD><span className="block font-medium text-slate-900">{invitation.full_name}</span><span className="text-xs text-slate-500">{invitation.email}</span></TD>
            <TD>{invitation.role_name}</TD>
            <TD className="tabular text-xs whitespace-nowrap">{dateTime(invitation.expires_at)}</TD>
            {manage && (
              <TD>
                <Button size="sm" variant="secondary" loading={revoke.isPending && revoke.variables === invitation.id} onClick={() => revoke.mutate(invitation.id, { onSuccess: () => toast.success('Invitation revoked'), onError: (err) => toast.error('Could not revoke', { description: errorMessage(err) }) })}>Revoke</Button>
              </TD>
            )}
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function Institutions() {
  const { can } = useAuth();
  const { data, isLoading, error, refetch } = useInstitutions();
  if (isLoading) return <TableSkeleton rows={2} cols={5} />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || data.length === 0) return <EmptyState icon={<Building2 className="size-5" />} title="No institutions in scope" />;
  return (
    <div>
      <Table>
        <THead><tr><TH>Institution</TH><TH>Type</TH><TH>Status</TH><TH className="text-right">Users</TH><TH className="text-right">Applications</TH><TH className="text-right">Open alerts</TH></tr></THead>
        <tbody>
          {data.map((institution) => (
            <TR key={institution.id}>
              <TD><span className="block font-medium text-slate-900">{institution.name}</span><span className="text-xs text-slate-500">{institution.city}, {institution.state}</span></TD>
              <TD>{label(institution.institution_type)}</TD>
              <TD><Badge tone={institution.is_active ? 'success' : 'neutral'}>{institution.is_active ? 'Active' : 'Inactive'}</Badge></TD>
              <TD className="tabular text-right">{institution.user_count.toLocaleString()}</TD>
              <TD className="tabular text-right">{institution.application_count.toLocaleString()}</TD>
              <TD className="tabular text-right">{institution.open_alert_count.toLocaleString()}</TD>
            </TR>
          ))}
        </tbody>
      </Table>
      {can(P.operationsRead) && <Link to="/app/operations" className="m-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-blue hover:underline"><Activity className="size-4" /> View operational status</Link>}
    </div>
  );
}
