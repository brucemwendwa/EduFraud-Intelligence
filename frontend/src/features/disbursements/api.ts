import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DisbursementDetail, DisbursementRow, DisbursementSummary, Page } from '@/api/types';
import { api } from '@/lib/api';

export function useDisbursements(params: Record<string, string>) {
  return useQuery({
    queryKey: ['disbursements', 'list', params],
    queryFn: async () => (await api.get<Page<DisbursementRow>>('/disbursements', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useDisbursementSummary() {
  return useQuery({
    queryKey: ['disbursements', 'summary'],
    queryFn: async () => (await api.get<DisbursementSummary>('/disbursements/summary')).data,
  });
}

export function useDisbursement(id: string | null) {
  return useQuery({
    queryKey: ['disbursements', 'detail', id],
    queryFn: async () => (await api.get<DisbursementDetail>(`/disbursements/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useHoldAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action, reason }: { id: string; action: 'hold' | 'release'; reason: string }) =>
      (await api.post<DisbursementDetail>(`/disbursements/${id}/${action}`, { reason })).data,
    onSuccess: (data) => {
      qc.setQueryData(['disbursements', 'detail', data.id], data);
      void qc.invalidateQueries({ queryKey: ['disbursements', 'list'] });
      void qc.invalidateQueries({ queryKey: ['disbursements', 'summary'] });
      void qc.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}
