"""The SQL projection must agree with the domain definition (ADR-017, ADR-035 §7).

``ViewingPolicy.permits()`` is the rule; ``visibility_conditions`` is its
projection into SQL. Nothing stops the two from drifting apart except a
test that runs both over the same rows and compares the answers — and
without it, ``permits()`` quietly becomes an ornament while the ``WHERE``
clause decides something subtly different.

The row matrix deliberately includes the shapes that only exist in the
database: a row with an age but no label, and one with an empty-string
label. The mapper reads those back as *no certification at all* (it
tests the label for truthiness), so a projection that checked only
``IS NULL`` would let them through the query and have the domain deny
them — fail-open in a parental gate.
"""

import pytest
from sqlalchemy import select

from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.repositories._visibility_filter import (
    visibility_conditions,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, LibraryId

KIDS_LIB = "lib_kids12345678"
MAIN_LIB = "lib_main12345678"
OTHER_LIB = "lib_other1234567"

#: Row shape: ``(external_id, library_id, content_rating, minimum_age)``.
ROWS: list[tuple[str, str, str | None, int | None]] = [
    ("mov_livre0000001", KIDS_LIB, "L", 0),
    ("mov_dez000000001", KIDS_LIB, "10", 10),
    ("mov_doze00000001", MAIN_LIB, "12", 12),
    ("mov_pg13000000001"[:16], MAIN_LIB, "PG-13", 13),
    ("mov_quatorze0001", MAIN_LIB, "14", 14),
    ("mov_dezesseis001", MAIN_LIB, "16", 16),
    ("mov_erre00000001", MAIN_LIB, "R", 17),
    ("mov_dezoito00001", MAIN_LIB, "18", 18),
    # Undeterminable, in all three shapes that can exist in the table
    ("mov_semrotulo001", MAIN_LIB, None, None),
    ("mov_naoclassif01", MAIN_LIB, "NR", None),
    ("mov_idadesemrot1", MAIN_LIB, None, 12),  # age without a label
    ("mov_rotulovazio1", MAIN_LIB, "", 12),  # empty-string label
    # Outside every ACL used below
    ("mov_forasacl0001", OTHER_LIB, "L", 0),
]

POLICIES: list[tuple[str, ViewingPolicy | None]] = [
    ("ungated", None),
    ("deny-all", ViewingPolicy(allowed_library_ids=[])),
    ("library only", ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB])),
    (
        "limit 0",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(0)),
    ),
    (
        "limit 12",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(12)),
    ),
    (
        "limit 16",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(16)),
    ),
    (
        "limit 17",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(17)),
    ),
    (
        "limit 18",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(18)),
    ),
    (
        "limit 21",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(21)),
    ),
    (
        "one library, limited",
        ViewingPolicy(allowed_library_ids=[KIDS_LIB], maturity_limit=AgeRating(12)),
    ),
]


def _domain_visible(policy: ViewingPolicy | None) -> set[str]:
    """What the domain rule says, read straight off the row matrix.

    Mirrors ``certification_from_columns``: a row without a truthy
    label has no certification, so its age is ``None`` no matter what
    the ``minimum_age`` column holds.
    """
    if policy is None:
        return {external_id for external_id, *_ in ROWS}

    visible: set[str] = set()
    for external_id, library_id, label, age in ROWS:
        minimum_age = AgeRating(age) if (label and age is not None) else None
        if policy.permits(library_id=LibraryId(library_id), minimum_age=minimum_age):
            visible.add(external_id)
    return visible


@pytest.fixture
async def seeded_session(session_factory):
    """Insert the row matrix directly, bypassing the mapper.

    Written as raw models on purpose: the point is to exercise rows the
    mapper would never produce, which is where definition and projection
    are most likely to disagree.
    """
    from datetime import UTC, datetime

    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    async with session_factory() as session:
        for external_id, library_id, label, age in ROWS:
            session.add(
                MovieModel(
                    external_id=external_id,
                    library_id=library_id,
                    title=external_id,
                    year=2024,
                    duration=7200,
                    content_rating=label,
                    minimum_age=age,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
    return session_factory


@pytest.mark.integration
class TestProjectionMatchesDefinition:
    """The query and the rule must select exactly the same titles."""

    @pytest.mark.parametrize(("name", "policy"), POLICIES, ids=[p[0] for p in POLICIES])
    async def test_sql_selects_what_the_domain_permits(self, seeded_session, name, policy):
        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, policy))
            )
            from_sql = set(result.scalars().all())

        assert from_sql == _domain_visible(policy), (
            f"policy '{name}': SQL and ViewingPolicy.permits() disagree. "
            f"only in SQL: {sorted(from_sql - _domain_visible(policy))}; "
            f"only in domain: {sorted(_domain_visible(policy) - from_sql)}"
        )


@pytest.mark.integration
class TestSpecificGuarantees:
    """Named cases, so a failure says what broke rather than just 'sets differ'."""

    async def test_ungated_reads_see_everything(self, seeded_session):
        """The scanner and background jobs must not be filtered."""
        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, None))
            )
            assert len(set(result.scalars().all())) == len(ROWS)

    async def test_empty_acl_returns_nothing(self, seeded_session):
        policy = ViewingPolicy(allowed_library_ids=[])

        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, policy))
            )
            assert set(result.scalars().all()) == set()

    async def test_unlimited_profile_sees_the_same_rows_as_before_the_feature(self, seeded_session):
        """No regression for profiles with no maturity limit — which is all of them today."""
        policy = ViewingPolicy(allowed_library_ids=[KIDS_LIB, MAIN_LIB])

        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, policy))
            )
            visible = set(result.scalars().all())

        assert "mov_forasacl0001" not in visible
        assert len(visible) == len(ROWS) - 1

    @pytest.mark.parametrize("limit", [0, 10, 12, 14, 16, 17])
    async def test_a_limited_profile_never_sees_an_undeterminable_row(self, seeded_session, limit):
        """The fail-closed rule, including the two corrupt shapes."""
        policy = ViewingPolicy(
            allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(limit)
        )

        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, policy))
            )
            visible = set(result.scalars().all())

        assert "mov_semrotulo001" not in visible
        assert "mov_naoclassif01" not in visible
        assert "mov_idadesemrot1" not in visible, "age without a label must not count as classified"
        assert "mov_rotulovazio1" not in visible, "empty label must not count as classified"

    async def test_adult_limit_reveals_the_undeterminable_rows(self, seeded_session):
        """``AgeRating.allows(None)`` resolves to ADULT, so 18 is where they appear."""
        policy = ViewingPolicy(
            allowed_library_ids=[KIDS_LIB, MAIN_LIB], maturity_limit=AgeRating(18)
        )

        async with seeded_session() as session:
            result = await session.execute(
                select(MovieModel.external_id).where(*visibility_conditions(MovieModel, policy))
            )
            visible = set(result.scalars().all())

        assert {
            "mov_semrotulo001",
            "mov_naoclassif01",
            "mov_idadesemrot1",
            "mov_rotulovazio1",
        } <= visible
