"""Test harness.

A template SQLite database is migrated once per session (real Alembic migrations,
including the audit triggers); every test then works on its own file copy, so tests
are isolated without paying the migration cost each time.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="edushield-tests-"))
_TEMPLATE = _TMP / "template.db"
os.environ["ENV"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["CELERY_BROKER_URL"] = ""
os.environ["DATABASE_URL"] = f"sqlite:///{_TEMPLATE}"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal, build_engine  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_migrations(url: str, revision: str = "head") -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, revision)


@pytest.fixture(scope="session")
def template_db() -> Path:
    run_migrations(f"sqlite:///{_TEMPLATE}")
    _prepare_template()
    return _TEMPLATE


def _prepare_template() -> None:
    """Hook for reference data shared by every test (extended as modules are added)."""


@pytest.fixture
def engine(template_db: Path, tmp_path: Path) -> Iterator[Engine]:
    db_file = tmp_path / "test.db"
    shutil.copy(template_db, db_file)
    eng = build_engine(f"sqlite:///{db_file}")
    SessionLocal.configure(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    shutil.rmtree(_TMP, ignore_errors=True)
