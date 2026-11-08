import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const can = vi.fn();
const me = { id: 'me', is_platform_admin: false };
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ can, user: me, activeOrgId: null }) }));
const staff = (id: string, name: string, role: string, extra = {}) => ({ id, full_name: name, email: `${id}@x.edu`, title: null, role: { key: role, name: role }, organization: null, is_active: true, is_demo: false, last_login_at: null, locked_until: null, created_at: '2026-01-01T00:00:00Z', ...extra });
const roles = [
  { key: 'platform_admin', name: 'Platform Administrator', is_platform_role: true },
  { key: 'institution_admin', name: 'Institution Administrator', is_platform_role: false },
  { key: 'financial_aid_officer', name: 'Financial Aid Officer', is_platform_role: false },
  { key: 'student', name: 'Student', is_platform_role: false },
  { key: 'demo_presenter', name: 'Demo Presenter', is_platform_role: false },
];
vi.mock('./api', () => ({
  useRoles: () => ({ data: roles }),
  useUsers: () => ({ isLoading: false, error: null, refetch: vi.fn(), data: { items: [staff('me', 'Me Myself', 'institution_admin'), staff('a', 'Ana Officer', 'financial_aid_officer'), staff('d', 'Dee Demo', 'auditor', { is_demo: true })], total: 3, page: 1, page_size: 25 } }),
  useUpdateUser: () => ({ mutate: vi.fn(), isPending: false }),
  useInvitations: () => ({ data: [], isLoading: false, error: null, refetch: vi.fn() }),
  useRevokeInvitation: () => ({ mutate: vi.fn(), isPending: false }),
  useInstitutions: () => ({ data: [], isLoading: false, error: null, refetch: vi.fn() }),
  useInviteStaff: () => ({ mutate: vi.fn(), isPending: false }),
}));
import AdministrationPage from './AdministrationPage';

describe('AdministrationPage', () => {
  beforeEach(() => can.mockReset());

  it('never offers platform, student or demo roles', () => {
    can.mockReturnValue(true);
    renderWithProviders(<AdministrationPage />);
    const options = Array.from(screen.getByLabelText('Role for Ana Officer').querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['institution_admin', 'financial_aid_officer']);
  });

  it('offers no controls on your own account or demonstration accounts', () => {
    can.mockReturnValue(true);
    renderWithProviders(<AdministrationPage />);
    expect(screen.queryByLabelText('Role for Me Myself')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Role for Dee Demo')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Deactivate' })).toHaveLength(1);
  });

  it('is read-only without the manage permission', () => {
    can.mockImplementation((permission: string) => permission === 'users:read');
    renderWithProviders(<AdministrationPage />);
    expect(screen.queryByRole('button', { name: 'Invite staff' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Role for Ana Officer')).not.toBeInTheDocument();
  });
});
