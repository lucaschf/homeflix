r"""Rewrite the absolute media paths stored in the database after the library moved.

The catalog stores absolute file paths. A database whose library now lives somewhere
else (another mount point, or a Windows drive such as ``G:\library``, which no Linux
mount can reproduce) finds none of its files: playback answers 404, and a scan would
import everything again as new titles.

Stop the backend and back up the database first. Without ``--apply`` the script only
reports what would change::

    docker compose stop backend
    docker compose run --rm --entrypoint python backend \
        scripts/rebase_media_paths.py --from 'G:\library' --to /media
    docker compose up -d backend

The HLS cache is keyed by the MD5 of the file path, so moving a file orphans its
transcoded segments. ``--hls-cache`` renames the buckets of whole files and shared-file
segments to the name the new path hashes to, and records the renames in
``.rebased_buckets.json`` inside the cache. Buckets of a seek are left behind, since
their key carries the second playback started at; LRU eviction removes them eventually.

It is safe to run again, and running it with ``--hls-cache`` on a database whose paths
have already moved only renames the buckets.

Soft-deleted movies keep their old path on purpose: ``movies_fts_update`` fires on every
UPDATE and emits a 'delete' for rows that already left the search index, which corrupts
its document count. Their ``media_files`` row does move, because that row is the
tombstone that stops a scan from re-importing a title the user deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DATABASE = Path("/app/data/homeflix.db")
UNDO_MAP_FILENAME = ".rebased_buckets.json"
_SEARCH_PROBES = ("a*", "e*", "s*", "the")
_MISSING_SHOWN = 10


class RebaseAbortedError(Exception):
    """A check failed before committing, so nothing was written."""


@dataclass(frozen=True)
class PathRebase:
    """Translates stored paths from one library root to another.

    Attributes:
        old_root: Root the database knows, with its trailing separator.
        new_root: Root the files are at now, with its trailing slash.
    """

    old_root: str
    new_root: str

    @classmethod
    def between(cls, old_root: str, new_root: str) -> PathRebase:
        """Build a rebase, tolerating a trailing separator on either root."""
        separator = "\\" if "\\" in old_root else "/"
        return cls(old_root.rstrip(separator) + separator, new_root.rstrip("/") + "/")

    @property
    def _old_separator(self) -> str:
        return "\\" if "\\" in self.old_root else "/"

    def forward(self, value: str | None) -> str | None:
        """Translate one path; anything outside the old root stays as it is."""
        if value is None:
            return None
        if value == self.old_root[:-1]:
            return self.new_root[:-1]
        if not value.startswith(self.old_root):
            return value
        return self.new_root + value[len(self.old_root) :].replace(self._old_separator, "/")

    def backward(self, value: str) -> str:
        """Rebuild the old form of a path that is under the new root."""
        return self.old_root + value[len(self.new_root) :].replace("/", self._old_separator)

    def forward_json(self, raw: str | None) -> str | None:
        """Translate every path nested in a JSON document, keeping its escaping style."""
        if raw is None or json.dumps(self.old_root[:-1])[1:-1] not in raw:
            return raw
        return json.dumps(self._walk(json.loads(raw)), ensure_ascii=raw.isascii())

    def _walk(self, node: Any) -> Any:
        if isinstance(node, str):
            return self.forward(node)
        if isinstance(node, list):
            return [self._walk(item) for item in node]
        if isinstance(node, dict):
            return {key: self._walk(value) for key, value in node.items()}
        return node


@dataclass(frozen=True)
class RebaseReport:
    """What a run changed, or would change without ``apply``.

    Attributes:
        rows: Rows rewritten per table.
        missing: Live paths that do not exist at the new root.
        buckets: HLS cache renames, old name to new name.
        failed_buckets: Buckets that could not be renamed and kept their old name.
    """

    rows: dict[str, int]
    missing: list[str]
    buckets: dict[str, str]
    failed_buckets: list[str]


def _bucket_name(path: str, start: int = 0, end: int | None = None) -> str:
    """Name a cache bucket as ``HlsCacheStore.get_path_hash`` does."""
    key = path if start == 0 and end is None else f"{path}:{start}:{end}"
    return hashlib.md5(key.encode()).hexdigest()


def _rewrite_rows(connection: sqlite3.Connection, rebase: PathRebase) -> dict[str, int]:
    """Rewrite every path column, inside the caller's transaction."""
    under_root = "substr({column}, 1, length(:root)) = :root"
    file_or_sprite = (
        f"({under_root.format(column='file_path')} "
        f"or {under_root.format(column='scrub_preview_path')})"
    )
    file_and_sprite = (
        "set file_path = rebased(file_path), scrub_preview_path = rebased(scrub_preview_path)"
    )
    json_root = json.dumps(rebase.old_root[:-1])[1:-1]
    statements = {
        "movies": f"update movies {file_and_sprite} where deleted_at is null and {file_or_sprite}",
        "episodes": f"update episodes {file_and_sprite} where {file_or_sprite}",
        "media_files": (
            "update media_files set file_path = rebased(file_path), "
            "subtitle_tracks_json = rebased_json(subtitle_tracks_json) "
            f"where {under_root.format(column='file_path')} "
            "or instr(subtitle_tracks_json, :json_root) > 0"
        ),
        "libraries": (
            "update libraries set paths = rebased_json(paths) " "where instr(paths, :json_root) > 0"
        ),
        "subtitle_ocr_runs": (
            "update subtitle_ocr_runs set file_path = rebased(file_path) "
            f"where {under_root.format(column='file_path')}"
        ),
    }
    parameters = {"root": rebase.old_root, "json_root": json_root}
    return {
        table: connection.execute(statement, parameters).rowcount
        for table, statement in statements.items()
    }


