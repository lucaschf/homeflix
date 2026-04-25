"""Tests for the small helpers in stream_routes.

The route handlers themselves are thin glue (DTO lookup → FileResponse
or 404) and the only piece worth isolating is the path validation in
``_scrub_preview_files``: it sits between the DTO contract (path may
be ``None``) and the filesystem (the path may be stale) and must turn
both failure modes into 404s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from src.modules.media.presentation.routes.stream_routes import _scrub_preview_files

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
class TestScrubPreviewFiles:
    def test_raises_404_when_path_is_none(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _scrub_preview_files(None)
        assert exc.value.status_code == 404
        assert "not generated" in exc.value.detail

    def test_raises_404_when_path_is_empty_string(self) -> None:
        # The DTO surface is ``str | None`` — an empty string would be
        # an invariant violation, but we still want a clean 404 instead
        # of a misleading FileNotFoundError later.
        with pytest.raises(HTTPException) as exc:
            _scrub_preview_files("")
        assert exc.value.status_code == 404

    def test_raises_404_when_vtt_missing_on_disk(self, tmp_path: Path) -> None:
        ghost_path = tmp_path / "ghost" / "sprite.vtt"
        with pytest.raises(HTTPException) as exc:
            _scrub_preview_files(str(ghost_path))
        assert exc.value.status_code == 404
        assert "missing on disk" in exc.value.detail

    def test_returns_paired_paths_when_vtt_exists(self, tmp_path: Path) -> None:
        vtt_path = tmp_path / "sprite.vtt"
        vtt_path.write_text("WEBVTT\n", encoding="utf-8")

        returned_vtt, returned_sprite = _scrub_preview_files(str(vtt_path))

        assert returned_vtt == vtt_path
        # Sprite is derived from the VTT — same directory, ``sprite.jpg`` filename.
        assert returned_sprite == vtt_path.with_name("sprite.jpg")
