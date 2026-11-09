import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Page, TransactionDetail, TransactionRow, TransactionSummary } from '@/api/types';
import { invalidateAccountData } from '@/features/accounts/api';
import { api } from '@/lib/api';

export function useTransactions(params: Record<string, string>) {
  return useQuery({
    queryKey: ['transactions', 'list', params],
    queryFn: async () => (await api.get<Page<TransactionRow>>('/transactions', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useTransactionSummary() {
  return useQuery({
    queryKey: ['transactions', 'summary'],
    queryFn: async () => (await api.get<TransactionSummary>('/transactions/summary')).data,
  });
}

export function useTransaction(id: string | null) {
  return useQuery({
    queryKey: ['transactions', 'detail', id],
    queryFn: async () => (await api.get<TransactionDetail>(`/transactions/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useReviewTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, decision, note }: { id: string; decision: 'cleared' | 'suspicious'; note: string }) =>
      (await api.post<TransactionDetail>(`/transactions/${id}/review`, { decision, note })).data,
    onSuccess: (data) => {
      qc.setQueryData(['transactions', 'detail', data.id], data);
      invalidateAccountData(qc);
    },
  });
}
