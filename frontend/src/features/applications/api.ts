import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApplicationDetail, ApplicationRow, Page, RevealResponse, ReviewUpdate } from '@/api/types';
import { api } from '@/lib/api';

export const applicationKeys = {
  all: ['applications'] as const,
  list: (params: Record<string, string>) => ['applications', 'list', params] as const,
  detail: (id: string) => ['applications', 'detail', id] as const,
};

export function useApplications(params: Record<string, string>) {
  return useQuery({
    queryKey: applicationKeys.list(params),
    queryFn: async () => (await api.get<Page<ApplicationRow>>('/applications', { params })).data,
    placeholderData: keepPreviousData,
  });
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: applicationKeys.detail(id),
    queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${id}`)).data,
  });
}

export function useReviewApplication(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ReviewUpdate) => (await api.patch<ApplicationRow>(`/applications/${id}/review`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: applicationKeys.all }),
  });
}

export function useRevealStudent() {
  return useMutation({
    mutationFn: async ({ studentId, reason }: { studentId: string; reason: string }) =>
      (await api.post<RevealResponse>(`/students/${studentId}/reveal`, { reason })).data,
  });
}

export function useAssessApplication(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>(`/applications/${id}/assess`)).data,
    onSuccess: (data) => {
      qc.setQueryData(applicationKeys.detail(id), data);
      void qc.invalidateQueries({ queryKey: ['applications', 'list'] });
      void qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}
