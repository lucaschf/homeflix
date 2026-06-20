"""Display-name normalization for audio and subtitle tracks.

Source files frequently carry noisy re-encode titles on their audio
tracks (release-group tags, codec dumps, site URLs). The player only
needs the *language*; what actually has to be disambiguated is the case
where several tracks share one language — typically multiple dubs.

There is no authoritative service that maps an audio track to its
dubbing studio, so detection is best-effort from the raw ``title``
text: we match it against a curated list of known studios. When that
fails we fall back to the channel layout, and finally to a plain
ordinal — which always guarantees a unique, sensible label.

The result is a structured :class:`TrackVersion` (kind + value) rather
than a finished string, so the presentation layer stays in charge of
localization (e.g. rendering an ``ordinal`` as "Versão 2" / "Version 2").
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

VersionKind = Literal["studio", "channel_layout", "ordinal", "sdh"]


@dataclass(frozen=True)
class TrackVersion:
    """A structured, language-agnostic differentiator for a track.

    Attributes:
        kind: How the track was disambiguated from same-language siblings:
            ``studio`` (a dubbing studio detected in the raw title),
            ``channel_layout`` (e.g. "5.1" vs "Stereo"), ``ordinal``
            (a 1-based position when nothing else separates them), or
            ``sdh`` (a subtitle for the deaf/hard-of-hearing).
        value: The kind's payload — the studio name, the layout string,
            the ordinal as a string, or "" for ``sdh``. ``ordinal`` and
            ``sdh`` are meant to be localized by the presentation layer.
    """

    kind: VersionKind
    value: str = ""


# Curated dubbing studios → normalized aliases (lowercase, accent-stripped).
# Matched against the raw track title on alphanumeric boundaries. There is
# no public registry for this, so the list is intentionally conservative:
# a false positive shows a wrong studio, whereas the ordinal fallback is
# always safe. Add studios here (or promote to a runtime setting) as needed.
_STUDIO_ALIASES: dict[str, tuple[str, ...]] = {
    "Herbert Richers": ("herbert richers", "richers"),
    "Álamo": ("alamo",),
    "VTI": ("vti rio", "vti"),
    "Delart": ("delart",),
    "Dublavídeo": ("dublavideo",),
    "Drei Marc": ("drei marc",),
    "Som de Vera Cruz": ("som de vera cruz", "vera cruz"),
    "Cinevídeo": ("cinevideo",),
    "Centauro": ("centauro",),
    "Unidub": ("unidub",),
    "BKS": ("bks",),
    "Marsh Mallow": ("marsh mallow", "marshmallow"),
    "Wan Macher": ("wan macher",),
    "TV Group": ("tv group", "tvgroup"),
    "Rio Sound": ("rio sound",),
    "Double Sound": ("double sound",),
    "MG Estúdio": ("mg estudio", "mg studio"),
    "Dublasom": ("dublasom",),
    "Vox Mundi": ("vox mundi",),
    "Studio Gábia": ("studio gabia",),
    "Sincrocine": ("sincrocine",),
    "Audio News": ("audio news",),
    "Som Livre": ("som livre",),
    "Master Sound": ("master sound",),
    "Netflix": ("netflix",),
    "Disney": ("disney+", "disney"),
    "Amazon": ("prime video", "amazon"),
    "HBO Max": ("hbo max", "hbomax"),
    "Star+": ("star+",),
    "Crunchyroll": ("crunchyroll",),
    "Funimation": ("funimation",),
    "Globo": ("globoplay", "tv globo"),
    "Paramount": ("paramount",),
}

# Markers that a subtitle is for the deaf / hard-of-hearing.
_SDH_MARKERS: tuple[str, ...] = ("sdh", "hearing impaired", "surdos")


def _normalize(text: str) -> str:
    """Lowercase and strip accents for tolerant alias matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _contains_token(haystack: str, token: str) -> bool:
    """Whether ``token`` appears in ``haystack`` on alphanumeric boundaries."""
    pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def detect_studio(title: str | None) -> str | None:
    """Return the canonical studio name found in ``title``, else ``None``."""
    if not title:
        return None
    normalized = _normalize(title)
    for canonical, aliases in _STUDIO_ALIASES.items():
        if any(_contains_token(normalized, alias) for alias in aliases):
            return canonical
    return None


