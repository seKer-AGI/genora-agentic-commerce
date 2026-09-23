"""Test fixtures.

* Uses a dedicated Postgres database (`TEST_DATABASE_URL`, default genora_test on the dev container).
* The schema is built with Alembic and seeded once per session with the synthetic dataset.
* Every test runs inside an outer transaction that is rolled back; service-level commits become
  SAVEPOINT releases, so tests are isolated and fast.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+psycopg://genora:genora_dev_password@localhost:5433/genora_test"
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["APP_ENV"] = "test"
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["SEED_ON_START"] = "false"
os.environ["RUN_MIGRATIONS"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["VISION_PROVIDER"] = "none"
os.environ["EMBEDDING_PROVIDER"] = "hashing"
os.environ["EXTERNAL_PRICE_PROVIDERS"] = ""

import tempfile  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

os.environ.setdefault("MEDIA_ROOT", str(Path(tempfile.gettempdir()) / "genora-test-media"))

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def _migrate_and_seed() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        head = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if head else None
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    if version is None:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(cfg, "head")
    from app.models import User

    with Session(engine) as s:
        seeded = s.scalar(select(func.count()).select_from(User))
    if not seeded:
        from app.seed.seed import seed

        seed(reset=True)
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    _migrate_and_seed()


@pytest.fixture()
def db() -> Iterator[Session]:
    from app.db.session import get_engine

    conn = get_engine().connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False, autoflush=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    from app.core.rate_limit import rate_limiter
    from app.db.session import get_db
    from app.main import app

    rate_limiter.reset()

    def _db() -> Iterator[Session]:
        try:
            yield db
        except Exception:
            db.rollback()  # mirrors get_db: failed requests leave no partial state
            raise

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def buyer_headers(client: TestClient) -> dict[str, str]:
    return _login(client, "buyer@genora.dev", "Buyer#2026!")


@pytest.fixture()
def seller_headers(client: TestClient) -> dict[str, str]:
    return _login(client, "seller@genora.dev", "Seller#2026!")


@pytest.fixture()
def other_seller_headers(client: TestClient) -> dict[str, str]:
    return _login(client, "kestrel@sellers.example.com", "Password#2026!")


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    return _login(client, "admin@genora.dev", "Admin#2026!")


@pytest.fixture()
def product_by_slug(client: TestClient):  # type: ignore[no-untyped-def]
    def _get(slug: str) -> dict:
        r = client.get(f"/api/v1/products/{slug}")
        assert r.status_code == 200, r.text
        return r.json()

    return _get


@pytest.fixture()
def principal_for(db: Session):  # type: ignore[no-untyped-def]
    """Build a Principal for a seeded user (for service/tool level tests)."""
    from app.models import User
    from app.services.auth_service import build_principal

    def _p(email: str):  # type: ignore[no-untyped-def]
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        return build_principal(db, user)

    return _p
