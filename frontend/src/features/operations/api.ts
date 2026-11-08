import { useQuery } from '@tanstack/react-query';
import type { OperationsOverview } from '@/api/types';
import { api } from '@/lib/api';

export function useOperationsOverview() {
  return useQuery({
    queryKey: ['operations', 'overview'],
    queryFn: async () => (await api.get<OperationsOverview>('/operations/overview')).data,
    refetchInterval: 60_000,
  });
}
