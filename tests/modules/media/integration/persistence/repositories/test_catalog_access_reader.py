"""``SqlAlchemyCatalogAccessReader`` answers access without loading titles (ADR-035).

``test_visibility_projection.py`` holds the reader to ``ViewingPolicy.permits()``
across every policy shape. This module pins what that equivalence cannot
see: the query is skipped for no ids, it selects only the certification
columns, soft-deleted rows stay out, the age is rebuilt with the mapper's
empty-label rule rather than read off the column, and ``policy`` can never
be left out.

Rows are inserted as raw models so the corrupt shapes the mapper never
writes — an age with an empty or missing label — are in the table.
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, get_type_hints

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.repositories import CatalogAccessReader, TitleAccess
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.models.series import SeriesModel
from src.modules.media.infrastructure.persistence.repositories.catalog_access_reader import (
    SqlAlchemyCatalogAccessReader,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating

_LIB_A = "lib_accessalpha1"
_LIB_B = "lib_accessbravo1"

_BOTH_LIBRARIES = ViewingPolicy.unrestricted([_LIB_A, _LIB_B])

#: Row shape: ``(id suffix, library_id, content_rating, minimum_age, deleted)``.
_ROWS: list[tuple[str, str, str | None, int | None, bool]] = [
    ("livre0000001", _LIB_A, "L", 0, False),
    ("dezesseis001", _LIB_A, "16", 16, False),
    ("rotulovazio1", _LIB_A, "", 12, False),  # empty-string label
    ("semrotulo001", _LIB_A, None, 12, False),  # age without a label
    ("naoclassif01", _LIB_A, "NR", None, False),
    ("outrabib0001", _LIB_B, "L", 0, False),
    ("apagado00001", _LIB_A, "L", 0, True),
]

#: Never seeded.
_MISSING = "inexistente1"


type _Find = Callable[
    [SqlAlchemyCatalogAccessReader, list[str], ViewingPolicy],
    Awaitable[Mapping[str, TitleAccess]],
]


async def _find_movies(
    reader: SqlAlchemyCatalogAccessReader, suffixes: list[str], policy: ViewingPolicy
) -> Mapping[str, TitleAccess]:
    return await reader.find_movie_access([MovieId(f"mov_{s}") for s in suffixes], policy=policy)


async def _find_series(
    reader: SqlAlchemyCatalogAccessReader, suffixes: list[str], policy: ViewingPolicy
) -> Mapping[str, TitleAccess]:
    return await reader.find_series_access([SeriesId(f"ser_{s}") for s in suffixes], policy=policy)


@dataclass(frozen=True)
class _Catalog:
    """One catalog model and the reader method that serves it.

    Attributes:
        prefix: External id prefix of the model's rows.
        find: Calls the reader method with ids built from suffixes.
    """

    prefix: str
    find: _Find

    def key(self, suffix: str) -> str:
        """The external id the reader keys a seeded row by."""
        return f"{self.prefix}_{suffix}"


_CATALOGS = [_Catalog("mov", _find_movies), _Catalog("ser", _find_series)]
_CATALOG_IDS = ["movies", "series"]


@pytest.fixture
async def seeded(
    session_factory: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    """Insert every row both as a movie and as a series."""
    now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    async with session_factory() as session:
        for suffix, library_id, label, age, deleted in _ROWS:
            deleted_at = now if deleted else None
            session.add(
                MovieModel(
                    external_id=f"mov_{suffix}",
                    library_id=library_id,
                    title=suffix,
                    year=2024,
                    duration=7200,
                    content_rating=label,
                    minimum_age=age,
                    rating_system="br_dejus" if label else None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=deleted_at,
                )
            )
            session.add(
                SeriesModel(
                    external_id=f"ser_{suffix}",
                    library_id=library_id,
                    title=suffix,
                    start_year=2024,
                    content_rating=label,
                    minimum_age=age,
                    rating_system="br_dejus" if label else None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=deleted_at,
                )
            )
        await session.commit()
    return session_factory


@contextmanager
def _recorded_statements(
    session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[list[str]]:
    """Collect every SQL statement the engine sends while the block runs."""
    engine = session_factory.kw["bind"].sync_engine
    statements: list[str] = []

    def record(*args: Any) -> None:
        # ``before_cursor_execute(conn, cursor, statement, ...)``
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.mark.integration
@pytest.mark.parametrize("catalog", _CATALOGS, ids=_CATALOG_IDS)
class TestCatalogAccessReader:
    """Behavior the projection equivalence test does not pin."""

    async def test_no_ids_return_empty_without_querying(self, seeded, catalog):
        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)

            with _recorded_statements(seeded) as statements:
                empty = await catalog.find(reader, [], _BOTH_LIBRARIES)
            assert empty == {}
            assert statements == [], "an empty lookup must not reach the database"

            # Positive control: the recorder does see the reader's query.
            with _recorded_statements(seeded) as statements:
                await catalog.find(reader, ["livre0000001"], _BOTH_LIBRARIES)
            assert len(statements) == 1

    async def test_selects_only_the_id_and_certification_columns(self, seeded, catalog):
        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)
            with _recorded_statements(seeded) as statements:
                await catalog.find(reader, ["livre0000001"], _BOTH_LIBRARIES)

        (statement,) = statements
        select_list = statement.split("FROM", 1)[0].removeprefix("SELECT")
        columns = [column.strip().rsplit(".", 1)[-1] for column in select_list.split(",")]
        assert columns == ["external_id", "content_rating", "minimum_age", "rating_system"]

    async def test_soft_deleted_and_missing_titles_are_absent(self, seeded, catalog):
        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)
            access = await catalog.find(
                reader,
                ["livre0000001", "livre0000001", "apagado00001", _MISSING],
                _BOTH_LIBRARIES,
            )

        assert set(access) == {catalog.key("livre0000001")}

    async def test_age_is_rebuilt_from_the_label_like_the_funnel(self, seeded, catalog):
        """A row counts as classified only with a truthy label, whatever its age column holds."""
        suffixes = ["livre0000001", "dezesseis001", "rotulovazio1", "semrotulo001", "naoclassif01"]

        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)
            access = await catalog.find(reader, suffixes, _BOTH_LIBRARIES)

        assert access == {
            catalog.key("livre0000001"): TitleAccess(minimum_age=AgeRating(0)),
            catalog.key("dezesseis001"): TitleAccess(minimum_age=AgeRating(16)),
            catalog.key("rotulovazio1"): TitleAccess(minimum_age=None),
            catalog.key("semrotulo001"): TitleAccess(minimum_age=None),
            catalog.key("naoclassif01"): TitleAccess(minimum_age=None),
        }

    async def test_library_only_policy_returns_the_age_of_a_reachable_title(self, seeded, catalog):
        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)
            access = await catalog.find(
                reader,
                ["dezesseis001", "outrabib0001"],
                ViewingPolicy.unrestricted([_LIB_A]),
            )

        assert access == {catalog.key("dezesseis001"): TitleAccess(minimum_age=AgeRating(16))}

    async def test_empty_acl_returns_nothing(self, seeded, catalog):
        """An empty ACL is deny-all, never a wildcard (ADR-018 §3)."""
        suffixes = [suffix for suffix, *_ in _ROWS]

        async with seeded() as session:
            reader = SqlAlchemyCatalogAccessReader(session)
            access = await catalog.find(reader, suffixes, ViewingPolicy(allowed_library_ids=[]))

        assert access == {}


@pytest.mark.integration
async def test_media_unit_of_work_exposes_the_reader(seeded):
    """Consumers reach the reader as ``uow.catalog_access``, bound to the UoW session."""
    async with SqlAlchemyMediaUnitOfWorkFactory(seeded)() as uow:
        access = await uow.catalog_access.find_series_access(
            [SeriesId("ser_dezesseis001")], policy=ViewingPolicy.unrestricted([_LIB_A])
        )

    assert access == {"ser_dezesseis001": TitleAccess(minimum_age=AgeRating(16))}


_POLICY_METHODS = [
    (CatalogAccessReader, "find_movie_access"),
    (CatalogAccessReader, "find_series_access"),
    (SqlAlchemyCatalogAccessReader, "find_movie_access"),
    (SqlAlchemyCatalogAccessReader, "find_series_access"),
]


@pytest.mark.parametrize(
    ("owner", "method_name"),
    _POLICY_METHODS,
    ids=[f"{owner.__name__}.{name}" for owner, name in _POLICY_METHODS],
)
def test_policy_is_a_required_keyword_that_rejects_none(owner, method_name):
    """``policy=None`` is the ungated read everywhere else; here it must not exist."""
    method = getattr(owner, method_name)
    parameter = inspect.signature(method).parameters["policy"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty, "policy must have no default"
    assert get_type_hints(method)["policy"] is ViewingPolicy, "policy must not accept None"


@pytest.mark.integration
@pytest.mark.parametrize("catalog", _CATALOGS, ids=_CATALOG_IDS)
async def test_policy_none_is_refused_at_runtime_not_read_as_ungated(seeded, catalog):
    """The signature only binds the type checker; ``None`` must still fail closed.

    Handed to the funnel, ``None`` renders no predicate at all, so a caller
    that sneaks one past mypy would read titles from libraries outside its
    ACL. The reader has to refuse it before any query runs.
    """
    reader_factory = SqlAlchemyMediaUnitOfWorkFactory(seeded)
    async with reader_factory() as uow:
        with _recorded_statements(seeded) as statements, pytest.raises(TypeError):
            await catalog.find(uow.catalog_access, ["outrabib0001"], None)  # type: ignore[arg-type]

    assert statements == [], "the reader must refuse None before querying"