def _live_paths(connection: sqlite3.Connection, rebase: PathRebase) -> set[str]:
    """Return the paths under the new root that a live title depends on."""
    queries = (
        "select file_path from movies where deleted_at is null",
        "select scrub_preview_path from movies where deleted_at is null",
        "select file_path from episodes where deleted_at is null",
        "select scrub_preview_path from episodes where deleted_at is null",
        """
        select f.file_path from media_files f
        left join movies m on m.id = f.movie_id
        where f.deleted_at is null and (f.movie_id is null or m.deleted_at is null)
        """,
    )
    paths: set[str] = set()
    for query in queries:
        paths.update(row[0] for row in connection.execute(query) if row[0] is not None)
    return {path for path in paths if path.startswith(rebase.new_root)}


def _search_snapshot(connection: sqlite3.Connection) -> dict[str, list[tuple[int, int]]]:
    """Capture what the movie search returns, and whether it can still rank it."""
    query = (
        "select rowid, bm25(movies_fts) is null from movies_fts "
        "where movies_fts match ? order by rowid"
    )
    return {term: connection.execute(query, (term,)).fetchall() for term in _SEARCH_PROBES}


def _plan_bucket_renames(
    connection: sqlite3.Connection, rebase: PathRebase, cache: Path
) -> dict[str, str]:
    """Map the cache buckets of moved files to the name their new path hashes to."""
    keys: set[tuple[str, int, int | None]] = set()
    for query in (
        "select file_path from movies where file_path is not null",
        "select file_path from episodes where file_path is not null",
        "select file_path from media_files",
    ):
        keys.update((row[0], 0, None) for row in connection.execute(query))
    keys.update(
        connection.execute(
            "select file_path, start_offset_seconds, end_offset_seconds from media_files "
            "where start_offset_seconds is not null and end_offset_seconds is not null"
        )
    )
    plan: dict[str, str] = {}
    for path, start, end in keys:
        if not path.startswith(rebase.new_root):
            continue
        old_name = _bucket_name(rebase.backward(path), start, end)
        new_name = _bucket_name(path, start, end)
        if (cache / old_name).is_dir() and not (cache / new_name).exists():
            plan[old_name] = new_name
    return plan


