import os

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from onefde.core.config import Settings
from onefde.entrypoints.api import create_app
from onefde.infrastructure.db.session import make_engine
from tests.support import models as m
from tests.support.constants import ORIGIN, PASSWORD


@pytest.fixture(scope="session")
def settings():
    load_dotenv()
    url = os.environ.get("ONEFDE_TEST_DATABASE_URL")
    if not url or not make_url(url).database.endswith("_test"):
        pytest.fail(
            "Set ONEFDE_TEST_DATABASE_URL to an isolated PostgreSQL database ending _test"
        )
    if url == os.environ.get("ONEFDE_DATABASE_URL"):
        pytest.fail("Test database must differ from development database")
    return Settings(
        _env_file=None,
        environment="development",
        database_url=url,
        owner_username="founder",
        owner_password_hash=PasswordHasher().hash(PASSWORD),
        trusted_origin=ORIGIN,
        cookie_secure=False,
        login_limit=10,
    )


@pytest.fixture(scope="session", autouse=True)
def migrate(settings):
    # Use real Alembic migrations; never metadata.create_all or SQLite.
    previous = os.environ.get("ONEFDE_DATABASE_URL")
    os.environ["ONEFDE_DATABASE_URL"] = settings.database_url.get_secret_value()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("ONEFDE_DATABASE_URL", None)
        else:
            os.environ["ONEFDE_DATABASE_URL"] = previous


@pytest.fixture(autouse=True)
def clean(settings, migrate):
    engine = make_engine(settings.database_url.get_secret_value())
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE tasks, engagements, auth_sessions, login_attempts, idempotency_records, model_profile_revisions CASCADE"
            )
        )
    engine.dispose()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def auth(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "founder", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": response.json()["csrf_token"],
        "Idempotency-Key": "test-key",
    }


@pytest.fixture
def profile(app):
    with Session(app.state.engine) as db:
        row = m.ModelProfileRevision(
            provider="deterministic-test",
            model="fixture-no-model-call",
            capabilities=[],
            config={"adapter": "deterministic-test"},
        )
        db.add(row)
        db.flush()
        identifier = str(row.revision_id)
        db.commit()
    return identifier


@pytest.fixture
def control(client, auth, app, profile):
    from tests.support.control import Control

    return Control(client, auth, app, profile)
