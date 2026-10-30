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
from app.models import FinancialAidApplication
from app.seed.base import bootstrap
from app.seed.generator import SyntheticGenerator

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
        print(f"Reference data: {len(orgs)} institutions, {len(users)} demo accounts.")
        if db.query(FinancialAidApplication).first() is not None:
            print("Synthetic records already present; use --reset to regenerate.")
            return
        summary = SyntheticGenerator(db, orgs).run()
        db.commit()
    print(
        f"Synthetic data: {summary.students} students, {summary.applications} applications, "
        f"{summary.disbursements} disbursements, {summary.verifications} verifications."
    )
    for scenario, refs in summary.scenario_refs.items():
        print(f"  {scenario:<24} {', '.join(refs[:4])}{' …' if len(refs) > 4 else ''}")


if __name__ == "__main__":
    main()
