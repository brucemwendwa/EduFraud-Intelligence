import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AccountDetail, AccountRow, AccountSummary, Page } from '@/api/types';
import { api } from '@/lib/api';

export function useAccounts(params: Record<string, string>) {
  return useQuery({
    queryKey: ['accounts', 'list', params],
    queryFn: async () => (await api.get<Page<AccountRow>>('/accounts', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useAccountSummary() {
  return useQuery({
    queryKey: ['accounts', 'summary'],
    queryFn: async () => (await api.get<AccountSummary>('/accounts/summary')).data,
  });
}

export function useAccount(id: string | undefined) {
  return useQuery({
    queryKey: ['accounts', 'detail', id],
    queryFn: async () => (await api.get<AccountDetail>(`/accounts/${id}`)).data,
    enabled: Boolean(id),
  });
}

/** Records touched by any account-protection action. */
export function invalidateAccountData(qc: ReturnType<typeof useQueryClient>) {
  for (const key of ['accounts', 'cards', 'transactions', 'security', 'alerts', 'verification-requests', 'dashboard', 'audit']) {
    void qc.invalidateQueries({ queryKey: [key] });
  }
}

export function useAccountAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ action, reason }: { action: 'restrict' | 'lift-restriction' | 'suspend' | 'reactivate' | 'assess'; reason?: string }) =>
      (await api.post<AccountDetail>(`/accounts/${id}/${action}`, action === 'assess' ? undefined : { reason })).data,
    onSuccess: (data) => {
      qc.setQueryData(['accounts', 'detail', id], data);
      invalidateAccountData(qc);
    },
  });
}
