import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { StudentApplication, StudentApplicationDraft, StudentDashboard } from '@/api/types';
import { api } from '@/lib/api';

const key = ['student-applications'] as const;
const dashboardKey = ['student-dashboard'] as const;

/** How the portal groups application statuses. Mirrors the counts returned by the dashboard API. */
export const STATUS_GROUPS = {
  draft: { label: 'Drafts', statuses: ['draft'] },
  additional_information: { label: 'Action needed', statuses: ['additional_information_required'] },
  submitted: { label: 'Submitted', statuses: ['submitted', 'received'] },
  under_review: { label: 'Under review', statuses: ['in_review', 'on_hold'] },
  approved: { label: 'Approved', statuses: ['approved'] },
  rejected: { label: 'Not approved', statuses: ['rejected'] },
  withdrawn: { label: 'Withdrawn', statuses: ['withdrawn'] },
} as const;
export type StatusGroup = keyof typeof STATUS_GROUPS;

export const isStatusGroup = (value: string | null): value is StatusGroup =>
  value !== null && Object.prototype.hasOwnProperty.call(STATUS_GROUPS, value);

export const useStudentDashboard = () =>
  useQuery({
    queryKey: dashboardKey,
    queryFn: async () => (await api.get<StudentDashboard>('/student-portal/dashboard')).data,
  });

export const useStudentApplications = () =>
  useQuery({
    queryKey: key,
    queryFn: async () => (await api.get<StudentApplication[]>('/student-applications')).data,
  });

export const useStudentApplication = (id: string | undefined) =>
  useQuery({
    queryKey: [...key, id],
    enabled: Boolean(id),
    queryFn: async () => (await api.get<StudentApplication>(`/student-applications/${id}`)).data,
  });

export function useStudentApplicationActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: dashboardKey });
  };
  return {
    create: useMutation({
      mutationFn: async (body: StudentApplicationDraft) =>
        (await api.post<StudentApplication>('/student-applications', body)).data,
      onSuccess: invalidate,
    }),
    save: useMutation({
      mutationFn: async ({ id, body }: { id: string; body: StudentApplicationDraft }) =>
        (await api.patch<StudentApplication>(`/student-applications/${id}`, body)).data,
      onSuccess: invalidate,
    }),
    submit: useMutation({
      mutationFn: async ({ id, responseNote }: { id: string; responseNote?: string }) =>
        (await api.post<StudentApplication>(`/student-applications/${id}/submit`, { response_note: responseNote || null })).data,
      onSuccess: invalidate,
    }),
    withdraw: useMutation({
      mutationFn: async (id: string) => (await api.post<StudentApplication>(`/student-applications/${id}/withdraw`)).data,
      onSuccess: invalidate,
    }),
  };
}
