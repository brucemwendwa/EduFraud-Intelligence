"""Fraud-network analysis with NetworkX.

Only *risk-bearing* links join applications into clusters:
  - an SSN token shared by students with conflicting identity details,
  - a device or network address used for a burst of applications (>= 3 within 72 h),
  - a phone number shared by three or more students,
  - a payment destination receiving funds for more than one student.
Benign sharing (households, residence halls, a campus kiosk used over months) does not
link records, which keeps legitimate students out of clusters.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from app.detection.context import DetectionContext
from app.detection.rules.application import BURST_MIN_APPS, burst_peers
from app.detection.signals import Signal
from app.detection.versions import GRAPH_VERSION
from app.models import FinancialAidApplication
from app.models.enums import Severity, SignalCategory

MIN_CLUSTER = 4


@dataclass
class Cluster:
    id: str
    application_ids: set[uuid.UUID]
    link_types: dict[str, int] = field(default_factory=dict)
    organizations: set[uuid.UUID] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.application_ids)


def link_graph(ctx: DetectionContext) -> nx.Graph:
    """Bipartite graph: application nodes connected to the shared attribute nodes that link them."""
    g = nx.Graph()
    apps_by_student: dict[uuid.UUID, list[FinancialAidApplication]] = ctx.student_apps

    def link(attr: str, kind: str, apps: list[FinancialAidApplication]) -> None:
        if len({a.student_id for a in apps}) < 2:
            return
        g.add_node(attr, kind=kind)
        for a in apps:
            g.add_node(a.id, kind="application", org=a.organization_id)
            g.add_edge(a.id, attr)

    for (token_type, value), students in ctx.token_students.items():
        if len(students) < 2:
            continue
        if token_type == "ssn":
            identities = {(ctx.student_tokens[s].get("name"), ctx.student_tokens[s].get("dob")) for s in students}
            if len(identities) > 1:
                link(f"ssn:{value}", "ssn", [a for s in students for a in apps_by_student.get(s, [])])
        elif token_type == "phone" and len(students) >= 3:
            link(f"phone:{value}", "phone", [a for s in students for a in apps_by_student.get(s, [])])

    for kind, index in (("device", ctx.device_apps), ("ip", ctx.ip_apps)):
        for value, apps in index.items():
            if len(apps) < BURST_MIN_APPS:
                continue
            bursty = [a for a in apps if len(burst_peers(a, apps)) + 1 >= BURST_MIN_APPS]
            link(f"{kind}:{value}", kind, bursty)

    for dest_id, students in ctx.destination_students.items():
        if len(students) < 2:
            continue
        app_ids = {
            d.application_id
            for s in students
            for d in ctx.student_disbursements.get(s, [])
            if d.destination_id == dest_id
        }
        apps = [a for s in students for a in apps_by_student.get(s, []) if a.id in app_ids]
        link(f"destination:{dest_id}", "destination", apps)
    return g


def find_clusters(g: nx.Graph) -> dict[uuid.UUID, Cluster]:
    """Maps each application to its cluster (connected component with >= MIN_CLUSTER applications)."""
    by_app: dict[uuid.UUID, Cluster] = {}
    components = sorted(nx.connected_components(g), key=len, reverse=True)
    for idx, component in enumerate(components, start=1):
        app_ids = {n for n in component if g.nodes[n].get("kind") == "application"}
        if len(app_ids) < MIN_CLUSTER:
            continue
        links: dict[str, int] = defaultdict(int)
        for n in component:
            kind = g.nodes[n].get("kind")
            if kind != "application":
                links[kind] += 1
        cluster = Cluster(
            id=f"CL-{idx:03d}",
            application_ids=app_ids,
            link_types=dict(links),
            organizations={g.nodes[a]["org"] for a in app_ids},
        )
        for a in app_ids:
            by_app[a] = cluster
    return by_app


def evaluate(clusters: dict[uuid.UUID, Cluster], app: FinancialAidApplication) -> list[Signal]:
    cluster = clusters.get(app.id)
    if cluster is None:
        return []
    links = ", ".join(f"{n} shared {k}{'s' if n > 1 else ''}" for k, n in sorted(cluster.link_types.items()))
    return [
        Signal(
            code="NETWORK_CLUSTER",
            category=SignalCategory.NETWORK,
            severity=Severity.HIGH if cluster.size >= 6 else Severity.MEDIUM,
            weight=0.4 if cluster.size >= 6 else 0.3,
            title=f"Part of a linked cluster of {cluster.size} applications",
            description=(
                f"Graph analysis links this application to {cluster.size - 1} others through {links}"
                + (f", spanning {len(cluster.organizations)} institutions" if len(cluster.organizations) > 1 else "")
                + "."
            ),
            method="graph",
            version=GRAPH_VERSION,
            evidence={"cluster_id": cluster.id, "size": cluster.size, "links": cluster.link_types},
        )
    ]
