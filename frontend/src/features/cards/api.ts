import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CardDetail, CardOut, CardSummary, Page } from '@/api/types';
import { invalidateAccountData } from '@/features/accounts/api';
import { api } from '@/lib/api';

export function useCards(params: Record<string, string>) {
  return useQuery({
    queryKey: ['cards', 'list', params],
    queryFn: async () => (await api.get<Page<CardOut>>('/cards', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useCardSummary() {
  return useQuery({
    queryKey: ['cards', 'summary'],
    queryFn: async () => (await api.get<CardSummary>('/cards/summary')).data,
  });
}

export function useCard(id: string | null) {
  return useQuery({
    queryKey: ['cards', 'detail', id],
    queryFn: async () => (await api.get<CardDetail>(`/cards/${id}`)).data,
    enabled: Boolean(id),
  });
}

export type CardAction = 'report-lost' | 'block' | 'suspicious-activity' | 'request-replacement' | 'issue-replacement';

export function useCardAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action, body }: { id: string; action: CardAction; body?: unknown }) =>
      (await api.post<CardDetail>(`/cards/${id}/${action}`, body)).data,
    onSuccess: (data) => {
      qc.setQueryData(['cards', 'detail', data.id], data);
      invalidateAccountData(qc);
    },
  });
}
