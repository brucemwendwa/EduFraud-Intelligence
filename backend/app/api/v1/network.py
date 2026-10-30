from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import DB, Principal, require
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.models.enums import AuditCategory
from app.schemas.network import NetworkCluster, NetworkGraph
from app.services import audit
from app.services.network import NetworkService

router = APIRouter(prefix="/network", tags=["network"])

Reader = Annotated[Principal, Depends(require(P.NETWORK_READ))]


@router.get("/clusters", response_model=list[NetworkCluster], summary="Linked application clusters, riskiest first")
def clusters(db: DB, principal: Reader) -> list[dict]:
    return NetworkService(db, principal).list_clusters()


@router.get("/graph", response_model=NetworkGraph, summary="Relationship graph for a cluster or around one application")
def graph(
    request: Request,
    db: DB,
    principal: Reader,
    cluster: Annotated[str | None, Query(max_length=16, pattern=r"^CL-[0-9A-F]{6}$")] = None,
    focus: uuid.UUID | None = None,
) -> dict:
    if not cluster and not focus:
        raise ValidationFailedError("Provide a cluster id or a focus application.")
    service = NetworkService(db, principal)
    result = service.cluster_graph(cluster) if cluster else service.focus_graph(focus)  # type: ignore[arg-type]
    if result is None:
        raise NotFoundError("Network not found in your scope.")
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="network.view",
        actor=principal.user,
        organization_id=principal.org_id,
        target_type="cluster" if cluster else "application",
        target_id=cluster or str(focus),
        target_ref=result["cluster_id"],
        details={"nodes": len(result["nodes"]), "applications": result["stats"]["applications"]},
        request=request,
    )
    db.commit()
    return result
