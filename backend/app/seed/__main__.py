"""Seed the database with reference data and synthetic demonstration records.

    python -m app.seed            # idempotent: RBAC, institutions, demo accounts (+ synthetic data if empty)
    python -m app.seed --reset    # drop and recreate the schema first (destroys ALL data, incl. audit trail)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.seed.base import bootstrap

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables before seeding")
    args = parser.parse_args()

    if args.reset:
        if get_settings().is_production:
            raise SystemExit("Refusing to reset a production database.")
        command.downgrade(_alembic(), "base")
    command.upgrade(_alembic(), "head")

    with SessionLocal() as db:
        orgs, users = bootstrap(db)
        db.commit()
    print(f"Seeded {len(orgs)} institutions and {len(users)} demo accounts.")


if __name__ == "__main__":
    main()
