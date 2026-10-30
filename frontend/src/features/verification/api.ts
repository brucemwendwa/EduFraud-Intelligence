import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  AlternativeVerificationIn,
  BiometricVerificationIn,
  Page,
  ProviderInfo,
  Verification,
  VerificationStats,
} from '@/api/types';
import { api } from '@/lib/api';

export function useProviderInfo() {
  return useQuery({
    queryKey: ['verifications', 'provider'],
    queryFn: async () => (await api.get<ProviderInfo>('/verifications/provider')).data,
    staleTime: Infinity,
  });
}

export function useVerifications(params: Record<string, string>) {
  return useQuery({
    queryKey: ['verifications', 'list', params],
    queryFn: async () => (await api.get<Page<Verification>>('/verifications', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useVerificationStats() {
  return useQuery({
    queryKey: ['verifications', 'stats'],
    queryFn: async () => (await api.get<VerificationStats>('/verifications/stats')).data,
  });
}

export function useVerification(id: string | null) {
  return useQuery({
    queryKey: ['verifications', 'detail', id],
    queryFn: async () => (await api.get<Verification>(`/verifications/${id}`)).data,
    enabled: Boolean(id),
  });
}

function useAfterVerification() {
  const qc = useQueryClient();
  return () => {
    for (const key of ['verifications', 'applications', 'alerts', 'dashboard', 'detection']) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useRunBiometric() {
  const refresh = useAfterVerification();
  return useMutation({
    mutationFn: async (body: BiometricVerificationIn) => (await api.post<Verification>('/verifications', body)).data,
    onSuccess: refresh,
  });
}

export function useRecordAlternative() {
  const refresh = useAfterVerification();
  return useMutation({
    mutationFn: async (body: AlternativeVerificationIn) =>
      (await api.post<Verification>('/verifications/alternative', body)).data,
    onSuccess: refresh,
  });
}
