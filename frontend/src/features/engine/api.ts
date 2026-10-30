import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DetectionRun, DetectionStatus, ScenarioCheck } from '@/api/types';
import { api } from '@/lib/api';

export function useDetectionStatus() {
  return useQuery({
    queryKey: ['detection', 'status'],
    queryFn: async () => (await api.get<DetectionStatus>('/detection/status')).data,
  });
}

export function useScenarioValidation() {
  return useQuery({
    queryKey: ['detection', 'scenarios'],
    queryFn: async () => (await api.get<ScenarioCheck[]>('/detection/scenario-validation')).data,
  });
}

/** Polls a run until it finishes. */
export function useDetectionRun(id: string | null) {
  return useQuery({
    queryKey: ['detection', 'run', id],
    queryFn: async () => (await api.get<DetectionRun>(`/detection/runs/${id}`)).data,
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && ['completed', 'failed'].includes(q.state.data.status) ? false : 1200),
  });
}

export function useStartDetectionRun() {
  return useMutation({
    mutationFn: async () => (await api.post<DetectionRun>('/detection/runs')).data,
  });
}

/** Everything derived from risk scores must refresh after a run completes. */
export function useInvalidateAfterRun() {
  const qc = useQueryClient();
  return () => {
    for (const key of ['detection', 'applications', 'alerts', 'disbursements', 'dashboard']) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
  };
}
