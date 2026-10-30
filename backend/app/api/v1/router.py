"""Aggregates every v1 module router. Each module owns its own prefix and tag."""

from fastapi import APIRouter

from app.api.v1 import audit, auth, organizations, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
