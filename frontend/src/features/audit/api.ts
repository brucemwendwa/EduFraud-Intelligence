import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import type { AuditEvent, AuditSummary, ChainVerification, Page } from '@/api/types';
import { api } from '@/lib/api';

export function useAuditEvents(params: Record<string, string>) {
  return useQuery({
    queryKey: ['audit', 'events', params],
    queryFn: async () => (await api.get<Page<AuditEvent>>('/audit/events', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useAuditSummary() {
  return useQuery({
    queryKey: ['audit', 'summary'],
    queryFn: async () => (await api.get<AuditSummary>('/audit/summary')).data,
  });
}

export function useVerifyChain() {
  return useMutation({
    mutationFn: async () => (await api.get<ChainVerification>('/audit/verify')).data,
  });
}
