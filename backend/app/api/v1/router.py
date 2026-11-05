"""Aggregates every v1 module router. Each module owns its own prefix and tag."""

from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    alerts,
    applications,
    audit,
    auth,
    cards,
    cases,
    dashboard,
    detection,
    disbursements,
    network,
    organizations,
    provider_events,
    security,
    simulations,
    student_applications,
    student_onboarding,
    student_portal,
    students,
    system,
    transactions,
    users,
    verification_requests,
    verifications,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(applications.router)
api_router.include_router(students.router)
api_router.include_router(student_portal.router)
api_router.include_router(student_onboarding.router)
api_router.include_router(student_applications.router)
api_router.include_router(disbursements.router)
api_router.include_router(verifications.router)
api_router.include_router(network.router)
api_router.include_router(alerts.router)
api_router.include_router(cases.router)
api_router.include_router(detection.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(accounts.router)
api_router.include_router(accounts.case_router)
api_router.include_router(cards.router)
api_router.include_router(transactions.router)
api_router.include_router(security.router)
api_router.include_router(verification_requests.router)
api_router.include_router(provider_events.router)
api_router.include_router(simulations.router)
api_router.include_router(system.router)
