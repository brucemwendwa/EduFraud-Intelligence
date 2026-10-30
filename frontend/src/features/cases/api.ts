import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  Assignee,
  CaseDecisionIn,
  CaseDetail,
  CaseEvidenceCreate,
  CaseRow,
  CaseSummary,
  Page,
} from '@/api/types';
import { api } from '@/lib/api';

export const caseKeys = {
  all: ['cases'] as const,
  detail: (id: string) => ['cases', 'detail', id] as const,
};

export function useCases(params: Record<string, string | string[]>) {
  return useQuery({
    queryKey: ['cases', 'list', params],
    queryFn: async () => (await api.get<Page<CaseRow>>('/cases', { params, paramsSerializer: { indexes: null } })).data,
    placeholderData: keepPreviousData,
  });
}

export function useCaseSummary() {
  return useQuery({ queryKey: ['cases', 'summary'], queryFn: async () => (await api.get<CaseSummary>('/cases/summary')).data });
}

export function useCase(id: string) {
  return useQuery({ queryKey: caseKeys.detail(id), queryFn: async () => (await api.get<CaseDetail>(`/cases/${id}`)).data });
}

export function useAssignees(enabled: boolean) {
  return useQuery({
    queryKey: ['cases', 'assignees'],
    queryFn: async () => (await api.get<Assignee[]>('/cases/assignees')).data,
    enabled,
    staleTime: 60_000,
  });
}

/** Every case mutation returns the refreshed workspace; related lists refresh too. */
function useCaseMutation<TBody>(id: string, request: (body: TBody) => Promise<CaseDetail>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (data) => {
      qc.setQueryData(caseKeys.detail(id), data);
      for (const key of ['cases', 'alerts', 'applications']) void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}

export const useAssignCase = (id: string) =>
  useCaseMutation(id, async (body: { assigned_to_id: string | null; note?: string }) => (await api.post<CaseDetail>(`/cases/${id}/assign`, body)).data);

export const useStartReview = (id: string) =>
  useCaseMutation(id, async () => (await api.patch<CaseDetail>(`/cases/${id}`, { status: 'under_review' })).data);

export const useAddNote = (id: string) =>
  useCaseMutation(id, async (body: { body: string }) => (await api.post<CaseDetail>(`/cases/${id}/notes`, body)).data);

export const useAddEvidence = (id: string) =>
  useCaseMutation(id, async (body: CaseEvidenceCreate) => (await api.post<CaseDetail>(`/cases/${id}/evidence`, body)).data);

export const useDecision = (id: string) =>
  useCaseMutation(id, async (body: CaseDecisionIn) => (await api.post<CaseDetail>(`/cases/${id}/decision`, body)).data);

export function useOpenCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { application_id?: string; alert_id?: string }) => (await api.post<CaseDetail>('/cases', body)).data,
    onSuccess: () => {
      for (const key of ['cases', 'alerts', 'applications']) void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}
