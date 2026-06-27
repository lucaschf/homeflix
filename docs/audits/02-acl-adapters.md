# Audit 02 — ACL / Adapters / Gateways

**Scope.** Read-only audit of the boundary code in the HomeFlix backend: every
`infrastructure/acl/` adapter (cross-BC Read Port implementations per ADR-009),
the external provider gateways under `src/modules/media/infrastructure/`
(`metadata/` TMDB client, `file_system/`, `audio/`, `video/`, `streaming/`), and
a sweep of `building_blocks` / `shared_kernel` for boundary surface.

**Principles applied.** No dedicated `acl-audit` skill exists in this repo, so
findings are tagged `acl-audit (principles)` and grounded in **ADR-009**
(Cross-BC Read Ports + Anti-Corruption Layer). Hunt targets: business/domain
policy living in the adapter, provider signal discarded/collapsed/first-wins,
silently permissive defaults, missing translation (foreign type leak), and leaky
error handling.

**No source was modified.** This file is the only artifact written.

## Severity counts by module

| Module | crítico | alto | médio | baixo | Total |
|---|---|---|---|---|---|
| media (TMDB gateway) | 0 | 0 | 2 | 1 | 3 |
| media (probe / scanner) | 0 | 0 | 2 | 1 | 3 |
| collections (ACL) | 0 | 0 | 0 | 1 | 1 |
| library / watch_progress / catalog_requests / notifications | 0 | 0 | 0 | 0 | 0 (healthy) |
| building_blocks / shared_kernel | 0 | 0 | 0 | 0 | 0 (no surface) |
| **Total** | **0** | **0** | **4** | **3** | **7** |

---

## Module: media — TMDB gateway (`infrastructure/metadata/tmdb_client.py`)

