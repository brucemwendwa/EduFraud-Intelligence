from __future__ import annotations

from typing import Any

from app.schemas.common import Schema


class NetworkCluster(Schema):
    id: str
    size: int
    applications_in_scope: int
    applications_other_institutions: int
    institutions: int
    link_types: dict[str, int]
    risk_level: str
    max_score: float
    references: list[str]
    scenarios: list[str]


class NetworkNode(Schema):
    id: str
    type: str
    label: str
    sublabel: str
    risk_level: str | None
    details: dict[str, Any]
    link: str | None
    x: float
    y: float


class NetworkEdge(Schema):
    id: str
    source: str
    target: str
    relation: str
    suspicious: bool


class NetworkGraph(Schema):
    title: str
    cluster_id: str | None
    focus: str | None
    stats: dict[str, int]
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
