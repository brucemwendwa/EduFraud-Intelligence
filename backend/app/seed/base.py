"""Reference institutions and demo accounts shared by the seed command and the test suite."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Organization, Role, User
from app.services.rbac import sync_rbac

DEMO_PASSWORD = "EduShield!Demo2026"


@dataclass(frozen=True)
class InstitutionDef:
    slug: str
    name: str
    institution_type: str
    city: str
    state: str
    ope: str


INSTITUTIONS = (
    InstitutionDef("northbridge", "Northbridge State University", "public_4yr", "Dayton", "OH", "SYN-00101"),
    InstitutionDef("lakeshore", "Lakeshore Community College", "community_college", "Racine", "WI", "SYN-00102"),
    InstitutionDef("pinecrest", "Pinecrest Technical Institute", "technical", "Asheville", "NC", "SYN-00103"),
)

# (email, full name, title, role key, institution slug or None for platform)
DEMO_USERS = (
    ("admin@edushield.demo", "Jordan Ellis", "Platform Administrator", "platform_admin", None),
    ("inst.admin@northbridge.demo", "Priya Raman", "Director of Financial Aid", "institution_admin", "northbridge"),
    ("investigator@northbridge.demo", "Marcus Bell", "Senior Fraud Investigator", "fraud_investigator", "northbridge"),
    ("analyst@northbridge.demo", "Dana Whitfield", "Fraud Analyst", "fraud_investigator", "northbridge"),
    ("officer@northbridge.demo", "Elena Torres", "Financial Aid Officer", "financial_aid_officer", "northbridge"),
    ("auditor@northbridge.demo", "Samuel Okafor", "Internal Auditor", "auditor", "northbridge"),
    ("investigator@lakeshore.demo", "Hannah Kim", "Fraud Investigator", "fraud_investigator", "lakeshore"),
    ("officer@pinecrest.demo", "Luis Ortega", "Financial Aid Officer", "financial_aid_officer", "pinecrest"),
)


def ensure_institutions(db: Session) -> dict[str, Organization]:
    orgs = {o.slug: o for o in db.scalars(select(Organization))}
    for d in INSTITUTIONS:
        if d.slug not in orgs:
            org = Organization(
                slug=d.slug,
                name=d.name,
                institution_type=d.institution_type,
                city=d.city,
                state=d.state,
                synthetic_ope_id=d.ope,
            )
            db.add(org)
            orgs[d.slug] = org
    db.flush()
    return orgs


def ensure_demo_users(db: Session, orgs: dict[str, Organization], roles: dict[str, Role]) -> dict[str, User]:
    existing = {u.email: u for u in db.scalars(select(User))}
    password_hash = hash_password(DEMO_PASSWORD)  # hashed once; every demo account shares the published password
    users = {}
    for email, name, title, role_key, org_slug in DEMO_USERS:
        user = existing.get(email)
        if user is None:
            user = User(
                email=email,
                full_name=name,
                title=title,
                role_id=roles[role_key].id,
                organization_id=orgs[org_slug].id if org_slug else None,
                password_hash=password_hash,
                is_demo=True,
            )
            db.add(user)
        users[email] = user
    db.flush()
    return users


def bootstrap(db: Session) -> tuple[dict[str, Organization], dict[str, User]]:
    roles = sync_rbac(db)
    orgs = ensure_institutions(db)
    users = ensure_demo_users(db, orgs, roles)
    return orgs, users
