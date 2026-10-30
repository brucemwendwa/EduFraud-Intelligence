import { Background, Controls, MiniMap, ReactFlow, type Edge } from '@xyflow/react';
import { ArrowUpRight, EyeOff, Network, ShieldAlert } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import type { NetworkCluster, NetworkGraph, NetworkNode } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { cn } from '@/lib/cn';
import { label } from '@/lib/format';
import { scenarioLabels } from '@/lib/status';
import { useSearchState } from '@/lib/useSearchState';
import { useClusters, useNetworkGraph } from './api';
import { EntityNode, entityTypes, type EntityFlowNode } from './EntityNode';

const nodeTypes = { entity: EntityNode };
const DEFAULTS = { cluster: '', focus: '' };

export default function NetworkPage() {
  const [params, setParams] = useSearchState(DEFAULTS);
  const clusters = useClusters();
  const activeCluster = params.cluster || (!params.focus ? clusters.data?.[0]?.id ?? '' : '');
  const graph = useNetworkGraph({ cluster: activeCluster || undefined, focus: params.focus || undefined });

  return (
    <>
      <PageHeader
        title="Fraud network intelligence"
        description="Applications linked by shared identity tokens, devices, networks or payment destinations. Only risk-bearing links form clusters. Households, residence halls and campus kiosks do not."
      />
      <div className="grid gap-6 xl:grid-cols-[18rem_1fr]">
        <ClusterList
          clusters={clusters.data}
          loading={clusters.isLoading}
          error={clusters.error}
          active={graph.data?.cluster_id ?? activeCluster}
          onSelect={(id) => setParams({ cluster: id, focus: '' })}
        />
        <div className="min-w-0">
          {graph.isLoading || (clusters.isLoading && !params.focus) ? (
            <Card className="h-[640px] p-5"><Skeleton className="h-full w-full" /></Card>
          ) : graph.error ? (
            <Card><ErrorState error={graph.error} onRetry={() => graph.refetch()} /></Card>
          ) : !graph.data ? (
            <Card><EmptyState icon={<Network className="size-5" />} title="No linked clusters in your scope" description="No risk-bearing links connect applications at your institution right now." /></Card>
          ) : (
            <GraphView key={`${graph.data.cluster_id}-${graph.data.focus}`} graph={graph.data} />
          )}
        </div>
      </div>
    </>
  );
}

