"""Tests for ``scripts/rebase_media_paths.py``.

They run against the real schema (``create_all`` plus the FTS5 migration, triggers
included) because the two ways this rewrite goes wrong are invisible otherwise: an
UPDATE on a soft-deleted movie fires ``movies_fts_update`` and corrupts the search
index, and a soft-deleted movie whose ``media_files`` row keeps the old path stops
being a tombstone, so the next scan re-imports a title the user deleted.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

import src.modules.library.infrastructure.persistence.models.library_model
import src.modules.media.infrastructure.persistence.models
import src.modules.streaming.infrastructure.persistence.models.subtitle_ocr_run  # noqa: F401
from src.infrastructure.persistence import Base
from src.modules.streaming.infrastructure.streaming.hls_cache_store import HlsCacheStore
from tests.modules.media.integration.conftest import install_fts5_schema

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

_OLD_ROOT = "G:\\library"
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rebase_media_paths.py"
_unique = itertools.count(1)


def _load_script() -> ModuleType:
    """Load the script by path; ``scripts`` is not a package."""
    spec = importlib.util.spec_from_file_location("_rebase_media_paths", _SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"Could not load {_SCRIPT}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _old(relative: str) -> str:
    return f"{_OLD_ROOT}\\{relative}"


def _insert(connection: sqlite3.Connection, table: str, **values: Any) -> int:
    """Insert a row, filling every other required column with a dummy value."""
    row = dict(values)
    for _, name, column_type, not_null, default, primary_key in connection.execute(
        f'pragma table_info("{table}")'
    ):
        if name in row or primary_key or not not_null or default is not None:
            continue
        numeric = column_type.upper().startswith(("INT", "BOOL", "FLOAT", "NUMERIC", "BIG"))
        row[name] = 0 if numeric else f"{name}-{next(_unique)}"
    columns = ", ".join(f'"{name}"' for name in row)
    marks = ", ".join("?" for _ in row)
    cursor = connection.execute(
        f'insert into "{table}" ({columns}) values ({marks})',
        tuple(row.values()),
    )
    return int(cursor.lastrowid or 0)


class _Library:
    """A migrated database seeded with old-root paths, and the moved files on disk."""

    def __init__(self, root: Path) -> None:
        self.database = root / "homeflix.db"
        self.media = root / "media"
        self.new_root = self.media.as_posix()
        self.hls_cache = root / "hls_cache"
        self.hls_cache.mkdir()
        self.rebase = script.PathRebase.between(_OLD_ROOT, self.new_root)
        self._create_schema()
        self._seed()

    def new(self, relative: str) -> str:
        return f"{self.new_root}/{relative}"

    def _create_schema(self) -> None:
        engine = sa.create_engine(f"sqlite:///{self.database.as_posix()}")
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            install_fts5_schema(connection)
        engine.dispose()

    def _touch(self, relative: str) -> None:
        path = self.media / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def _seed(self) -> None:
        for relative in (
            "Movies/Alpha/Alpha.mkv",
            "Movies/Alpha/.homeflix/thumbnails/Alpha/sprite.vtt",
            "Movies/Apple/Apple.mkv",
            "Movies/Archived/Archived.mkv",
            "Series/Show/S01E01.mkv",
            "Series/Show/.homeflix/thumbnails/S01E01/sprite.vtt",
            "Series/Show/both.mkv",
        ):
            self._touch(relative)
        tracks = json.dumps(
            [
                {"index": 0, "is_external": True, "file_path": _old("Movies\\Alpha\\Alpha.srt")},
                {"index": 1, "is_external": False, "title": "Direção"},
            ],
        )
        with sqlite3.connect(self.database) as connection:
            alpha = _insert(
                connection,
                "movies",
                title="Alpha",
                file_path=_old("Movies\\Alpha\\Alpha.mkv"),
                scrub_preview_path=_old("Movies\\Alpha\\.homeflix\\thumbnails\\Alpha\\sprite.vtt"),
            )
            _insert(connection, "movies", title="Apple", file_path=_old("Movies\\Apple\\Apple.mkv"))
            archived = _insert(
                connection,
                "movies",
                title="Archived",
                file_path=_old("Movies\\Archived\\Archived.mkv"),
                deleted_at="2026-01-01 00:00:00",
            )
            episode = _insert(
                connection,
                "episodes",
                file_path=_old("Series\\Show\\S01E01.mkv"),
                scrub_preview_path=_old("Series\\Show\\.homeflix\\thumbnails\\S01E01\\sprite.vtt"),
            )
            _insert(
                connection,
                "media_files",
                movie_id=alpha,
                file_path=_old("Movies\\Alpha\\Alpha.mkv"),
                subtitle_tracks_json=tracks,
            )
            _insert(
                connection,
                "media_files",
                movie_id=archived,
                file_path=_old("Movies\\Archived\\Archived.mkv"),
            )
            _insert(
                connection,
                "media_files",
                episode_id=episode,
                file_path=_old("Series\\Show\\both.mkv"),
                start_offset_seconds=30,
                end_offset_seconds=90,
            )
            _insert(
                connection,
                "libraries",
                paths=json.dumps([_old("Movies"), "/elsewhere"]),
            )
            _insert(connection, "subtitle_ocr_runs", file_path=_old("Movies\\Alpha\\Alpha.mkv"))

    def query(self, sql: str) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.database) as connection:
            return connection.execute(sql).fetchall()

    def value(self, sql: str) -> Any:
        return self.query(sql)[0][0]

    def run(self, **options: Any) -> Any:
        options.setdefault("apply", True)
        return script.rebase_media_paths(self.database, self.rebase, **options)


@pytest.fixture
def library(tmp_path: Path) -> Iterator[_Library]:
    yield _Library(tmp_path)


def _bucket_for(path: str, start: int = 0, end: int | None = None) -> str:
    """Name a bucket the way the running app does, so the two cannot drift apart."""
    store = HlsCacheStore(Path(), MagicMock(), MagicMock())
    return store.get_path_hash(path, start, end)


def _add_bucket(cache: Path, name: str) -> Path:
    bucket = cache / name
    bucket.mkdir()
    (bucket / "master.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    return bucket


class TestDatabaseRewrite:
    def test_rewrites_every_stored_path(self, library: _Library) -> None:
        library.run()

        assert library.value("select file_path from movies where title = 'Alpha'") == library.new(
            "Movies/Alpha/Alpha.mkv"
        )
        assert library.value(
            "select scrub_preview_path from movies where title = 'Alpha'"
        ) == library.new("Movies/Alpha/.homeflix/thumbnails/Alpha/sprite.vtt")
        assert library.value("select file_path from episodes") == library.new(
            "Series/Show/S01E01.mkv"
        )
        assert library.value("select scrub_preview_path from episodes") == library.new(
            "Series/Show/.homeflix/thumbnails/S01E01/sprite.vtt"
        )
        assert library.value("select file_path from subtitle_ocr_runs") == library.new(
            "Movies/Alpha/Alpha.mkv"
        )

    def test_rewrites_paths_nested_in_json_and_leaves_the_rest_alone(
        self, library: _Library
    ) -> None:
        library.run()

        assert json.loads(library.value("select paths from libraries")) == [
            library.new("Movies"),
            "/elsewhere",
        ]
        tracks = json.loads(
            library.value("select subtitle_tracks_json from media_files where movie_id = 1")
        )
        assert tracks[0]["file_path"] == library.new("Movies/Alpha/Alpha.srt")
        assert tracks[1]["title"] == "Direção"

    def test_library_rooted_exactly_at_the_old_root(self, library: _Library) -> None:
        with sqlite3.connect(library.database) as connection:
            connection.execute("update libraries set paths = ?", (json.dumps([_OLD_ROOT]),))

        library.run()

        assert json.loads(library.value("select paths from libraries")) == [library.new_root]

    def test_moves_between_posix_roots(self) -> None:
        rebase = script.PathRebase.between("/mnt/old/", "/media/")

        assert rebase.forward("/mnt/old/Movies/a b.mkv") == "/media/Movies/a b.mkv"
        assert rebase.backward("/media/Movies/a b.mkv") == "/mnt/old/Movies/a b.mkv"
        assert rebase.forward("/mnt/older/a.mkv") == "/mnt/older/a.mkv"

    def test_windows_root_is_not_matched_by_a_longer_sibling(self) -> None:
        rebase = script.PathRebase.between(_OLD_ROOT, "/media")

        assert rebase.forward("G:\\library2\\a.mkv") == "G:\\library2\\a.mkv"
        assert rebase.backward("/media/Movies/a.mkv") == "G:\\library\\Movies\\a.mkv"

    def test_second_run_changes_nothing(self, library: _Library) -> None:
        library.run()

        report = library.run()

        assert set(report.rows.values()) == {0}


class TestSoftDeletedMovies:
    def test_movie_row_keeps_its_old_path(self, library: _Library) -> None:
        library.run()

        assert library.value("select file_path from movies where title = 'Archived'") == _old(
            "Movies\\Archived\\Archived.mkv"
        )

    def test_file_row_moves_so_it_still_stops_a_reimport(self, library: _Library) -> None:
        library.run()

        assert library.value("select file_path from media_files where movie_id = 3") == library.new(
            "Movies/Archived/Archived.mkv"
        )

    def test_search_index_survives_the_rewrite(self, library: _Library) -> None:
        library.run()

        ranked = library.query(
            "select rowid, bm25(movies_fts) from movies_fts where movies_fts match 'a*' "
            "order by rowid"
        )
        assert [row[0] for row in ranked] == [1, 2]
        assert all(row[1] is not None for row in ranked)


class TestDryRun:
    def test_reports_the_changes_but_writes_nothing(self, library: _Library) -> None:
        report = library.run(apply=False)

        assert report.rows["movies"] == 2
        assert report.rows["media_files"] == 3
        assert library.value("select file_path from episodes") == _old("Series\\Show\\S01E01.mkv")

    def test_leaves_hls_buckets_alone(self, library: _Library) -> None:
        old_name = _bucket_for(_old("Movies\\Alpha\\Alpha.mkv"))
        _add_bucket(library.hls_cache, old_name)

        report = library.run(apply=False, hls_cache=library.hls_cache)

        assert report.buckets == {old_name: _bucket_for(library.new("Movies/Alpha/Alpha.mkv"))}
        assert (library.hls_cache / old_name).is_dir()


class TestMissingFiles:
    def test_aborts_and_writes_nothing(self, library: _Library) -> None:
        (library.media / "Movies/Apple/Apple.mkv").unlink()

        with pytest.raises(script.RebaseAbortedError, match="Apple"):
            library.run()

        assert library.value("select file_path from episodes") == _old("Series\\Show\\S01E01.mkv")

    def test_a_wrong_destination_aborts_too(self, library: _Library) -> None:
        wrong = script.PathRebase.between(_OLD_ROOT, library.new("nowhere"))

        with pytest.raises(script.RebaseAbortedError):
            script.rebase_media_paths(library.database, wrong, apply=True)

    def test_can_be_overridden(self, library: _Library) -> None:
        (library.media / "Movies/Apple/Apple.mkv").unlink()

        report = library.run(allow_missing=True)

        assert report.missing == [library.new("Movies/Apple/Apple.mkv")]
        assert library.value("select file_path from movies where title = 'Apple'") == library.new(
            "Movies/Apple/Apple.mkv"
        )

    def test_soft_deleted_movie_files_do_not_count(self, library: _Library) -> None:
        (library.media / "Movies/Archived/Archived.mkv").unlink()

        assert library.run().missing == []


class TestHlsBuckets:
    def test_renames_to_the_name_the_new_path_hashes_to(self, library: _Library) -> None:
        bucket = _add_bucket(library.hls_cache, _bucket_for(_old("Movies\\Alpha\\Alpha.mkv")))
        unrelated = _add_bucket(library.hls_cache, _bucket_for("G:\\other\\x.mkv"))

        library.run(hls_cache=library.hls_cache)

        moved = library.hls_cache / _bucket_for(library.new("Movies/Alpha/Alpha.mkv"))
        assert (moved / "master.m3u8").is_file()
        assert not bucket.exists()
        assert unrelated.is_dir()

    def test_renames_the_bucket_of_a_shared_file_segment(self, library: _Library) -> None:
        _add_bucket(library.hls_cache, _bucket_for(_old("Series\\Show\\both.mkv"), 30, 90))

        library.run(hls_cache=library.hls_cache)

        assert (
            library.hls_cache / _bucket_for(library.new("Series/Show/both.mkv"), 30, 90)
        ).is_dir()

    def test_keeps_a_map_to_undo_the_renames(self, library: _Library) -> None:
        old_name = _bucket_for(_old("Movies\\Alpha\\Alpha.mkv"))
        _add_bucket(library.hls_cache, old_name)

        library.run(hls_cache=library.hls_cache)

        undo = json.loads((library.hls_cache / script.UNDO_MAP_FILENAME).read_text("utf-8"))
        assert undo == {_bucket_for(library.new("Movies/Alpha/Alpha.mkv")): old_name}

    def test_does_not_overwrite_a_bucket_already_at_the_new_name(self, library: _Library) -> None:
        old_bucket = _add_bucket(library.hls_cache, _bucket_for(_old("Movies\\Alpha\\Alpha.mkv")))
        _add_bucket(library.hls_cache, _bucket_for(library.new("Movies/Alpha/Alpha.mkv")))

        report = library.run(hls_cache=library.hls_cache)

        assert report.buckets == {}
        assert old_bucket.is_dir()

    def test_works_on_a_database_whose_paths_already_moved(self, library: _Library) -> None:
        library.run()
        _add_bucket(library.hls_cache, _bucket_for(_old("Series\\Show\\S01E01.mkv")))

        library.run(hls_cache=library.hls_cache)

        assert (library.hls_cache / _bucket_for(library.new("Series/Show/S01E01.mkv"))).is_dir()

    def test_a_locked_bucket_does_not_stop_the_others_and_is_retried(
        self, library: _Library, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = library.hls_cache
        locked = _add_bucket(cache, _bucket_for(_old("Movies\\Alpha\\Alpha.mkv")))
        free_name = _bucket_for(_old("Movies\\Apple\\Apple.mkv"))
        _add_bucket(cache, free_name)
        moved_locked = _bucket_for(library.new("Movies/Alpha/Alpha.mkv"))
        moved_free = _bucket_for(library.new("Movies/Apple/Apple.mkv"))
        real_rename = Path.rename

        def rename(self: Path, target: Path) -> Path:
            if self.name == locked.name:
                raise PermissionError(13, "held by another process")
            return real_rename(self, target)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "rename", rename)
            report = library.run(hls_cache=cache)

        assert report.failed_buckets == [locked.name]
        assert (locked / "master.m3u8").is_file()
        assert (cache / moved_free).is_dir()
        undo = json.loads((cache / script.UNDO_MAP_FILENAME).read_text("utf-8"))
        assert undo == {moved_free: free_name}

        retry = library.run(hls_cache=cache)

        assert retry.failed_buckets == []
        assert (cache / moved_locked).is_dir()
        undo = json.loads((cache / script.UNDO_MAP_FILENAME).read_text("utf-8"))
        assert undo == {moved_free: free_name, moved_locked: locked.name}
