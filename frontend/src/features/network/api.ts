import { useQuery } from '@tanstack/react-query';
import type { NetworkCluster, NetworkGraph } from '@/api/types';
import { api } from '@/lib/api';

export function useClusters() {
  return useQuery({
    queryKey: ['network', 'clusters'],
    queryFn: async () => (await api.get<NetworkCluster[]>('/network/clusters')).data,
  });
}

export function useNetworkGraph(params: { cluster?: string; focus?: string }) {
  const enabled = Boolean(params.cluster || params.focus);
  return useQuery({
    queryKey: ['network', 'graph', params],
    queryFn: async () => (await api.get<NetworkGraph>('/network/graph', { params })).data,
    enabled,
  });
}