function ClusterList({
  clusters,
  loading,
  error,
  active,
  onSelect,
}: {
  clusters?: NetworkCluster[];
  loading: boolean;
  error: unknown;
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <Card className="self-start">
      <CardHeader title="Linked clusters" description="Riskiest first" icon={<Network className="size-4" />} />
      {loading ? (
        <CardSkeleton />
      ) : error ? (
        <ErrorState error={error} />
      ) : !clusters?.length ? (
        <p className="px-5 pb-5 text-sm text-slate-500">No clusters found.</p>
      ) : (
        <ul className="space-y-2 px-3 pb-3">
          {clusters.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onSelect(c.id)}
                aria-pressed={active === c.id}
                className={cn(
                  'w-full rounded-lg border p-3 text-left transition-colors',
                  active === c.id ? 'border-navy-900 bg-navy-50/60' : 'border-slate-200 hover:border-slate-300',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-slate-900">{c.id}</span>
                  <RiskBadge level={c.risk_level as RiskLevel} />
                </div>
                <p className="mt-1.5 text-sm text-slate-700">
                  {c.size} applications · {c.institutions} institution{c.institutions > 1 ? 's' : ''}
                </p>
                {c.applications_other_institutions > 0 && (
                  <p className="text-xs text-amber-700">{c.applications_other_institutions} outside your scope (anonymised)</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(c.link_types).map(([k, n]) => (
                    <span key={k} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{n} {label(k)}</span>
                  ))}
                </div>
                {c.scenarios.map((s) => (
                  <Badge key={s} tone="violet" className="mt-2">{scenarioLabels[s] ?? s}</Badge>
                ))}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function GraphView({ graph }: { graph: NetworkGraph }) {
  const [selected, setSelected] = useState<string | null>(graph.focus);
  const neighbours = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const e of graph.edges) {
      if (!map.has(e.source)) map.set(e.source, new Set());
      if (!map.has(e.target)) map.set(e.target, new Set());
      map.get(e.source)!.add(e.target);
      map.get(e.target)!.add(e.source);
    }
    return map;
  }, [graph.edges]);

  const focusSet = selected ? new Set([selected, ...(neighbours.get(selected) ?? [])]) : null;
  const nodes: EntityFlowNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: 'entity',
    position: { x: n.x, y: n.y },
    data: { ...n, dimmed: focusSet ? !focusSet.has(n.id) : false },
    selected: n.id === selected,
  }));
  const edges: Edge[] = graph.edges.map((e) => {
    const lit = !focusSet || (focusSet.has(e.source) && focusSet.has(e.target));
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'straight',
      label: selected && lit ? e.relation : undefined,
      labelStyle: { fontSize: 10, fill: '#475569' },
      labelBgStyle: { fill: '#ffffff' },
      style: {
        stroke: e.suspicious ? '#B22234' : '#94A3B8',
        strokeWidth: e.suspicious ? 1.75 : 1.25,
        strokeDasharray: e.relation === 'also linked' ? '4 3' : undefined,
        opacity: lit ? 0.9 : 0.12,
      },
    };
  });
  const selectedNode = graph.nodes.find((n) => n.id === selected) ?? null;
  const hasExternal = graph.nodes.some((n) => n.type === 'external');

  return (
    <div className="grid gap-6 2xl:grid-cols-[1fr_20rem]">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{graph.title}</h2>
            <p className="text-xs text-slate-500">
              {graph.stats.applications} application(s) in scope · {graph.stats.institutions} institution(s) · {graph.stats.shared_attributes} shared attribute(s)
            </p>
          </div>
          {hasExternal && (
            <Badge tone="warning" icon={<EyeOff className="size-3" />}>{graph.stats.applications_other_institutions} linked record(s) at other institutions, anonymised</Badge>
          )}
        </div>
        <div className="h-[600px] bg-slate-50/50" role="figure" aria-label={`Relationship graph: ${graph.title}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={(_, n) => setSelected((cur) => (cur === n.id ? null : n.id))}
            onPaneClick={() => setSelected(null)}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.2}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={22} color="#E2E8F0" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable style={{ width: 140, height: 96 }} nodeColor={(n) => ((n.data as NetworkNode).type === 'application' ? '#102A4C' : '#CBD5E1')} />
          </ReactFlow>
        </div>
        <Legend />
      </Card>
      <Inspector node={selectedNode} graph={graph} neighbours={neighbours} onSelect={setSelected} />
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-100 px-5 py-3">
      {Object.entries(entityTypes).map(([key, meta]) => (
        <span key={key} className="flex items-center gap-1.5 text-xs text-slate-600">
          <span className={cn('flex size-5 items-center justify-center rounded-full border', meta.tone)}>
            <meta.Icon className="size-3" aria-hidden />
          </span>
          {meta.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5 text-xs text-slate-600">
        <span className="h-0.5 w-5 bg-flag-red" aria-hidden />Risk-bearing link
      </span>
    </div>
  );
}

function Inspector({
  node,
  graph,
  neighbours,
  onSelect,
}: {
  node: NetworkNode | null;
  graph: NetworkGraph;
  neighbours: Map<string, Set<string>>;
  onSelect: (id: string) => void;
}) {
  if (!node) {
    return (
      <Card className="self-start">
        <EmptyState icon={<ShieldAlert className="size-5" />} title="Select a node" description="Click any entity to see its details and every record connected to it." />
      </Card>
    );
  }
  const meta = entityTypes[node.type] ?? entityTypes.application!;
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const connected = [...(neighbours.get(node.id) ?? [])].map((id) => byId.get(id)).filter(Boolean) as NetworkNode[];
  return (
    <Card className="self-start">
      <div className="border-b border-slate-100 p-5">
        <div className="flex items-center gap-3">
          <span className={cn('flex size-10 items-center justify-center rounded-full border-2', meta.tone)}><meta.Icon className="size-4" /></span>
          <div className="min-w-0">
            <p className="text-xs text-slate-500">{meta.label}</p>
            <p className="truncate font-semibold text-slate-900">{node.label}</p>
            {node.sublabel && <p className="truncate text-xs text-slate-500">{node.sublabel}</p>}
          </div>
        </div>
        {node.risk_level && <div className="mt-3"><RiskBadge level={node.risk_level as RiskLevel} /></div>}
        {node.link && (
          <Link to={node.link} className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">
            Open record <ArrowUpRight className="size-3.5" />
          </Link>
        )}
      </div>
      {Object.keys(node.details).length > 0 && (
        <dl className="grid grid-cols-2 gap-3 border-b border-slate-100 p-5 text-sm">
          {Object.entries(node.details).map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-slate-500">{k}</dt>
              <dd className="mt-0.5 text-slate-800">{String(v).replace(/_/g, ' ')}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="p-5">
        <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Connected ({connected.length})</h3>
        <ul className="space-y-1">
          {connected.map((n) => {
            const m = entityTypes[n.type] ?? entityTypes.application!;
            return (
              <li key={n.id}>
                <button type="button" onClick={() => onSelect(n.id)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50">
                  <m.Icon className="size-3.5 shrink-0 text-slate-400" aria-hidden />
                  <span className="truncate text-slate-800">{n.label}</span>
                  <span className="ml-auto shrink-0 text-[11px] text-slate-400">{m.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </Card>
  );
}
