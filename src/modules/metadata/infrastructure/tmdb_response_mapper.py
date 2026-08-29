"""Pure TMDB-payload → port-DTO mapping for the TMDB metadata provider.

This module owns the *translation* half of the TMDB Anti-Corruption
Layer: given an already-fetched TMDB JSON payload (a plain ``dict``),
shape it into the module's port DTOs (``MediaMetadata``,
``SearchCandidate``, ``PersonMetadata``, ``CollectionDetailMetadata``,
``SeasonMetadata`` …). It performs **no** HTTP — every method operates on
data the ``TmdbClient`` has already retrieved. Keeping the shaping here
leaves ``TmdbClient`` as a thin HTTP orchestrator (params/auth/GET/retry/
rate-limit) and makes the picking logic (logos, ratings, translations,
year matching) unit-testable without a network.
"""

from typing import Any, cast

from src.modules.metadata.application.ports.metadata_provider_port import (
    CollectionDetailMetadata,
    CollectionMetadata,
    CollectionPartMetadata,
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    LocalizedTextFields,
    MediaMetadata,
    PersonMetadata,
    SearchCandidate,
    SeasonMetadata,
)
from src.shared_kernel.value_objects import ContentRating

_MAX_CAST = 15

_TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"


def _safe_int(value: object, default: int) -> int:
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return default


def _episode_payload_by_number(
    season_payload: dict[str, Any], episode_number: int
) -> dict[str, Any] | None:
    """Find an episode dict in a season payload by its ``episode_number``."""
    episodes: list[dict[str, Any]] = season_payload.get("episodes", [])
    for ep in episodes:
        if ep.get("episode_number") == episode_number:
            return ep
    return None


def _pick_translation_title(
    translations: list[dict[str, Any]], locale: str, title_key: str
) -> str | None:
    """Pick a title from a TMDB ``/translations`` payload for a BCP-47 locale.

    Prefers an exact language+region match (``pt`` + ``BR`` for
    ``pt-BR``), then falls back to the first entry sharing the base
    language. Returns ``None`` when the locale has no usable title.
    """
    parts = locale.split("-", 1)
    lang = parts[0].lower()
    region = parts[1].upper() if len(parts) > 1 else None

    base: str | None = None
    for tr in translations:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("iso_639_1", "")).lower() != lang:
            continue
        title = (tr.get("data") or {}).get(title_key)
        if not isinstance(title, str) or not title:
            continue
        if region and str(tr.get("iso_3166_1", "")).upper() == region:
            return title
        if base is None:
            base = title
    return base


def _extract_year_prefix(value: object) -> int | None:
    """Return the 4-digit year prefix of an ISO date string, or ``None``.

    Both ``release_date`` (movies) and ``first_air_date`` (TV) come
    in as ``"YYYY-MM-DD"`` — or empty/missing for poorly catalogued
    entries. Defensive parsing here avoids ``ValueError`` polluting
    the picker payload when TMDB returns ``""`` or no field at all.
    """
    if not isinstance(value, str) or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


