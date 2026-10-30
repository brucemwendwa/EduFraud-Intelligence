import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AlertDetail, AlertRow, AlertSummary, AlertTriage, Page } from '@/api/types';
import { api } from '@/lib/api';

export function useAlerts(params: Record<string, string | string[]>) {
  return useQuery({
    queryKey: ['alerts', 'list', params],
    queryFn: async () =>
      (await api.get<Page<AlertRow>>('/alerts', { params, paramsSerializer: { indexes: null } })).data,
    placeholderData: keepPreviousData,
  });
}

export function useAlertSummary() {
  return useQuery({
    queryKey: ['alerts', 'summary'],
    queryFn: async () => (await api.get<AlertSummary>('/alerts/summary')).data,
  });
}

export function useAlert(id: string | null) {
  return useQuery({
    queryKey: ['alerts', 'detail', id],
    queryFn: async () => (await api.get<AlertDetail>(`/alerts/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useTriageAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: AlertTriage & { id: string }) =>
      (await api.patch<AlertDetail>(`/alerts/${id}`, body)).data,
    onSuccess: (data) => {
      qc.setQueryData(['alerts', 'detail', data.id], data);
      void qc.invalidateQueries({ queryKey: ['alerts', 'list'] });
      void qc.invalidateQueries({ queryKey: ['alerts', 'summary'] });
      void qc.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}