def _is_sdh(title: str | None) -> bool:
    """Whether ``title`` marks a deaf/hard-of-hearing subtitle."""
    if not title:
        return False
    normalized = _normalize(title)
    return any(_contains_token(normalized, marker) for marker in _SDH_MARKERS)


def _render(version: TrackVersion) -> str:
    """A collision key for a version, namespaced by kind."""
    return f"{version.kind}:{version.value}"


def render_version_token(version: TrackVersion | None) -> str | None:
    """Render a version as a short, language-neutral token, or ``None``.

    Used for the HLS ``NAME=`` fallback (which can't carry structured
    data and isn't localized). Clients that read the structured
    ``TrackVersion`` should compose and localize it themselves instead.
    """
    if version is None:
        return None
    if version.kind == "ordinal":
        return f"v{version.value}"
    if version.kind == "sdh":
        return "SDH"
    return version.value


def _group_by_language(tracks: Iterable[object]) -> list[list]:
    """Group tracks by language code, preserving first-seen order."""
    groups: dict[str, list] = defaultdict(list)
    for track in tracks:
        groups[track.language.value].append(track)  # type: ignore[attr-defined]
    return list(groups.values())


def _ordinal_labels(group: list) -> dict[int, TrackVersion]:
    """Assign 1-based ordinals to every track in a group — the safe fallback."""
    return {t.index: TrackVersion("ordinal", str(i)) for i, t in enumerate(group, start=1)}


def audio_version_labels(tracks: Iterable[AudioTrack]) -> dict[int, TrackVersion | None]:
    """Compute a version label per audio track, keyed by track index.

    A language with a single track gets ``None`` (just show the language).
    Within a same-language group the chain is: detected studio → channel
    layout (when it uniquely separates the rest) → ordinal. A final guard
    falls the whole group back to ordinals if any label would collide, so
    every track in a group always renders distinctly.
    """
    result: dict[int, TrackVersion | None] = {}
    for group in _group_by_language(tracks):
        if len(group) == 1:
            result[group[0].index] = None
            continue

        labels: dict[int, TrackVersion] = {}
        for track in group:
            studio = detect_studio(track.title)
            if studio is not None:
                labels[track.index] = TrackVersion("studio", studio)

        remaining = [t for t in group if t.index not in labels]
        if remaining:
            layouts = [t.channel_layout for t in remaining]
            taken = {_render(v) for v in labels.values()}
            layouts_unique = len(set(layouts)) == len(layouts)
            if layouts_unique and taken.isdisjoint(f"channel_layout:{x}" for x in layouts):
                for track in remaining:
                    labels[track.index] = TrackVersion("channel_layout", track.channel_layout)
            else:
                for ordinal, track in enumerate(remaining, start=1):
                    labels[track.index] = TrackVersion("ordinal", str(ordinal))

        if len({_render(labels[t.index]) for t in group}) != len(group):
            labels = _ordinal_labels(group)

        result.update(labels)
    return result


def subtitle_version_labels(
    subtitles: Iterable[SubtitleTrack],
) -> dict[int, TrackVersion | None]:
    """Compute a version label per subtitle track, keyed by track index.

    Subtitles mostly only need the language; forced tracks are already
    flagged separately. This adds an ``sdh`` label for deaf/hard-of-hearing
    tracks and disambiguates genuine duplicates — tracks sharing language,
    forced-flag and SDH-status — with an ordinal.
    """
    result: dict[int, TrackVersion | None] = {}
    for group in _group_by_language(subtitles):
        sdh = {t.index for t in group if _is_sdh(t.title)}

        # Genuine duplicates share (is_forced, is_sdh); only those need an
        # ordinal. Everything else is distinguishable by language + forced.
        buckets: dict[tuple[bool, bool], list] = defaultdict(list)
        for track in group:
            buckets[(track.is_forced, track.index in sdh)].append(track)

        for track in group:
            is_sdh = track.index in sdh
            bucket = buckets[(track.is_forced, is_sdh)]
            if len(bucket) > 1:
                result[track.index] = TrackVersion("ordinal", str(bucket.index(track) + 1))
            elif is_sdh:
                result[track.index] = TrackVersion("sdh")
            else:
                result[track.index] = None
    return result


__all__ = [
    "TrackVersion",
    "VersionKind",
    "audio_version_labels",
    "detect_studio",
    "render_version_token",
    "subtitle_version_labels",
]