def _rename_buckets(cache: Path, plan: dict[str, str]) -> list[str]:
    """Apply the renames, recording them so they can be undone.

    A file held open on the host (an antivirus or indexer on Windows) blocks the rename
    of its bucket. That bucket stays intact under its old name and the others go on;
    running the script again retries it.

    Returns:
        The buckets left under their old name.
    """
    undo_map = cache / UNDO_MAP_FILENAME
    undo: dict[str, str] = (
        json.loads(undo_map.read_text(encoding="utf-8")) if undo_map.exists() else {}
    )
    failed: list[str] = []
    for old_name, new_name in plan.items():
        try:
            (cache / old_name).rename(cache / new_name)
        except OSError:
            failed.append(old_name)
        else:
            undo[new_name] = old_name
    if undo:
        undo_map.write_text(json.dumps(undo, indent=2), encoding="utf-8")
    return failed


def rebase_media_paths(
    database: Path,
    rebase: PathRebase,
    *,
    hls_cache: Path | None = None,
    allow_missing: bool = False,
    apply: bool = False,
) -> RebaseReport:
    """Rewrite the stored paths in one transaction, committing only if the checks pass.

    Args:
        database: SQLite database to rewrite.
        rebase: The old and new library roots.
        hls_cache: HLS cache directory whose buckets should follow the files.
        allow_missing: Commit even if a live path does not exist at the new root.
        apply: Write the changes; otherwise only report them.

    Returns:
        What changed, or what would change when ``apply`` is false.

    Raises:
        RebaseAbortedError: A live file is missing or the search index changed.
    """
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.create_function("rebased", 1, rebase.forward, deterministic=True)
        connection.create_function("rebased_json", 1, rebase.forward_json, deterministic=True)
        search_before = _search_snapshot(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            rows = _rewrite_rows(connection, rebase)
            missing = sorted(
                path for path in _live_paths(connection, rebase) if not Path(path).is_file()
            )
            if missing and not allow_missing:
                shown = "\n  ".join(missing[:_MISSING_SHOWN])
                message = (
                    f"{len(missing)} live paths do not exist under {rebase.new_root}; "
                    f"is --to right? (--allow-missing overrides)\n  {shown}"
                )
                raise RebaseAbortedError(message)
            if _search_snapshot(connection) != search_before:
                message = "the rewrite changed the movie search results"
                raise RebaseAbortedError(message)
            buckets = _plan_bucket_renames(connection, rebase, hls_cache) if hls_cache else {}
            connection.execute("COMMIT" if apply else "ROLLBACK")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
    failed = _rename_buckets(hls_cache, buckets) if apply and hls_cache and buckets else []
    return RebaseReport(rows=rows, missing=missing, buckets=buckets, failed_buckets=failed)


def main() -> None:
    """Synchronous CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="old_root", required=True, help="Root the database knows.")
    parser.add_argument("--to", dest="new_root", required=True, help="Root the files are at now.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE, help="SQLite database.")
    parser.add_argument("--hls-cache", type=Path, help="HLS cache whose buckets follow the files.")
    parser.add_argument(
        "--allow-missing", action="store_true", help="Commit even if a live file is missing."
    )
    parser.add_argument("--apply", action="store_true", help="Write the changes.")
    args = parser.parse_args()

    try:
        report = rebase_media_paths(
            args.db,
            PathRebase.between(args.old_root, args.new_root),
            hls_cache=args.hls_cache,
            allow_missing=args.allow_missing,
            apply=args.apply,
        )
    except (RebaseAbortedError, sqlite3.Error) as exc:
        print(f"aborted, nothing was written: {exc}", file=sys.stderr)
        sys.exit(1)

    for table, count in report.rows.items():
        print(f"  {table}: {count} rows")
    print(f"  live paths missing on disk: {len(report.missing)}")
    if args.hls_cache:
        print(f"  HLS buckets: {len(report.buckets)}")
    print("applied" if args.apply else "dry run, nothing was written (add --apply)")
    if report.failed_buckets:
        print(
            f"{len(report.failed_buckets)} HLS buckets could not be renamed and kept their "
            "old name; run this again to retry them",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
