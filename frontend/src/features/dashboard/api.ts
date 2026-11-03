import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AccountScenarioCheck, DashboardOverview, ScenarioInfo, SimulationResult } from '@/api/types';
import { api } from '@/lib/api';

export function useDashboardOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: async () => (await api.get<DashboardOverview>('/dashboard/overview')).data,
    refetchInterval: 60_000,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: ['simulations', 'list'],
    queryFn: async () => (await api.get<ScenarioInfo[]>('/simulations')).data,
    staleTime: Infinity,
  });
}

export function useScenarioChecks() {
  return useQuery({
    queryKey: ['simulations', 'validation'],
    queryFn: async () => (await api.get<AccountScenarioCheck[]>('/simulations/validation')).data,
  });
}

/** Everything that a replayed scenario can change. */
const AFFECTED = ['dashboard', 'accounts', 'cards', 'transactions', 'security', 'alerts', 'verification-requests', 'simulations', 'network', 'audit'];

export function useRunScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (key: string) => (await api.post<SimulationResult>(`/simulations/${key}`)).data,
    onSuccess: () => {
      for (const key of AFFECTED) void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}
