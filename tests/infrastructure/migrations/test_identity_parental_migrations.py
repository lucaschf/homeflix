"""Migration harness for the identity revisions of the parental-control series (ADR-035).

Each revision runs its real ``upgrade()`` / ``downgrade()`` through
alembic ``Operations`` over the identity schema as it stood at
``a7e4c91d20b8`` (``fixtures/identity_schema_a7e4c91d20b8.sql``, copied
from a migrated backup of the production database), on a SQLite
connection with foreign keys on — the same listener ``migrations/env.py``
attaches in production.

Both halves of that setup are load-bearing:

- ``Base.metadata.create_all`` would build the head schema, where the new
  column already exists, so the revision under test would either fail on
  a duplicate column or never run at all.
- Without ``PRAGMA foreign_keys=ON`` a batch rebuild of ``profiles`` or
  ``users`` keeps every row, so the failure this harness exists for —
  the rebuild's ``DROP TABLE`` firing ``ON DELETE SET NULL`` /
  ``CASCADE`` and silently detaching or deleting sessions — cannot show.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from src.infrastructure.persistence.database import _enable_sqlite_foreign_keys

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from sqlalchemy.engine import Connection

_HERE = Path(__file__).resolve().parent
_VERSIONS = _HERE.parents[2] / "migrations" / "versions"
_BASE_SCHEMA = _HERE / "fixtures" / "identity_schema_a7e4c91d20b8.sql"


def _load_revision(filename: str) -> ModuleType:
    """Load a migration by path; its date-prefixed name is not importable."""
    path = _VERSIONS / filename
    spec = importlib.util.spec_from_file_location(f"_migration_{path.stem}", path)
    if spec is None or spec.loader is None:
        msg = f"Could not load migration at {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MATURITY_LIMIT = _load_revision("2026_09_13_add_maturity_limit_to_profiles.py")
_PARENTAL_PIN = _load_revision("2026_09_14_add_parental_pin_to_users.py")

_USER_ID = str(uuid.uuid4())
_SESSION_PROFILE_ID = str(uuid.uuid4())
_OTHER_PROFILE_ID = str(uuid.uuid4())
_TOKENS = ("token-tv", "token-tablet")


@pytest.fixture
def connection() -> Iterator[Connection]:
    """A FK-enforcing SQLite connection holding the seeded ``a7e4c91d20b8`` schema."""
    engine = sa.create_engine("sqlite:///:memory:")
    sa.event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    with engine.connect() as conn:
        with conn.begin():
            for statement in _schema_statements():
                conn.exec_driver_sql(statement)
            _seed(conn)
        yield conn
    engine.dispose()


def _schema_statements() -> list[str]:
    """Split the schema fixture into statements, dropping its comment header."""
    lines = _BASE_SCHEMA.read_text(encoding="utf-8").splitlines()
    sql = "\n".join(line for line in lines if not line.startswith("--"))
    return [statement for statement in sql.split(";") if statement.strip()]


def _seed(conn: Connection) -> None:
    """One user, two profiles, two sessions bound to the first profile."""
    conn.execute(
        sa.text(
            "INSERT INTO users (id, external_id, email, hashed_password) "
            "VALUES (:id, 'usr_harness00001', 'harness@example.com', 'hash')"
        ),
        {"id": _USER_ID},
    )
    for profile_id, external_id, name in (
        (_SESSION_PROFILE_ID, "prf_harness00001", "Parent"),
        (_OTHER_PROFILE_ID, "prf_harness00002", "Kid"),
    ):
        conn.execute(
            sa.text(
                "INSERT INTO profiles (id, external_id, user_id, name) "
                "VALUES (:id, :external_id, :user_id, :name)"
            ),
            {"id": profile_id, "external_id": external_id, "user_id": _USER_ID, "name": name},
        )
    for token in _TOKENS:
        conn.execute(
            sa.text(
                "INSERT INTO access_tokens (token, user_id, current_profile_id) "
                "VALUES (:token, :user_id, :profile_id)"
            ),
            {"token": token, "user_id": _USER_ID, "profile_id": _SESSION_PROFILE_ID},
        )


def _run(conn: Connection, step: str, *revisions: ModuleType) -> None:
    """Run ``upgrade`` or ``downgrade`` of each revision, in order, in one transaction."""
    with conn.begin(), Operations.context(MigrationContext.configure(conn)):
        for revision in revisions:
            getattr(revision, step)()


def _counts(conn: Connection) -> dict[str, int]:
    return {
        table: conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
        for table in ("users", "profiles", "access_tokens")
    }


def _session_bindings(conn: Connection) -> dict[str, str | None]:
    rows = conn.exec_driver_sql("SELECT token, current_profile_id FROM access_tokens").all()
    return dict(rows)


def _profile_columns(conn: Connection) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(profiles)")}


def _user_columns(conn: Connection) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")}


_SEEDED_COUNTS = {"users": 1, "profiles": 2, "access_tokens": 2}
_SEEDED_BINDINGS = dict.fromkeys(_TOKENS, _SESSION_PROFILE_ID)


class TestHarness:
    """The harness must be able to see what it is here to catch."""

    def test_foreign_keys_are_enforced(self, connection: Connection) -> None:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    def test_dropping_profiles_detaches_sessions(self, connection: Connection) -> None:
        # What a batch rebuild of ``profiles`` does to the sessions: its
        # DROP TABLE is an implicit DELETE, which fires ON DELETE SET NULL.
        with connection.begin():
            connection.exec_driver_sql("DELETE FROM profiles")

        assert set(_session_bindings(connection).values()) == {None}

    def test_dropping_users_deletes_profiles_and_sessions(self, connection: Connection) -> None:
        # What a batch rebuild of ``users`` does: ON DELETE CASCADE on both
        # ``profiles.user_id`` and ``access_tokens.user_id``.
        with connection.begin():
            connection.exec_driver_sql("DELETE FROM users")

        assert _counts(connection) == {"users": 0, "profiles": 0, "access_tokens": 0}


class TestAddMaturityLimitToProfiles:
    """Revision ``ed6c3864ea50``: ``profiles.maturity_limit``."""

    def test_chains_onto_the_minimum_age_revision(self) -> None:
        assert _MATURITY_LIMIT.down_revision == "a7e4c91d20b8"

    def test_upgrade_keeps_every_row_and_session_binding(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT)

        assert _counts(connection) == _SEEDED_COUNTS
        assert _session_bindings(connection) == _SEEDED_BINDINGS

    def test_upgrade_leaves_existing_profiles_unrestricted(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT)

        limits = connection.exec_driver_sql("SELECT maturity_limit FROM profiles").scalars().all()
        assert limits == [None, None]

    @pytest.mark.parametrize("limit", [0, 12, 21])
    def test_check_accepts_limits_on_the_scale(self, connection: Connection, limit: int) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT)

        with connection.begin():
            connection.execute(
                sa.text("UPDATE profiles SET maturity_limit = :limit"), {"limit": limit}
            )

        limits = connection.exec_driver_sql("SELECT maturity_limit FROM profiles").scalars().all()
        assert limits == [limit, limit]

    @pytest.mark.parametrize("limit", [22, -1])
    def test_check_rejects_limits_off_the_scale(self, connection: Connection, limit: int) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT)

        with pytest.raises(
            sa.exc.IntegrityError, match="ck_profiles_maturity_limit_range"
        ), connection.begin():
            connection.execute(
                sa.text("UPDATE profiles SET maturity_limit = :limit"), {"limit": limit}
            )

    def test_downgrade_drops_the_column_and_keeps_every_row(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT)
        with connection.begin():
            connection.execute(
                sa.text("UPDATE profiles SET maturity_limit = 10 WHERE id = :id"),
                {"id": _OTHER_PROFILE_ID},
            )

        _run(connection, "downgrade", _MATURITY_LIMIT)

        assert "maturity_limit" not in _profile_columns(connection)
        assert _counts(connection) == _SEEDED_COUNTS
        assert _session_bindings(connection) == _SEEDED_BINDINGS


class TestAddParentalPinToUsers:
    """Revision ``7737e1954c0c``: ``users.parental_pin_hash``, chained after ``ed6c3864ea50``."""

    def test_chains_onto_the_maturity_limit_revision(self) -> None:
        assert _PARENTAL_PIN.down_revision == _MATURITY_LIMIT.revision

    def test_upgrade_keeps_every_row_and_session_binding(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT, _PARENTAL_PIN)

        assert _counts(connection) == _SEEDED_COUNTS
        assert _session_bindings(connection) == _SEEDED_BINDINGS

    def test_upgrade_leaves_every_account_without_a_pin(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT, _PARENTAL_PIN)

        hashes = connection.exec_driver_sql("SELECT parental_pin_hash FROM users").scalars().all()
        assert hashes == [None]

    def test_check_accepts_a_hash(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT, _PARENTAL_PIN)

        with connection.begin():
            connection.exec_driver_sql("UPDATE users SET parental_pin_hash = '$argon2id$pin'")

        hashes = connection.exec_driver_sql("SELECT parental_pin_hash FROM users").scalars().all()
        assert hashes == ["$argon2id$pin"]

    def test_check_rejects_an_empty_hash(self, connection: Connection) -> None:
        # An empty string must never be able to stand in for "no PIN".
        _run(connection, "upgrade", _MATURITY_LIMIT, _PARENTAL_PIN)

        with pytest.raises(
            sa.exc.IntegrityError, match="ck_users_parental_pin_hash_not_empty"
        ), connection.begin():
            connection.exec_driver_sql("UPDATE users SET parental_pin_hash = ''")

    def test_downgrade_drops_the_column_and_keeps_every_row(self, connection: Connection) -> None:
        _run(connection, "upgrade", _MATURITY_LIMIT, _PARENTAL_PIN)
        with connection.begin():
            connection.exec_driver_sql("UPDATE users SET parental_pin_hash = '$argon2id$pin'")

        _run(connection, "downgrade", _PARENTAL_PIN)

        assert "parental_pin_hash" not in _user_columns(connection)
        assert _counts(connection) == _SEEDED_COUNTS
        assert _session_bindings(connection) == _SEEDED_BINDINGS
