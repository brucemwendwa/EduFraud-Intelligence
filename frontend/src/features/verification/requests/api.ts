import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  Page,
  VerificationOptions,
  VerificationRequestDetail,
  VerificationRequestRow,
  VerificationRequestSummary,
} from '@/api/types';
import { invalidateAccountData } from '@/features/accounts/api';
import { api } from '@/lib/api';

export function useVerificationRequests(params: Record<string, string | string[]>) {
  return useQuery({
    queryKey: ['verification-requests', 'list', params],
    queryFn: async () =>
      (await api.get<Page<VerificationRequestRow>>('/verification-requests', { params, paramsSerializer: { indexes: null } })).data,
    placeholderData: keepPreviousData,
  });
}

export function useVerificationRequestSummary() {
  return useQuery({
    queryKey: ['verification-requests', 'summary'],
    queryFn: async () => (await api.get<VerificationRequestSummary>('/verification-requests/summary')).data,
  });
}

export function useVerificationOptions() {
  return useQuery({
    queryKey: ['verification-requests', 'options'],
    queryFn: async () => (await api.get<VerificationOptions>('/verification-requests/options')).data,
    staleTime: 5 * 60_000,
  });
}

export function useVerificationRequest(id: string | null) {
  return useQuery({
    queryKey: ['verification-requests', 'detail', id],
    queryFn: async () => (await api.get<VerificationRequestDetail>(`/verification-requests/${id}`)).data,
    enabled: Boolean(id),
  });
}

/** POSTs a workflow step (notify, schedule, start, checks, liveness, decision) and refreshes affected views. */
export function useVerificationStep(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ step, body }: { step: string; body?: unknown }) =>
      (await api.post<VerificationRequestDetail>(`/verification-requests/${id}/${step}`, body)).data,
    onSuccess: (data) => {
      qc.setQueryData(['verification-requests', 'detail', id], data);
      invalidateAccountData(qc);
      void qc.invalidateQueries({ queryKey: ['verifications'] });
    },
  });
}

export function useCreateVerificationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { account_id: string; reason: string; trigger?: string; alert_id?: string; case_id?: string }) =>
      (await api.post<VerificationRequestDetail>('/verification-requests', body)).data,
    onSuccess: () => invalidateAccountData(qc),
  });
}
