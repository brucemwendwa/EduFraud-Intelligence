"""Aggregates every v1 module router. Each module owns its own prefix and tag."""

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    applications,
    audit,
    auth,
    detection,
    disbursements,
    organizations,
    students,
    users,
    verifications,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(applications.router)
api_router.include_router(students.router)
api_router.include_router(disbursements.router)
api_router.include_router(verifications.router)
api_router.include_router(alerts.router)
api_router.include_router(detection.router)
api_router.include_router(audit.router)
