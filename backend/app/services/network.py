"""Fraud-network views for investigators: clusters and explorable relationship graphs.

Built on the same risk-bearing link graph the detection engine scores (app.detection.graph),
enriched with the records an investigator needs to see: students, institutions, enrollments,
payment destinations, devices, networks, identity tokens and alerts.

Tenant privacy: applications outside the viewer's scope are never shown individually. They
collapse into one anonymous "other institution" node per linked attribute set, so a Northbridge
investigator learns that a payment destination is also used elsewhere, but not by whom.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal
from app.core.tokenization import display_token
from app.detection import graph as risk_graph
from app.detection.context import DetectionContext, build_context
from app.models import Alert, Organization, PaymentDestinationToken
from app.services.records import mask_name

LEVEL_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    sublabel: str = ""
    risk_level: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    link: str | None = None


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    suspicious: bool = False


def _in_scope(org_id: uuid.UUID, principal: Principal) -> bool:
    return principal.org_id is None or org_id == principal.org_id


class NetworkService:
    def __init__(self, db: Session, principal: Principal) -> None:
        self.db = db
        self.principal = principal
        self.ctx: DetectionContext = build_context(db)
        self.links = risk_graph.link_graph(self.ctx)
        self.clusters = risk_graph.find_clusters(self.links)
        self.apps = {a.id: a for a in self.ctx.applications}
        self.orgs = {o.id: o for o in db.scalars(select(Organization))}

    # ------------------------------------------------------------------ clusters
    def list_clusters(self) -> list[dict[str, Any]]:
        unique = {c.id: c for c in self.clusters.values()}
        out = []
        for c in unique.values():
            members = [self.apps[a] for a in c.application_ids]
            visible = [a for a in members if _in_scope(a.organization_id, self.principal)]
            if not visible:
                continue
            top = max((a.risk_level or "low" for a in visible), key=lambda lvl: LEVEL_RANK[lvl])
            scenarios = sorted({a.scenario_key for a in visible if a.scenario_key})
            out.append(
                {
                    "id": c.id,
                    "size": c.size,
                    "applications_in_scope": len(visible),
                    "applications_other_institutions": c.size - len(visible),
                    "institutions": len(c.organizations),
                    "link_types": c.link_types,
                    "risk_level": top,
                    "max_score": max((a.risk_score or 0) for a in visible),
                    "references": sorted(a.reference for a in visible)[:12],
                    "scenarios": scenarios,
                }
            )
        return sorted(out, key=lambda c: (-LEVEL_RANK[c["risk_level"]], -c["max_score"], -c["size"]))

    # ------------------------------------------------------------------ graphs
    def cluster_graph(self, cluster_id: str) -> dict[str, Any] | None:
        cluster = next((c for c in self.clusters.values() if c.id == cluster_id), None)
        if cluster is None:
            return None
        if not any(_in_scope(self.apps[a].organization_id, self.principal) for a in cluster.application_ids):
            return None
        return self._build(set(cluster.application_ids), title=f"Cluster {cluster.id}", cluster_id=cluster.id)

    def focus_graph(self, application_id: uuid.UUID) -> dict[str, Any] | None:
        app = self.apps.get(application_id)
        if app is None or not _in_scope(app.organization_id, self.principal):
            return None
        cluster = self.clusters.get(app.id)
        if cluster is not None:
            return self._build(
                set(cluster.application_ids), title=f"Cluster {cluster.id}", cluster_id=cluster.id, focus=app.id
            )
        # Not in a risk cluster: show its one-hop neighbourhood over any shared attribute.
        members = {app.id}
        neighbours = self.links.neighbors(app.id) if app.id in self.links else []
        for attr in neighbours:
            members |= {n for n in self.links.neighbors(attr) if isinstance(n, uuid.UUID)}
        return self._build(members, title=f"Neighbourhood of {app.reference}", cluster_id=None, focus=app.id)

    def _build(
        self, app_ids: set[uuid.UUID], *, title: str, cluster_id: str | None, focus: uuid.UUID | None = None
    ) -> dict[str, Any]:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        visible = {a for a in app_ids if _in_scope(self.apps[a].organization_id, self.principal)}
        hidden = app_ids - visible

        def add(node: GraphNode) -> str:
            nodes.setdefault(node.id, node)
            return node.id

        def edge(a: str, b: str, relation: str, suspicious: bool = False) -> None:
            edges.append(GraphEdge(a, b, relation, suspicious))

        alerts = {a.application_id: a for a in self.db.scalars(select(Alert).where(Alert.application_id.in_(visible)))}
        for app_id in visible:
            app = self.apps[app_id]
            stu = app.student
            org = self.orgs[app.organization_id]
            a = add(
                GraphNode(
                    id=f"app:{app.id}",
                    type="application",
                    label=app.reference,
                    sublabel=f"Score {app.risk_score or 0:.0f}",
                    risk_level=app.risk_level,
                    link=f"/app/applications/{app.id}",
                    details={
                        "Status": app.status,
                        "Risk score": round(app.risk_score or 0),
                        "Submitted": app.submitted_at.date().isoformat(),
                        "Program": app.program,
                        "Scenario": app.scenario_key or "—",
                    },
                )
            )
            s = add(
                GraphNode(
                    id=f"stu:{stu.id}",
                    type="student",
                    label=stu.student_ref,
                    sublabel=mask_name(stu.first_name, stu.last_name),
                    details={
                        "Birth year": stu.birth_year,
                        "Biometric consent": "yes" if stu.biometric_consent else "no",
                    },
                )
            )
            edge(a, s, "applicant")
            o = add(
                GraphNode(
                    id=f"org:{org.id}",
                    type="institution",
                    label=org.name,
                    sublabel=f"{org.city}, {org.state}",
                    details={"Type": org.institution_type, "Identifier": org.synthetic_ope_id},
                )
            )
            edge(a, o, "submitted to")
            for e in self.ctx.student_enrollments.get(stu.id, []):
                if e.application_id == app.id:
                    n = add(
                        GraphNode(
                            id=f"enr:{e.id}",
                            type="enrollment",
                            label=e.term,
                            sublabel=f"{e.modality.replace('_', ' ')} · {e.status.replace('_', ' ')}",
                            details={
                                "Credits": e.credit_hours,
                                "Last attendance": e.last_attendance_at.date().isoformat()
                                if e.last_attendance_at
                                else "none recorded",
                            },
                        )
                    )
                    edge(s, n, "enrolled", suspicious=e.last_attendance_at is None)
            if app.id in alerts:
                al = alerts[app.id]
                n = add(
                    GraphNode(
                        id=f"alert:{al.id}",
                        type="alert",
                        label=al.reference,
                        sublabel=al.title,
                        risk_level=al.severity,
                        link=f"/app/alerts?selected={al.id}",
                        details={"Status": al.status, "Severity": al.severity},
                    )
                )
                edge(a, n, "raised")

        # Risk-bearing shared attributes between members (the edges that formed the cluster).
        attr_members: dict[str, set[uuid.UUID]] = defaultdict(set)
        for app_id in app_ids:
            if app_id in self.links:
                for attr in self.links.neighbors(app_id):
                    attr_members[attr].add(app_id)
        for attr, members in attr_members.items():
            if len(members) < 2 and focus is None:
                continue
            kind, _, value = attr.partition(":")
            node = self._attribute_node(kind, value, len(members))
            relation = node.details.pop("relation", "shares")
            add(node)
            for m in members & visible:
                edge(f"app:{m}", node.id, relation, suspicious=True)
            outside = members & hidden
            if outside:
                ext_orgs = {self.apps[m].organization_id for m in outside}
                ext = add(
                    GraphNode(
                        id=f"ext:{attr}",
                        type="external",
                        label=f"{len(outside)} record(s) elsewhere",
                        sublabel=f"{len(ext_orgs)} other institution(s)",
                        details={"Note": "Details belong to another institution and are not shared."},
                    )
                )
                edge(ext, node.id, "also linked", suspicious=True)

        positions = self._layout(nodes, edges)
        return {
            "title": title,
            "cluster_id": cluster_id,
            "focus": f"app:{focus}" if focus else None,
            "stats": {
                "applications": len(visible),
                "applications_other_institutions": len(hidden),
                "institutions": len({self.apps[a].organization_id for a in app_ids}),
                "shared_attributes": sum(
                    1 for n in nodes.values() if n.type in {"destination", "device", "network", "ssn", "phone"}
                ),
            },
            "nodes": [{**n.__dict__, "x": positions[n.id][0], "y": positions[n.id][1]} for n in nodes.values()],
            "edges": [{"id": f"e{i}", **e.__dict__} for i, e in enumerate(edges)],
        }

    def _attribute_node(self, kind: str, value: str, members: int) -> GraphNode:
        if kind == "destination":
            dest = self.db.get(PaymentDestinationToken, uuid.UUID(value))
            students = self.ctx.destination_students.get(uuid.UUID(value), set())
            return GraphNode(
                id=f"destination:{value}",
                type="destination",
                label=display_token(dest.token_value, "DST") if dest else "Destination",
                sublabel=(
                    f"{dest.destination_type.replace('_', ' ')} ••{dest.display_suffix}"
                    if dest
                    else "payment destination"
                ),
                details={"Students paid here": len(students), "relation": "paid to"},
            )
        labels = {
            "device": ("DEV", "Device fingerprint", "submitted from"),
            "ip": ("NET", "Network address", "submitted from"),
            "ssn": ("TKN", "SSN token", "identity"),
            "phone": ("PHN", "Phone token", "contact"),
        }
        prefix, name, relation = labels.get(kind, ("ATTR", kind, "shares"))
        node_type = {"ip": "network"}.get(kind, kind)
        return GraphNode(
            id=f"{kind}:{value}",
            type=node_type,
            label=display_token(value, prefix),
            sublabel=name,
            details={"Linked applications": members, "relation": relation},
        )

    @staticmethod
    def _layout(nodes: dict[str, GraphNode], edges: list[GraphEdge]) -> dict[str, tuple[float, float]]:
        """Deterministic radial layout that keeps dense rings readable.

        Shared attributes (the evidence) sit on an inner ring, applications on a middle ring grouped by
        institution, each application's own records fan straight outward, and institutions sit on the
        outer ring aligned with their applications. Force layouts collapse densely linked rings into an
        unreadable knot, which is exactly the shape investigators most need to see.
        """
        adjacency: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            adjacency[e.source].append(e.target)
            adjacency[e.target].append(e.source)
        apps = [n for n, node in nodes.items() if node.type == "application"]
        if not apps:
            return {n: (0.0, 0.0) for n in nodes}

        def institution_of(app: str) -> str:
            return next((n for n in adjacency[app] if nodes[n].type == "institution"), "")

        apps.sort(key=lambda a: (institution_of(a), nodes[a].label))
        r_app = max(240.0, len(apps) * 70 / math.tau * 2.2)
        pos: dict[str, tuple[float, float]] = {}
        angle_of: dict[str, float] = {}
        for i, app in enumerate(apps):
            angle = math.tau * i / len(apps) - math.pi / 2
            angle_of[app] = angle
            pos[app] = (r_app * math.cos(angle), r_app * math.sin(angle))

        def mean_angle(members: list[str]) -> float:
            xs = sum(math.cos(angle_of[m]) for m in members)
            ys = sum(math.sin(angle_of[m]) for m in members)
            return math.atan2(ys, xs) if (xs or ys) else 0.0

        evidence_types = {"destination", "device", "network", "ssn", "phone"}
        evidence = [n for n, node in nodes.items() if node.type in evidence_types]
        evidence.sort(key=lambda n: mean_angle([m for m in adjacency[n] if m in angle_of] or apps))
        r_inner = 0.0 if len(evidence) == 1 else max(150.0, r_app * 0.55, len(evidence) * 150 / math.tau)
        # Keep a clear band between the evidence ring and the application ring for placeholders and edges.
        gap = 230.0
        if evidence and r_app < r_inner + gap:
            factor = (r_inner + gap) / r_app
            r_app *= factor
            pos = {a: (x * factor, y * factor) for a, (x, y) in pos.items()}
        evidence_set = set(evidence)
        start = mean_angle([m for m in adjacency[evidence[0]] if m in angle_of] or apps) if evidence else 0.0
        for i, n in enumerate(evidence):
            angle = start + math.tau * i / max(len(evidence), 1)
            pos[n] = (r_inner * math.cos(angle), r_inner * math.sin(angle))

        def radial(angle: float, radius: float, turn: float = 0.0) -> tuple[float, float]:
            return radius * math.cos(angle + turn), radius * math.sin(angle + turn)

        spread = min(0.22, math.pi / max(len(apps), 1) * 0.45)
        for app in apps:
            angle = angle_of[app]
            for n in adjacency[app]:
                kind = nodes[n].type
                if kind == "student":
                    pos[n] = radial(angle, r_app + 95, -spread)
                    for e in adjacency[n]:
                        if nodes[e].type == "enrollment":
                            pos[e] = radial(angle, r_app + 180, -spread)
                elif kind == "alert":
                    pos[n] = radial(angle, r_app + 95, spread)

        for n, node in nodes.items():
            if node.type == "institution":
                members = [m for m in adjacency[n] if m in angle_of]
                pos[n] = radial(mean_angle(members), r_app + 270)
        # Anonymised placeholders: each sits on the ray of the evidence node it hangs off, between the rings,
        # so every label stays readable and the shared attribute visibly links to "records elsewhere".
        for n, node in nodes.items():
            if node.type == "external":
                anchor = next((m for m in adjacency[n] if m in evidence_set), None)
                ax, ay = pos[anchor] if anchor else (0.0, 0.0)
                angle = math.atan2(ay, ax) if (ax or ay) else -math.pi / 2
                pos[n] = radial(angle, r_inner + gap / 2)
        for n in nodes:
            pos.setdefault(n, (0.0, 0.0))
        return {n: (round(x, 1), round(y, 1)) for n, (x, y) in pos.items()}