### Finding 1 — Content-rating jurisdiction policy hardcoded in the gateway (+ all other countries discarded)
- **arquivo:linha**: `src/modules/media/infrastructure/metadata/tmdb_client.py:1096` and `:1153`
- **severidade**: médio
- **root cause**: The gateway decides *which jurisdiction's* content rating is
  authoritative — a product/domain policy ("Brazil's DEJUS rating preferred,
  US as fallback") — instead of translating the provider's full per-country
  rating set and letting the domain choose. It also collapses TMDB's rich
  `results[]` (one cert per country) into a single string, silently dropping
  every other country with no record of the loss. Adding a third supported
  locale would require editing this gateway, not config/domain.
- **skill + confiança**: acl-audit (principles), 0.7
- **evidence**:
  ```python
  # _parse_content_rating (movies)
  selected = ratings_by_country.get("BR") or ratings_by_country.get("US")
  return ContentRating(selected) if selected else None
  # _parse_series_content_rating (series) — same BR-then-US literal policy
  selected = ratings_by_country.get("BR") or ratings_by_country.get("US")
  ```

### Finding 2 — `get_*_summary_by_id` collapses transient/auth failures into "not found"
- **arquivo:linha**: `src/modules/media/infrastructure/metadata/tmdb_client.py:266-277` (movie) and `:279-292` (series)
- **severidade**: médio
- **root cause**: Both the `httpx.HTTPError` path and every non-200 status are
  mapped to the same `None` the method already uses for a genuine 404. A picker
  caller (admin relink) cannot distinguish "no such TMDB id" from "TMDB is down
  / API key rejected / rate-limited." This is *leaky error handling via a
  misleading domain outcome*, and it is inconsistent with the search paths in
  the same client (`search_movie`/`search_series`/`find_by_imdb_id`) which call
  `resp.raise_for_status()` and let failures surface.
- **skill + confiança**: acl-audit (principles), 0.65
- **evidence**:
  ```python
  except httpx.HTTPError:
      return None
  if resp.status_code == 404:
      return None
  if resp.status_code != 200:
      return None   # 401/429/500 indistinguishable from a true 404
  return _to_movie_candidate(resp.json(), self._image_url)
  ```

### Finding 3 — Cast list silently truncated to top 15 with no loss signal
- **arquivo:linha**: `src/modules/media/infrastructure/metadata/tmdb_client.py:27` (`_MAX_CAST = 15`), applied at `:1045-1052`
- **severidade**: baixo
- **root cause**: Provider returns the full ordered cast; the gateway flattens
  it to the first 15 with the cap hardcoded as a module constant rather than a
  configurable/domain concern, and records nothing about the truncation. A
  reasonable UI cap, but it is a provider-signal-discard decision living in the
  ACL.
- **skill + confiança**: acl-audit (principles), 0.5
- **evidence**:
  ```python
  sorted_cast = sorted(cast_data, key=lambda c: _safe_int(c.get("order"), 999))
  return [self._to_credit_person(c, role_key="character")
          for c in sorted_cast[:_MAX_CAST] if c.get("name")]
  ```

> Note (not a finding): the broad `except httpx.HTTPError: return None` /
> `status_code != 200: return None` pattern across `get_collection`,
> `get_movie_recommendations`, `_fetch_collection_movie_ids`,
> `_fetch_related_ids`, `get_person`, `get_translated_titles` is **documented and
> intentional best-effort polish** (recommendations/collections/translations are
> non-load-bearing) — accepted. The `_pick_translation_title`, `_logo_rank`, and
> `_parse_trailer` ranking functions are legitimate multi-value→single-field ACL
> translation, not domain policy.

---

## Module: media — probe & scanner

### Finding 4 — Probe fabricates an audio-default disposition the container never declared (first-wins)
- **arquivo:linha**: `src/modules/media/infrastructure/streaming/media_probe_service.py:403-405`
- **severidade**: médio
- **root cause**: When the source file declares *no* default audio stream, the
  probe adapter invents one by forcing `tracks[0]` to default. "Which audio is
  the default" is a selection concern the Library BC already owns
  (`TrackSelector`, ADR-005); manufacturing a provider signal that did not
  exist, and doing it first-wins, lets an arbitrary first track masquerade as an
  authoritative default downstream. The loss of "the file had no default" is
  not preserved.
- **skill + confiança**: acl-audit (principles), 0.6
- **evidence**:
  ```python
  # Ensure at least one track is default
  if tracks and not any(t.is_default for t in tracks):
      tracks[0] = tracks[0].with_updates(is_default=True)
  ```

### Finding 5 — Scanner silently treats a missing/unmounted directory as "empty"
- **arquivo:linha**: `src/modules/media/infrastructure/file_system/scanner.py:160-161`
- **severidade**: médio
- **root cause**: An unmounted/missing library root is skipped with `continue`,
  so the scan returns *no files* for that root with no distinguishable signal
  from "root mounted and genuinely empty." Downstream reconciliation could
  mistake an unmounted disk for "all media deleted." Partially mitigated by
  `LibraryHealthAdapter.is_library_root_accessible` (which deliberately returns
  `False` on partial mount to avoid trusting file-missing signals), but the
  scanner gateway itself is silently permissive.
- **skill + confiança**: acl-audit (principles), 0.55
- **evidence**:
  ```python
  dir_path = Path(directory.value)
  if not dir_path.is_dir():
      continue   # unmounted root == empty scan, no signal raised
  ```

### Finding 6 — Probe permissive defaults for missing stream metadata
- **arquivo:linha**: `src/modules/media/infrastructure/streaming/media_probe_service.py:373` (channels→2) and `:349-357` (unknown language→`"un"`)
- **severidade**: baixo
- **root cause**: A missing `channels` field defaults to stereo (2), and any
  3-letter ISO code not in the map (or an out-of-shape tag) collapses to `"un"`.
  Both are silent guesses that the provider data didn't supply; reasonable
  fallbacks but they erase the "unknown" distinction.
- **skill + confiança**: acl-audit (principles), 0.45
- **evidence**:
  ```python
  channels = int(stream.get("channels", 2))
  ...
  mapped = _ISO639_2_TO_1.get(lang)
  if mapped is None:
      return "un"
  ```

---

## Module: collections — ACL (`infrastructure/acl/media_lookup_adapter.py`)

### Finding 7 — Series quality fields (runtime/resolution/HDR) dropped to null in batch lookup
- **arquivo:linha**: `src/modules/collections/infrastructure/acl/media_lookup_adapter.py:56-66`
- **severidade**: baixo
- **root cause**: The batch series resolution leaves `runtime_seconds`,
  `resolution`, and `hdr` null because the batch loader doesn't hydrate
  episodes — a provider-signal-collapse the movie branch (same method) does fill
  in. Documented and the client hides absent fields, so this is an accepted
  asymmetry, flagged for visibility rather than as a defect.
- **skill + confiança**: acl-audit (principles), 0.4
- **evidence**:
  ```python
  # Runtime/resolution/HDR live on the series' episodes,
  # which the batch lookup doesn't hydrate — left null
  result[(MediaType.SERIES, media_id)] = MediaSummary(
      media_id=media_id, media_type=MediaType.SERIES,
      title=series.get_title(lang), poster_path=series.get_poster_path(lang),
      year=series.start_year.value, genres=tuple(series.get_genres(lang)),
  )
  ```

---

## Healthy notes

- **ADR-009 structure is followed faithfully.** Every cross-BC adapter is the
  *single* file importing the provider BC, returns a consumer-owned DTO/VO (no
  foreign aggregate leaks), and exposes a batch shape where needed
  (`MediaLookupAdapter.get_many`, `CatalogRequestLookupAdapter.get_for_movie_tmdb_ids`,
  `ProgressLookupAdapter.find_for_media_ids`). No raw provider repository or
  entity escapes upward.
- **Permissive defaults are deliberate and consistent where they matter.**
  `ProfileLibraryAccessAdapter.find_for_profile` returns `[]` (deny-all) for a
  missing profile, and the consumer use cases short-circuit on the empty list
  (`get_movie_by_id.py:75-76`) while repositories translate an empty allow-list
  to `IN ()` = match-nothing — so the "missing data → denied" semantics are
  end-to-end correct, not accidentally permissive.
- **`LibraryHealthAdapter`** correctly fails *closed*: missing library and
  partial mount both return `False` with an explicit rationale, exactly the
  safe direction for a file-missing signal.
- **Detection gateways are clean ACLs, not policy holders.** `CreditsDetector`,
  `ChromaprintCorrelator`, and the frame-hash detectors hold only the
  algorithm (per ADR-020/021's pluggable-port design); thresholds arrive as
  injected `*Tuning` from runtime settings (ADR-013) and the final
  `min_confidence` gate is applied by the orchestrating job, not the detector.
  They honestly return `None` ("no intro/credits found") rather than guessing.
- **`NotificationPublisherAdapter`** keeps all per-kind copy/payload shaping on
  the notifications side and accepts only a typed DTO; `body=None` is a
  documented frontend-fallback choice, not a swallowed value.
- **`building_blocks` / `shared_kernel`** expose no boundary-adapter surface
  (`building_blocks/infrastructure/` holds only the generic event bus + UoW), so
  there is nothing to anti-corrupt there.