class TmdbResponseMapper:
    """Translates fetched TMDB payloads into the metadata port DTOs.

    Pure — holds no HTTP client. It carries only the small amount of
    configuration the shaping logic needs: the image CDN base (to
    rewrite ``*_path`` fields into absolute URLs) and the catalog's
    supported BCP-47 locales (which drive content-rating jurisdiction
    order and the ``/translations`` title map).

    Args:
        image_base_url: Base URL for the TMDB image CDN.
        supported_locales: BCP-47 tags the catalog serves (e.g.
            ``("en", "pt-BR")``). Used to derive the content-rating
            jurisdiction order and to select translated titles.
    """

    def __init__(
        self,
        image_base_url: str = _TMDB_IMAGE_BASE,
        supported_locales: tuple[str, ...] = ("en", "pt-BR"),
    ) -> None:
        self._image_base_url = image_base_url
        self._supported_locales = list(supported_locales)

    def image_url(self, path: str | None) -> str | None:
        """Rewrite a TMDB ``*_path`` field into an absolute CDN URL."""
        return f"{self._image_base_url}{path}" if path else None

    @staticmethod
    def _logo_rank(logo: dict[str, object], target: str, target_base: str) -> int:
        """Score a TMDB logo entry for language preference (lower = better).

        Priority:
            0. exact language match (``pt-BR`` for a pt-BR request)
            1. base language match (``pt`` covers ``pt-BR`` / ``pt-PT``)
            2. English (``en``)
            3. language-neutral (``iso_639_1 is None``)
            4. anything else — last-resort fallback
        """
        iso = logo.get("iso_639_1")
        if iso is None:
            return 3
        if not isinstance(iso, str):
            return 4
        iso_lower = iso.lower()
        if iso_lower == target:
            return 0
        if iso_lower.split("-", 1)[0] == target_base:
            return 1
        if iso_lower == "en":
            return 2
        return 4

    def pick_best_logo_url(
        self,
        logos: list[dict[str, object]] | None,
        language: str,
    ) -> str | None:
        """Pick the best-language logo URL from a TMDB ``logos`` payload.

        Pure function — no HTTP. Caller already has the logo list from
        ``data["images"]["logos"]`` on a details response that included
        ``images`` in ``append_to_response``. Returns ``None`` when the
        list is empty / missing or the best entry has no ``file_path``.
        """
        if not logos:
            return None
        target = language.lower()
        target_base = target.split("-", 1)[0]
        best = min(logos, key=lambda logo: self._logo_rank(logo, target, target_base))
        return self.image_url(cast("str | None", best.get("file_path")))

    @staticmethod
    def pick_year_match(
        results: list[dict[str, object]],
        year: int | None,
        date_field: str,
    ) -> dict[str, object] | None:
        """Pick the first result whose ``date_field`` starts with ``year``.

        Without a ``year`` hint, falls back to the first result (TMDB's
        own popularity ranking). With a ``year`` hint, returns ``None``
        if no result matches — strict year semantics, to avoid silently
        returning a popular off-year entry.
        """
        if not results:
            return None
        if year is None:
            return results[0]

        prefix = f"{year}"
        for result in results:
            date = result.get(date_field)
            if isinstance(date, str) and date.startswith(prefix):
                return result
        return None

    @staticmethod
    def parse_trailer(videos: dict[str, object]) -> str | None:
        """Extract the best YouTube trailer URL from TMDB videos.

        Ranking: official Trailer > any Trailer > official Teaser > any Teaser.
        """
        results = videos.get("results", [])
        if not isinstance(results, list):
            return None

        candidates: list[dict[str, object]] = [
            v
            for v in results
            if isinstance(v, dict)
            and v.get("site") == "YouTube"
            and v.get("type") in ("Trailer", "Teaser")
            and v.get("key")
        ]

        if not candidates:
            return None

        def _rank(video: dict[str, object]) -> int:
            is_trailer = video.get("type") == "Trailer"
            is_official = bool(video.get("official"))
            if is_trailer and is_official:
                return 0
            if is_trailer:
                return 1
            if is_official:
                return 2
            return 3

        ranked = sorted(enumerate(candidates), key=lambda item: (_rank(item[1]), item[0]))
        best = ranked[0][1]

        return f"https://www.youtube.com/watch?v={best['key']}"

    def parse_cast(self, cast_data: list[dict[str, object]]) -> list[CreditPerson]:
        """Parse TMDB cast data into CreditPerson list (top billed)."""
        sorted_cast = sorted(cast_data, key=lambda c: _safe_int(c.get("order"), 999))
        return [
            self._to_credit_person(c, role_key="character")
            for c in sorted_cast[:_MAX_CAST]
            if c.get("name")
        ]

    def parse_crew(
        self, crew_data: list[dict[str, object]]
    ) -> tuple[list[CreditPerson], list[CreditPerson]]:
        """Parse TMDB crew data into directors and writers lists."""
        directors: list[CreditPerson] = []
        writers: list[CreditPerson] = []
        seen_directors: set[str] = set()
        seen_writers: set[str] = set()

        for c in crew_data:
            name = str(c.get("name", ""))
            if not name:
                continue
            job = str(c.get("job", "")).lower()
            dept = str(c.get("department", "")).lower()
            if job == "director" and name not in seen_directors:
                directors.append(self._to_credit_person(c, role_key="job"))
                seen_directors.add(name)
            elif dept == "writing" and name not in seen_writers:
                writers.append(self._to_credit_person(c, role_key="job"))
                seen_writers.add(name)

        return directors, writers

    def _to_credit_person(self, data: dict[str, object], role_key: str) -> CreditPerson:
        """Convert a TMDB cast/crew dict to a CreditPerson."""
        profile_path = str(data.get("profile_path", "")) or None
        return CreditPerson(
            name=str(data.get("name", "")),
            role=str(data.get(role_key, "")) or None,
            profile_url=self.image_url(profile_path),
            tmdb_id=int(str(data["id"])) if data.get("id") else None,
        )

    def _preferred_rating_countries(self) -> list[str]:
        """Jurisdiction order for picking a content rating — config-driven.

        Built from the *region* subtag of each ``supported_locales`` entry,
        in order, with ``US`` appended as the English-base fallback. The
        region is the trailing 2-letter alpha subtag (``pt-BR`` → ``BR``,
        ``zh-Hant-TW`` → ``TW``) — parsed by content, not position, so a
        script subtag (``Hant``) isn't mistaken for a region. For the
        default ``("en", "pt-BR")`` this is ``["BR", "US"]`` — same
        precedence as the old hardcoded pair.

        Note: this reuses ``supported_locales`` (a UI/metadata language
        axis) as a proxy for certification jurisdiction. They correlate but
        can diverge; if a household ever needs a UI language whose region
        should not drive ratings, add a dedicated
        ``content_rating_jurisdictions`` setting rather than overloading
        this one.
        """
        countries: list[str] = []
        for locale in self._supported_locales:
            subtags = locale.split("-")[1:]
            region = next((s.upper() for s in subtags if len(s) == 2 and s.isalpha()), None)
            if region and region not in countries:
                countries.append(region)
        if "US" not in countries:
            countries.append("US")
        return countries

    def _select_content_rating(self, ratings_by_country: dict[str, str]) -> ContentRating | None:
        """Pick the rating for the first preferred jurisdiction that has one."""
        for country in self._preferred_rating_countries():
            cert = ratings_by_country.get(country)
            if cert:
                return ContentRating(cert)
        return None

    def parse_content_rating(self, release_dates: dict[str, object]) -> ContentRating | None:
        """Extract a movie content rating from TMDB ``release_dates``.

        Builds the full per-country certification map, then selects by the
        config-driven jurisdiction order (see
        :meth:`_preferred_rating_countries`).
        """
        results = release_dates.get("results", [])
        if not isinstance(results, list):
            return None

        ratings_by_country: dict[str, str] = {}
        for entry in results:
            iso = str(entry.get("iso_3166_1", "")) if isinstance(entry, dict) else ""
            release_list = entry.get("release_dates", []) if isinstance(entry, dict) else []
            if not isinstance(release_list, list):
                continue
            for rel in release_list:
                cert = str(rel.get("certification", "")).strip() if isinstance(rel, dict) else ""
                if cert and iso not in ratings_by_country:
                    ratings_by_country[iso] = cert

        return self._select_content_rating(ratings_by_country)

    def parse_series_content_rating(
        self, content_ratings: dict[str, object]
    ) -> ContentRating | None:
        """Extract a series content rating from TMDB ``content_ratings``.

        Same config-driven jurisdiction selection as the movie path
        (:meth:`_preferred_rating_countries`).
        """
        results = content_ratings.get("results", [])
        if not isinstance(results, list):
            return None

        ratings_by_country: dict[str, str] = {}
        for entry in results:
            if not isinstance(entry, dict):
                continue
            iso = str(entry.get("iso_3166_1", ""))
            rating = str(entry.get("rating", "")).strip()
            if rating and iso not in ratings_by_country:
                ratings_by_country[iso] = rating

        return self._select_content_rating(ratings_by_country)

    def shape_collection_part(
        self,
        part: object,
    ) -> CollectionPartMetadata | None:
        """Convert a ``/collection/{id}`` ``parts`` entry to a part DTO.

        Drops any entry without a usable ``id`` + ``title`` since the
        UI cannot render those rows. Year is parsed from
        ``release_date`` when present; ``vote_average`` is forwarded
        as-is so 0.0 (TMDB's "no rating yet" signal) reaches the use
        case which can decide to hide the star.
        """
        if not isinstance(part, dict):
            return None
        raw_id = part.get("id")
        title = part.get("title") or part.get("original_title")
        if not isinstance(raw_id, int) or not isinstance(title, str) or not title:
            return None

        year: int | None = None
        release_date = part.get("release_date")
        if isinstance(release_date, str) and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except ValueError:
                year = None

        rating: float | None = None
        vote = part.get("vote_average")
        if isinstance(vote, int | float) and vote > 0:
            rating = float(vote)

        return CollectionPartMetadata(
            tmdb_id=raw_id,
            title=title,
            year=year,
            synopsis=str(part.get("overview")) if part.get("overview") else None,
            poster_url=self.image_url(
                str(part.get("poster_path")) if part.get("poster_path") else None,
            ),
            backdrop_url=self.image_url(
                str(part.get("backdrop_path")) if part.get("backdrop_path") else None,
            ),
            rating=rating,
        )

    def shape_collection_detail(self, data: dict[str, Any]) -> CollectionDetailMetadata | None:
        """Shape a ``/collection/{id}`` payload for the Collection Detail UI.

        Returns ``None`` when the payload lacks a usable ``id`` + ``name``.
        Each member ``parts`` entry is mapped via
        :meth:`shape_collection_part`; unrenderable ones are dropped.
        """
        raw_id = data.get("id")
        name = data.get("name")
        if not isinstance(raw_id, int) or not isinstance(name, str):
            return None

        parts_raw = data.get("parts") or []
        parts: list[CollectionPartMetadata] = []
        if isinstance(parts_raw, list):
            for part in parts_raw:
                shaped = self.shape_collection_part(part)
                if shaped is not None:
                    parts.append(shaped)

        return CollectionDetailMetadata(
            tmdb_id=raw_id,
            name=name,
            overview=str(data.get("overview")) if data.get("overview") else None,
            poster_url=self.image_url(
                str(data.get("poster_path")) if data.get("poster_path") else None,
            ),
            backdrop_url=self.image_url(
                str(data.get("backdrop_path")) if data.get("backdrop_path") else None,
            ),
            parts=parts,
        )

    def shape_movie_metadata(
        self,
        data: dict[str, Any],
        language: str,
        collection: CollectionMetadata | None,
    ) -> MediaMetadata:
        """Shape a full ``/movie/{id}`` details payload into ``MediaMetadata``.

        ``collection`` is resolved by the caller (an extra HTTP fetch)
        and injected here so this method stays pure.
        """
        year = None
        if data.get("release_date"):
            year = int(data["release_date"][:4])

        credits = data.get("credits", {})
        cast = self.parse_cast(credits.get("cast", []))
        directors, writers = self.parse_crew(credits.get("crew", []))
        content_rating = self.parse_content_rating(data.get("release_dates", {}))
        trailer_url = self.parse_trailer(data.get("videos", {}))

        logo_url = self.pick_best_logo_url(data.get("images", {}).get("logos"), language)
        return MediaMetadata(
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=year,
            duration_seconds=(data.get("runtime") or 0) * 60,
            synopsis=data.get("overview"),
            tagline=data.get("tagline") or None,
            poster_url=self.image_url(data.get("poster_path")),
            backdrop_url=self.image_url(data.get("backdrop_path")),
            logo_url=logo_url,
            genres=[g["name"] for g in data.get("genres", [])],
            tmdb_id=data["id"],
            imdb_id=data.get("imdb_id"),
            cast=cast,
            directors=directors,
            writers=writers,
            content_rating=content_rating.value if content_rating else None,
            trailer_url=trailer_url,
            collection=collection,
        )

    def shape_series_metadata(
        self,
        data: dict[str, Any],
        seasons: list[SeasonMetadata],
    ) -> MediaMetadata:
        """Shape a full ``/tv/{id}`` details payload into ``MediaMetadata``.

        ``seasons`` are fetched by the caller (one HTTP call per season)
        and injected here so this method stays pure.
        """
        # Top-billed cast comes back nested under ``credits.cast`` thanks
        # to the ``credits`` append. Reuse the same parser the movie path
        # uses so series and movies share the cap/order rules.
        credits = data.get("credits", {})
        cast = self.parse_cast(credits.get("cast", []))

        start_year = None
        if data.get("first_air_date"):
            start_year = int(data["first_air_date"][:4])

        end_year = None
        if data.get("last_air_date") and data.get("status") == "Ended":
            end_year = int(data["last_air_date"][:4])

        content_rating = self.parse_series_content_rating(
            data.get("content_ratings", {}),
        )

        logo_url = self.pick_best_logo_url(data.get("images", {}).get("logos"), "en")
        return MediaMetadata(
            title=data.get("name", ""),
            original_title=data.get("original_name"),
            year=start_year,
            end_year=end_year,
            synopsis=data.get("overview"),
            poster_url=self.image_url(data.get("poster_path")),
            backdrop_url=self.image_url(data.get("backdrop_path")),
            logo_url=logo_url,
            genres=[g["name"] for g in data.get("genres", [])],
            cast=cast,
            tmdb_id=data["id"],
            imdb_id=data.get("external_ids", {}).get("imdb_id"),
            content_rating=content_rating.value if content_rating else None,
            trailer_url=self.parse_trailer(data.get("videos", {})),
            seasons=seasons,
        )

    def shape_season(
        self,
        season_number: int,
        base: dict[str, Any],
        loc_payloads: dict[str, dict[str, Any]],
    ) -> SeasonMetadata:
        """Shape a season base payload + per-locale overlays into ``SeasonMetadata``.

        ``base`` is the English season payload; ``loc_payloads`` maps each
        BCP-47 locale to its (already-fetched) season payload. Both are
        retrieved by the caller so this method stays pure.
        """
        episodes = [
            EpisodeMetadata(
                season_number=season_number,
                episode_number=ep.get("episode_number", 0),
                title=ep.get("name"),
                synopsis=ep.get("overview"),
                air_date=ep.get("air_date"),
                duration_seconds=(ep.get("runtime") or 0) * 60,
                still_url=self.image_url(ep.get("still_path")),
                localized=self._episode_localized(ep.get("episode_number", 0), loc_payloads),
            )
            for ep in base.get("episodes", [])
        ]

        return SeasonMetadata(
            season_number=season_number,
            title=base.get("name"),
            synopsis=base.get("overview"),
            poster_url=self.image_url(base.get("poster_path")),
            air_date=base.get("air_date"),
            episodes=episodes,
            localized=self._text_localized(loc_payloads),
        )

    @staticmethod
    def _episode_localized(
        episode_number: int, loc_payloads: dict[str, dict[str, Any]]
    ) -> dict[str, LocalizedTextFields]:
        """Build per-locale title/synopsis overrides for one episode."""
        localized: dict[str, LocalizedTextFields] = {}
        for locale, payload in loc_payloads.items():
            loc_ep = _episode_payload_by_number(payload, episode_number)
            if loc_ep is None:
                continue
            fields = LocalizedTextFields(title=loc_ep.get("name"), synopsis=loc_ep.get("overview"))
            if fields.title or fields.synopsis:
                localized[locale] = fields
        return localized

    @staticmethod
    def _text_localized(
        loc_payloads: dict[str, dict[str, Any]],
    ) -> dict[str, LocalizedTextFields]:
        """Build per-locale title/synopsis overrides for the season itself."""
        localized: dict[str, LocalizedTextFields] = {}
        for locale, payload in loc_payloads.items():
            fields = LocalizedTextFields(
                title=payload.get("name"), synopsis=payload.get("overview")
            )
            if fields.title or fields.synopsis:
                localized[locale] = fields
        return localized

    def shape_localized_movie_fields(self, data: dict[str, Any], locale: str) -> LocalizedFields:
        """Shape a localized ``/movie/{id}`` payload into ``LocalizedFields``."""
        return LocalizedFields(
            title=data.get("title"),
            synopsis=data.get("overview"),
            tagline=data.get("tagline") or None,
            genres=[g["name"] for g in data.get("genres", [])],
            logo_url=self.pick_best_logo_url(data.get("images", {}).get("logos"), locale),
            poster_url=self.image_url(data.get("poster_path")),
            backdrop_url=self.image_url(data.get("backdrop_path")),
        )

    def shape_localized_series_fields(self, data: dict[str, Any], locale: str) -> LocalizedFields:
        """Shape a localized ``/tv/{id}`` payload into ``LocalizedFields``."""
        return LocalizedFields(
            title=data.get("name"),
            synopsis=data.get("overview"),
            genres=[g["name"] for g in data.get("genres", [])],
            logo_url=self.pick_best_logo_url(data.get("images", {}).get("logos"), locale),
            poster_url=self.image_url(data.get("poster_path")),
            backdrop_url=self.image_url(data.get("backdrop_path")),
        )

    def shape_person(self, data: Any) -> PersonMetadata | None:
        """Shape a ``/person/{id}`` payload into ``PersonMetadata``.

        Returns ``None`` when the payload is not a dict or lacks the
        ``id`` + ``name`` the UI needs to render anything useful;
        everything else is optional polish and empty strings collapse
        to ``None``.
        """
        if not isinstance(data, dict):
            return None
        raw_id = data.get("id")
        if not isinstance(raw_id, int):
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            return None
        return PersonMetadata(
            tmdb_id=raw_id,
            name=name,
            biography=str(data.get("biography") or ""),
            birthday=str(data.get("birthday")) if data.get("birthday") else None,
            deathday=str(data.get("deathday")) if data.get("deathday") else None,
            place_of_birth=(
                str(data.get("place_of_birth")) if data.get("place_of_birth") else None
            ),
            known_for_department=(
                str(data.get("known_for_department")) if data.get("known_for_department") else None
            ),
            profile_path=self.image_url(
                str(data.get("profile_path")) if data.get("profile_path") else None
            ),
        )

    def shape_translated_titles(
        self, translations: list[dict[str, Any]], title_key: str
    ) -> dict[str, str]:
        """Map a TMDB ``/translations`` payload to the supported locales."""
        titles: dict[str, str] = {}
        for locale in self._supported_locales:
            title = _pick_translation_title(translations, locale, title_key)
            if title:
                titles[locale] = title
        return titles

    def movie_candidate(self, raw: dict[str, object]) -> SearchCandidate:
        """Shape a raw movie search/detail hit into a picker ``SearchCandidate``."""
        title = str(raw.get("title") or raw.get("original_title") or "")
        overview_raw = raw.get("overview")
        overview = str(overview_raw) if overview_raw else None
        poster = raw.get("poster_path")
        return SearchCandidate(
            tmdb_id=int(str(raw["id"])),
            media_type="movie",
            title=title,
            year=_extract_year_prefix(raw.get("release_date")),
            overview=overview,
            poster_url=self.image_url(str(poster)) if isinstance(poster, str) else None,
        )

    def series_candidate(self, raw: dict[str, object]) -> SearchCandidate:
        """Shape a raw TV search/detail hit into a picker ``SearchCandidate``."""
        title = str(raw.get("name") or raw.get("original_name") or "")
        overview_raw = raw.get("overview")
        overview = str(overview_raw) if overview_raw else None
        poster = raw.get("poster_path")
        return SearchCandidate(
            tmdb_id=int(str(raw["id"])),
            media_type="tv",
            title=title,
            year=_extract_year_prefix(raw.get("first_air_date")),
            overview=overview,
            poster_url=self.image_url(str(poster)) if isinstance(poster, str) else None,
        )


__all__ = ["TmdbResponseMapper"]
