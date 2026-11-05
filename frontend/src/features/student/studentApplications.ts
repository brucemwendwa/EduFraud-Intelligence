import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type StudentApplication = {
  id: string; reference: string; award_year: string | null; status: string; submitted_at: string | null;
  dependency_status: string | null; enrollment_intensity: string | null; program: string | null;
  requested_amount: string | null; student_aid_index: number | null; risk_level: string | null;
  is_editable: boolean; outstanding_requirements: string[];
  history: { from_status: string | null; to_status: string; actor_role: string; created_at: string }[];
};

export type Draft = Pick<StudentApplication, 'award_year' | 'dependency_status' | 'enrollment_intensity' | 'program' | 'requested_amount' | 'student_aid_index'>;
const key = ['student-applications'] as const;

export const useStudentApplications = () => useQuery({ queryKey: key, queryFn: async () => (await api.get<StudentApplication[]>('/student-applications')).data });
export const useStudentApplication = (id: string | undefined) => useQuery({ queryKey: [...key, id], enabled: Boolean(id), queryFn: async () => (await api.get<StudentApplication>(`/student-applications/${id}`)).data });

export function useStudentApplicationActions(id?: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: key });
  return {
    create: useMutation({ mutationFn: async (body: Partial<Draft>) => (await api.post<StudentApplication>('/student-applications', body)).data, onSuccess: invalidate }),
    save: useMutation({ mutationFn: async (body: Partial<Draft>) => (await api.patch<StudentApplication>(`/student-applications/${id}`, body)).data, onSuccess: invalidate }),
    submit: useMutation({ mutationFn: async () => (await api.post<StudentApplication>(`/student-applications/${id}/submit`)).data, onSuccess: invalidate }),
    withdraw: useMutation({ mutationFn: async () => (await api.post<StudentApplication>(`/student-applications/${id}/withdraw`)).data, onSuccess: invalidate }),
  };
}
