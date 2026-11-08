import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Organization, Page, Role, StaffInvitation, StaffInvitationCreate, UserRow, UserUpdate } from '@/api/types';
import { api } from '@/lib/api';

const keys = { users: ['admin', 'users'] as const, invitations: ['admin', 'invitations'] as const };

export function useUsers(params: Record<string, string>) {
  return useQuery({
    queryKey: [...keys.users, params],
    queryFn: async () => (await api.get<Page<UserRow>>('/users', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export const useRoles = () =>
  useQuery({ queryKey: ['admin', 'roles'], queryFn: async () => (await api.get<Role[]>('/roles')).data, staleTime: 300_000 });

export const useInstitutions = () =>
  useQuery({ queryKey: ['admin', 'institutions'], queryFn: async () => (await api.get<Organization[]>('/organizations')).data });

export const useInvitations = () =>
  useQuery({ queryKey: keys.invitations, queryFn: async () => (await api.get<StaffInvitation[]>('/staff-invitations')).data });

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: UserUpdate }) => (await api.patch<UserRow>(`/users/${id}`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useInviteStaff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: StaffInvitationCreate) => (await api.post<StaffInvitation>('/staff-invitations', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invitations }),
  });
}

export function useRevokeInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => (await api.post<StaffInvitation>(`/staff-invitations/${id}/revoke`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invitations }),
  });
}
