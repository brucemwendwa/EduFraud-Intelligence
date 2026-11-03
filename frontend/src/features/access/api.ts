import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DeviceOut, Page, SecurityEventRow, SecuritySummary } from '@/api/types';
import { invalidateAccountData } from '@/features/accounts/api';
import { api } from '@/lib/api';

export function useSecurityEvents(params: Record<string, string | string[]>) {
  return useQuery({
    queryKey: ['security', 'events', params],
    queryFn: async () =>
      (await api.get<Page<SecurityEventRow>>('/security/events', { params, paramsSerializer: { indexes: null } })).data,
    placeholderData: keepPreviousData,
  });
}

export function useSecurityEvent(id: string | null) {
  return useQuery({
    queryKey: ['security', 'event', id],
    queryFn: async () => (await api.get<SecurityEventRow>(`/security/events/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useSecuritySummary() {
  return useQuery({
    queryKey: ['security', 'summary'],
    queryFn: async () => (await api.get<SecuritySummary>('/security/summary')).data,
  });
}

export function useDevices(params: Record<string, string>) {
  return useQuery({
    queryKey: ['security', 'devices', params],
    queryFn: async () => (await api.get<Page<DeviceOut>>('/security/devices', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useSetDeviceTrust() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, trust_status, reason }: { id: string; trust_status: 'trusted' | 'suspicious'; reason: string }) =>
      (await api.post<DeviceOut>(`/security/devices/${id}/trust`, { trust_status, reason })).data,
    onSuccess: () => invalidateAccountData(qc),
  });
}
