# HomeFlix — Plano de Remediação Faseado (PRs)

**Data:** 2026-06-27 · **Base:** achados de [`00-executive-summary.md`](00-executive-summary.md)
e dos 5 relatórios por dimensão (01–05). **Modo do plano:** proposta — nenhum
código foi alterado.

Este plano ataca **todos os ~40 defeitos raiz distintos** identificados, na ordem
recomendada pelo sumário executivo (barato→estrutural→cleanup). Cada PR é
independentemente revisável e mergeável.

## Como ler

Cada card de PR traz: **título** (Conventional Commits), **escopo**, **achados
cobertos** (id do relatório de origem), **arquivos-chave**, **migration?**, **ADR?**,
**esforço**, **depende de**. Severidade herda do relatório de origem.

> **Regra de workflow (CLAUDE.md):** cada PR sai de um branch novo a partir de
> `origin/develop` (`git checkout -b <type>/<slug> origin/develop`). Sem menções a
> IA em commits/PRs/código. PR com `## Summary` + `## Test plan`.

## Sequência global

```
FASE 1  Docs (baixo risco, alta alavancagem)         ── PR-D1..D4   [paralelizável]
FASE 2  LocalizedMetadata VO + ADR  (CRÍTICO)         ── PR-2.1..2.3 [base p/ Fase 4 e 5]
FASE 3  Mecanismo de integração cross-BC             ── PR-3.1..3.5 [faseável; epicentro media]
FASE 4  Gateways de provider + MetadataReconciler     ── PR-4.1..4.4 [4.4 depende de Fase 2]
FASE 5  Primitive Obsession de idioma (resto)         ── PR-5.1      [depende de Fase 2]
FASE 6  Cleanup de modelagem (médios/baixos)          ── PR-6.1..6.11 [independentes entre si]
```

**Dependências duras:** Fase 4 (PR-4.4 reconciler) e Fase 5 consomem o VO da Fase 2.
O resto é majoritariamente independente e pode ser paralelizado por revisor.

> ⚠️ **Recomendação de reordenação:** **PR-6.2** (`with_updates` muta a fonte →
> **perda silenciosa de domain events**) é o único achado "cleanup" que é um bug
> latente de corrupção, não estética. Sugiro **puxá-lo para logo após a Fase 1**,
> antes da Fase 3 (que vai mexer pesado em event handlers).

---

## FASE 1 — Documentação (Tema D)

Sem risco de runtime, evita que novos PRs herdem doc errada. Os quatro são
independentes; podem virar um único PR `docs:` se preferir.

### PR-D1 · `docs(standards): align response envelope and pagination placement`
- **Escopo:** corrigir o "API Response Standard (resumo)" do CLAUDE.md para o
  envelope real (`type` obrigatório, chave `metadata` não `meta`, `request_id` no
  header `X-Request-Id`, não no corpo). Anotar no `api-response-standard-rest-v3.md`
  a divergência atual de paginação (aninhada em `metadata`, não top-level).
- **Achados:** doc-drift 🔴 #1 (envelope) + 🟡 (pagination v3 vs código).
- **Arquivos:** `.claude/CLAUDE.md` (seção API Response Standard);
  `docs/standards/api-response-standard-rest-v3.md:51-68`. Referência real:
  `src/building_blocks/presentation/responses.py:73,101`.
- **Migration?** Não. **ADR?** Não. **Esforço:** XS.

### PR-D2 · `docs: realign i18n docs with localized-field model`
- **Escopo:** reescrever o checklist #8 do CLAUDE.md (remover `i18n/locales/{en,pt-BR}/`
  inexistente) e o `api-i18n-guide.md` para o modelo real: query param `lang` +
  `entity.get_title(lang)` + `supported_locales` config-driven; remover descrição de
  message-catalogs JSON + Accept-Language não usada.
- **Achados:** doc-drift 🟠 (i18n catálogo) + 🟡 (api-i18n-guide obsoleto).
- **Arquivos:** `.claude/CLAUDE.md` (checklist #8);
  `docs/standards/api-i18n-guide.md:32-58,68-73,175-201`. Referência:
  `src/config/settings.py:176`, `movie_routes.py:58`.
- **Migration?** Não. **ADR?** Não (o ADR da localização é a Fase 2). **Esforço:** S.

### PR-D3 · `docs(standards): mark PresentationException layer as not implemented`
- **Escopo:** marcar a seção `PresentationException` (e subclasses) como
  "aspiracional / não implementada" ou removê-la até existir o módulo.
- **Achados:** doc-drift 🟠 (PresentationException ausente).
- **Arquivos:** `docs/standards/exception-hierarchy-clean-architecture.md:128,867-943`.
  Verificação: `grep -rn PresentationException src/` → zero.
- **Migration?** Não. **ADR?** Não. **Esforço:** XS.

### PR-D4 · `docs: refresh module inventory and project counters`
- **Escopo:** atualizar o tree de `src/modules/` e a lista de Bounded Contexts do
  CLAUDE.md (4→9: incluir `catalog_requests`, `identity`, `notifications`,
  `preferences`, `settings`); atualizar contagens (107/112→~132 endpoints;
  2530/2660→~2941 testes); nota de revisão na ADR-008 (snapshot histórico + eventos
  ficam no domínio de cada BC); registrar `notifications`/`preferences` como
  deliberadamente sem ADR (ou abrir ADR curto p/ notifications transport).
- **Achados:** doc-drift 🟡 (módulos 4 vs 9), 🟡 (contagens), 🔵 (ADR-008 tree),
  🔵 (notifications/preferences sem ADR).
- **Arquivos:** `.claude/CLAUDE.md` (Estrutura, Bounded Contexts, Fase Atual);
  `docs/roadmap.md:69,114`; `docs/adr/ADR-008-screaming-architecture.md` (nota).
- **Migration?** Não. **ADR?** Opcional (notifications). **Esforço:** S.

---

## FASE 2 — `LocalizedMetadata` Value Object + ADR (Tema B · CRÍTICO)

Estanca a corrupção silenciosa ativa (chave mágica que não faz round-trip; tagline
já foi perdida). Base para Fases 4 e 5.

### PR-2.1 · `docs(adr): ADR-023 localized metadata as value object`
- **Escopo:** ADR registrando (a) a iniciativa de localização config-driven (que hoje
  não tem ADR) e (b) a decisão "metadados localizados como VO `LocalizedMetadata`
  chaveado por `LanguageTag`, serializado só na borda de persistência". Usar a skill
  `adr-writer`.
- **Achados:** code-smell CRÍTICO (contexto) + doc-drift 🟡 (localização sem ADR).
- **Arquivos:** `docs/adr/ADR-023-localized-metadata-value-object.md` (novo).
- **Migration?** Não. **ADR?** É o ADR. **Esforço:** S. **Depende de:** —

### PR-2.2 · `feat(media): introduce LocalizedMetadata value object (read path)`
- **Escopo:** criar o VO `LocalizedMetadata` (registro por-locale tipado, chaveado por
  `LanguageTag`, com `get(field, lang)` e fallback centralizado) e `merge(other,
  policy)`. Trocar os ~24 acessores `str(loc.get("title") or ...)` das 4 entidades
  para ler via VO. **Manter a serialização JSON idêntica** na borda de persistência
  (mesmo shape no disco) para não exigir migration. Tipar `lang` desses acessores como
  `LanguageTag` (coagindo a string crua uma vez).
- **Achados:** code-smell 🔴 (dict localizado) + 🟠 (lang:str nos acessores de entidade).
- **Arquivos:** `src/modules/media/domain/value_objects/` (novo VO);
  `domain/entities/{movie.py:95,131-180, series.py:78,106-150, episode.py:67,95-100,
  season.py:57,139-146}`; mapper/persistence boundary.
- **Migration?** **Não** (wire JSON preservado) — verificar round-trip do
  `json_extract(localized, lang)` em teste de integração. **ADR?** PR-2.1. **Esforço:**
  G. **Depende de:** PR-2.1.

### PR-2.3 · `refactor(media): write localized metadata through the VO on enrich`
- **Escopo:** caminho de escrita do enrich passa a montar/gravar via `LocalizedMetadata`
  em vez de achatar para dict aninhado em `_localized_metadata_helpers`. Remove a chance
  de divergência de chave entre as variantes movie/series.
- **Achados:** code-smell 🔴 (mesmo defeito, lado escrita).
- **Arquivos:** `enrich_movie_metadata.py:344`, `enrich_series_metadata.py:260`,
  `_localized_metadata_helpers.py:15-101`.
- **Migration?** Não. **Esforço:** M. **Depende de:** PR-2.2. **Nota:** prepara o terreno
  para o `MetadataReconciler` da Fase 4.

---

## FASE 3 — Mecanismo de integração cross-BC (Tema A)

Maior alavanca estrutural. Epicentro `media`. Faseável em 5 PRs ortogonais.

### PR-3.1 · `feat(shared_kernel): materialize integration events package`
- **Escopo:** criar os contratos de integration event versionados/estáveis em
  `shared_kernel/integration_events/` (hoje vazio) para os ~4 eventos cross-BC
  (`MovieMerged`, `MoviePromotedToSeries`, `MediaEnriched`, `UserDeleted`). Publicar a
  partir do produtor; consumidores deixam de importar `*.domain.events`.
- **Achados:** clean-arch M-8/M-9 · coupling F3 (🟠) · doc-drift 🟠 (regra "módulos não
  importam entre si").
- **Arquivos:** `src/shared_kernel/integration_events/` (popular);
  `media/domain/events.py`, `identity/domain/events.py` (publicar integration event);
  `watch_progress|collections|catalog_requests/.../event_handlers/*.py` (consumir o
  contrato). Atualizar ADR-008/009 (nota sobre integration events reais).
- **Migration?** Não. **ADR?** Nota em ADR-008/009. **Esforço:** G. **Depende de:** —
  (mas coordenar com PR-6.2 se reordenado, pois mexe em handlers).

### PR-3.2 · `refactor(media): replace cross-BC UoW shortcuts with read ports`
- **Escopo:** criar `IdentityUserCountPort` e `LibraryLookupPort` (ports locais em
  `media/application/ports/`) + adapters ACL em `media/infrastructure/acl/` retornando
  DTOs próprios; usar nos use cases que hoje pegam a UoW alheia.
- **Achados:** clean-arch A-2/A-3 (🟠) · coupling F2 (🟠).
- **Arquivos:** `media/application/use_cases/get_overview_stats.py:3`,
  `trigger_scan.py:6`, `presentation/routes/scan_routes.py:13`; novos ports + adapters.
- **Migration?** Não. **Esforço:** M. **Depende de:** —

### PR-3.3 · `refactor(media): pass library data as DTO into scan, not the aggregate`
- **Escopo:** `scan_run_service.run_scan(...)` deixa de receber o aggregate `Library`
  de outro BC; recebe um DTO local (via `LibraryLookupPort` da PR-3.2). Elimina o
  acoplamento *intrusive* mais grave da base.
- **Achados:** clean-arch A-1 · coupling **F1 (🔴 CRÍTICO)** · doc-drift 🟠.
- **Arquivos:** `media/application/services/scan_run_service.py:21,86`.
- **Migration?** Não. **Esforço:** M. **Depende de:** PR-3.2 (reusa a port/DTO).

### PR-3.4 · `refactor(identity): expose AuthenticatedUser DTO to route boundaries`
- **Escopo:** o crosscut de auth passa a tipar o usuário injetado como um DTO
  `AuthenticatedUser` (publicado pelo `identity`), não o ORM `UserModel`. Atualizar os
  ~20 sites de rotas em 5 módulos.
- **Achados:** clean-arch M-7 (🟡 sistêmico) · coupling F5 (🟡).
- **Arquivos:** `identity/.../auth.py` (retorno DTO);
  `media/presentation/routes/*` (~14), `library/.../library_routes.py:12`,
  `catalog_requests`, `notifications`, `settings` routes.
- **Migration?** Não. **Esforço:** M (mecânico, amplo). **Depende de:** —

### PR-3.5 · `refactor(media): introduce config ports for runtime settings`
- **Escopo:** substituir os imports concretos de `settings.RuntimeSettings`/VOs por
  Protocols/ports de config locais (ex.: `StreamingConfigPort`, `ScanDedupConfigPort`)
  injetados no composition root. Inclui o site `identity` (F6).
- **Achados:** clean-arch M-5/M-6 · coupling F4 (🟠) + F6 (🟡).
- **Arquivos:** `media/infrastructure/streaming/{hls_service.py:68,
  thumbnail_service.py:36,scrub_preview_locator.py:18}`, `audio/audio_extractor.py:32`,
  `video/{credits_detector.py:47,frame_hasher.py:30}`,
  `application/use_cases/detect_movie_conflicts.py:32-33`;
  `identity/.../local_avatar_storage.py:32`.
- **Migration?** Não. **Esforço:** M. **Depende de:** —

---

## FASE 4 — Gateways de provider + `MetadataReconciler` (Temas C + E)

### PR-4.1 · `fix(media): distinguish provider failure from not-found in TMDB lookups`
- **Escopo:** `get_*_summary_by_id` para de colapsar `HTTPError`/não-200 no mesmo `None`
  de um 404 real; alinhar ao comportamento dos paths de search (`raise_for_status`).
  Caller (relink admin) passa a distinguir "id inexistente" de "TMDB fora/auth/rate".
- **Achados:** ACL Finding 2 (🟡).
- **Arquivos:** `media/infrastructure/metadata/tmdb_client.py:266-292`.
- **Migration?** Não. **Esforço:** S.

### PR-4.2 · `refactor(media): move content-rating jurisdiction policy out of the gateway`
- **Escopo:** o gateway TMDB passa a **traduzir o conjunto completo** de ratings por
  país; a escolha de jurisdição (hoje `BR or US` hardcoded) vira política
  domínio/config (alinha com `supported_locales` da Fase 2). Para de descartar
  silenciosamente os demais países.
- **Achados:** ACL Finding 1 (🟡).
- **Arquivos:** `media/infrastructure/metadata/tmdb_client.py:1096,1153`.
- **Migration?** Não (se o campo persistido continuar `ContentRating` único; a escolha
  muda de lugar). **Esforço:** M.

### PR-4.3 · `fix(media): preserve "no default audio / unmounted root" signals`
- **Escopo:** (a) probe deixa de fabricar `tracks[0].is_default=True` quando o container
  não declara default — preserva "sem default" e deixa a seleção para o `TrackSelector`
  da Library; (b) scanner distingue raiz desmontada/ausente de raiz vazia (sinal
  explícito, não `continue` silencioso); (c) opcional: tornar explícitos os defaults
  `channels→2` / `lang→"un"`.
- **Achados:** ACL Finding 4 + 5 (🟡), Finding 6 (🔵).
- **Arquivos:** `media/infrastructure/streaming/media_probe_service.py:403-405,373,349-357`;
  `media/infrastructure/file_system/scanner.py:160-161`.
- **Migration?** Não. **Esforço:** M.

### PR-4.4 · `refactor(media): extract MetadataReconciler domain service + MergePolicy`
- **Escopo:** mover a regra "provider ⇄ entidade" (`if meta_val and (force or not
  entity_val)`), hoje copiada ~23× nos use cases, para um domain service
  `MetadataReconciler` (ou `entity.merged_with(metadata, policy)`); substituir o
  `force: bool` plumbado por ~12 funções por `MergePolicy.FILL_IF_EMPTY | OVERWRITE`.
  Usa o `LocalizedMetadata.merge()` da Fase 2.
- **Achados:** code-smell 🟠 (anemic+shotgun, reconciler) + 🟠 (force boolean blindness).
- **Arquivos:** `enrich_movie_metadata.py:236-345`, `enrich_series_metadata.py:165-480`,
  `_localized_metadata_helpers.py:15-101`; novo domain service em
  `media/domain/services/`.
- **Migration?** Não. **Esforço:** G. **Depende de:** PR-2.2/2.3.

### PR-4.5 (opcional) · `chore(media): make cast truncation configurable`
- **Escopo:** `_MAX_CAST = 15` hardcoded vira config; registrar/logar a truncagem.
- **Achados:** ACL Finding 3 (🔵). **Esforço:** XS. **Pode virar won't-fix** se 15 for OK.

---

## FASE 5 — Primitive Obsession de idioma (resto do Tema F)

### PR-5.1 · `refactor(media): accept LanguageTag across read-path use cases`
- **Escopo:** estender o `LanguageTag` (introduzido na Fase 2) ao caminho de leitura
  restante — os ~14 use cases/helpers de summary que ainda recebem `lang: str = "en"`
  cru; parsear a string crua uma vez na presentation.
- **Achados:** code-smell 🔵 (lang:str read-path) — mesma raiz do 🟠 da Fase 2.
- **Arquivos:** `_movie_summary_helpers.py:14`, `_series_summary_helpers.py`,
  `list_by_genre.py`, `search_catalog.py` (~14 arquivos).
- **Migration?** Não. **Esforço:** M. **Depende de:** PR-2.2.

---

## FASE 6 — Cleanup de modelagem (médios/baixos)

PRs pequenos e independentes entre si. Ordem livre; ver recomendação de puxar PR-6.2.

### PR-6.1 · `refactor(building_blocks): move repository/domain contracts to domain layer`
- **Escopo:** reclassificar `PaginatedResult` (e bases de exceção de domínio) de
  `building_blocks/application` → `building_blocks/domain`, eliminando a direção
  invertida domínio→application nas interfaces de repositório.
- **Achados:** clean-arch M-4 + B-11 (🔵).
- **Arquivos:** `building_blocks/application/pagination.py`,
  `domain/repositories/{movie_repository.py:7,series_repository.py:7,
  media_conflict_repository.py:5}`. **Esforço:** S.

### PR-6.2 · `fix(building_blocks): make aggregate event hand-off explicit` ⚠️ prioridade
- **Escopo:** `AggregateRoot.with_updates` deixa de **mutar a fonte** (`self._events.clear()`)
  — hand-off de eventos explícito (coletor puxado no save) ou contrato return-only. Hoje
  qualquer `old.pull_events()` após `with_updates` retorna vazio → **domain events
  perdidos em silêncio** (dirigem persistência/integração). Bug latente, não estética.
- **Achados:** code-smell 🟡 (temporal coupling / mutação surpresa).
- **Arquivos:** `building_blocks/domain/entity.py:104-115`. **Esforço:** M.
  **Recomendação:** mergear logo após a Fase 1, antes da Fase 3.

### PR-6.3 · `refactor(media): introduce Confidence value object [0,1]`
- **Escopo:** VO `Confidence` (valida `[0,1]`) reusado em `IntroMarker`/`CreditsMarker`
  e em `EpisodeDetectionResult`/`min_confidence` (hoje `float` irrestrito); de quebra,
  unificar segundos `int` vs `float` entre markers e `EpisodeDetectionResult`.
- **Achados:** code-smell 🟡 (Confidence) + 🔵 (int/float seconds).
- **Arquivos:** `intro_detection_run.py:42-43,85`, `intro_marker.py:51-52`,
  `credits_marker.py:52`. **Esforço:** M.

### PR-6.4 · `refactor(media): ConflictCandidate parameter object`
- **Escopo:** par `(candidate_*_id, candidate_*_type)` vira VO `ConflictCandidate(id,
  type)` em `MediaConflict.detect/resolve/loser_id`.
- **Achados:** code-smell 🟡 (data clump + primitive obsession).
- **Arquivos:** `media/domain/entities/media_conflict.py:111-114,122`. **Esforço:** S.

### PR-6.5 · `refactor(media): tidy scanner domain modeling`
- **Escopo:** cluster de smells do scan: `ScanRun.summary` dict→VOs contadores tipados
  (`ScanCounters`/`EnrichCounters`); `Resolution.UNKNOWN` + `is_unknown()` em vez do
  literal `"Unknown"`; parameter object `VariantGroup` para o par `(paths, by_path)`;
  mover upsert para `Season.with_episode_upserted`/`Series.with_season_upserted`.
- **Achados:** code-smell 🟡 (ScanRun.summary, "Unknown" sentinel, (paths,by_path) clump,
  feature-envy upsert).
- **Arquivos:** `scan_run.py:85,105,114`, `scan_media_directories.py:180,203,261-354,
  554-575`. **Migration?** Não (summary continua JSON). **Esforço:** M-G. *(pode dividir
  em 2 PRs: counters/Unknown vs VariantGroup/upsert.)*

### PR-6.6 · `fix(media): single validated path for intro/credits marker persistence`
- **Escopo:** remover o temporal coupling em que a validação `with_*_marker` é chamada só
  pelo efeito e a cópia validada é **descartada** antes do update direto de coluna; o
  repositório passa a receber a entidade/marker validado (caminho único).
- **Achados:** code-smell 🟡 (temporal coupling).
- **Arquivos:** `set_episode_intro.py:87`, `set_credits_marker.py:70`. **Esforço:** S.

### PR-6.7 · `refactor(collections): derive list item_count from items`
- **Escopo:** eliminar o contador denormalizado `item_count` que drifta dos itens reais
  (duas chamadas coordenadas hoje); derivar via `COUNT`/agregado dono, ou unir
  add-item+bump num único método. A invariante `MAX_ITEMS` passa a checar a verdade.
- **Achados:** code-smell 🟡 (temporal coupling / invariante denormalizada).
- **Arquivos:** `custom_list.py:117,196-219`, `add_item_to_custom_list.py:42-53`,
  `remove_item_from_custom_list.py:24-31`. **Migration?** Talvez (se a coluna
  `item_count` for removida) — avaliar. **Esforço:** M.

### PR-6.8 · `refactor(library): typed request models + CronExpression VO`
- **Escopo:** `metadata_providers`/`settings` na borda da aplicação deixam de ser
  `list[dict[str,Any]]`/`dict[str,Any]` e passam a usar o VO `MetadataProviderConfig`
  (já existe) / sub-models de request tipados, convertidos uma vez na borda; VO
  `CronExpression` validando faixas reais para `scan_schedule`.
- **Achados:** code-smell 🟡 (library list[dict]) + 🔵 (scan_schedule cron).
- **Arquivos:** `update_library.py:71-79`, `library_dtos.py:60-62,81-83`,
  `create_library._build_settings`, `library.py:66-69`. **Esforço:** M.

### PR-6.9 · `refactor(shared_kernel): centralize episode composite id format`
- **Escopo:** centralizar o formato `epi_ser_{id}_{S}_{E}` junto de `parse_media_id`
  (hoje duplicado por cirurgia de string); tipar `series_id` como `SeriesId`; distinguir
  "não-episódio" de "malformado" (em vez de `None` para ambos). Opcional: enum
  `SubtitleFormat` para `tracks.format`.
- **Achados:** code-smell 🟡 (episode_composite_id) + 🔵 (codec/format str).
- **Arquivos:** `shared_kernel/value_objects/episode_composite_id.py:31-83`,
  `media_id.py`, `tracks.py:54,119`. **Esforço:** M.

### PR-6.10 · `refactor(watch_progress): model subtitle preference explicitly`
- **Escopo:** substituir o sentinela sobrecarregado `subtitle_track: int | None`
  (`None`=no-op, `-1`=off, só no docstring) por um modelo explícito (`Off | Track(index)`)
  ou separar "clear" de "set".
- **Achados:** code-smell 🔵 (magic value / sentinel overload).
- **Arquivos:** `watch_progress.py:64-65,112-113`. **Esforço:** S.

### PR-6.11 · `refactor(presentation): formalize resolve_profile_id as identity contract`
- **Escopo:** o helper de presentation `resolve_profile_id` é reusado por 4 módulos via
  import direto cross-BC; promover a contrato de presentation publicado do `identity`
  (ou documentar como API pública estável).
- **Achados:** clean-arch B-9/B-10 (🔵) · coupling F9 (🔵).
- **Arquivos:** `identity/presentation/dependencies.py`;
  `media|collections|watch_progress|preferences/presentation/dependencies.py:10-11`.
  **Esforço:** S.

---

## Itens sem PR (vigiar / decisão consciente)

| Item | Origem | Decisão sugerida |
|---|---|---|
| `shared_kernel` acumulando VOs de id per-BC (`MovieId`…) | coupling F8 (🟡) | **Vigiar em review.** Aliviado naturalmente pela PR-3.1 (integration events tipados); não promover modelos de domínio ao shared kernel. |
| Inversões de port (provedor implementa port do consumidor) | coupling F10 (🔵) | **Sem ação** — é o melhor caso de Strength (contrato). |
| `directors`/`writers: list[str]` vs `cast: list[CastMember]` | code-smell 🔵 | **Won't-fix** salvo se navegação por crew for desejada → VO `CrewMember`. |
| `collections` ACL: campos quality da série nulos no batch | ACL Finding 7 (🔵) | **Aceito/documentado** (cliente esconde campos ausentes); rever só se a UI precisar. |
| `library_id: str` cru nas entidades | code-smell 🔵 | **Adiado** (território de arquitetura/ADR-008); reavaliar com a Fase 3. |

---

## Matriz de cobertura (achado → PR)

| Relatório | Achado | Sev | PR |
|---|---|---|---|
| 01 clean-arch | A-1 (Library aggregate) | 🟠 | PR-3.3 |
| 01 | A-2 / A-3 (UoW alheia) | 🟠 | PR-3.2 |
| 01 | M-4 (PaginatedResult na app) | 🟡 | PR-6.1 |
| 01 | M-5 / M-6 (settings type-coupling) | 🟡 | PR-3.5 |
| 01 | M-7 (UserModel em rotas) | 🟡 | PR-3.4 |
| 01 | M-8 / M-9 (domain events crus) | 🟡 | PR-3.1 |
| 01 | B-9 / B-10 (presentation→presentation) | 🔵 | PR-6.11 |
| 01 | B-11 (contratos na app layer) | 🔵 | PR-6.1 |
| 02 ACL | Finding 1 (rating jurisdiction) | 🟡 | PR-4.2 |
| 02 | Finding 2 (erro→not-found) | 🟡 | PR-4.1 |
| 02 | Finding 3 (cast truncado) | 🔵 | PR-4.5 |
| 02 | Finding 4 (audio default fabricado) | 🟡 | PR-4.3 |
| 02 | Finding 5 (raiz desmontada silenciosa) | 🟡 | PR-4.3 |
| 02 | Finding 6 (defaults de probe) | 🔵 | PR-4.3 |
| 02 | Finding 7 (quality fields nulos) | 🔵 | won't-fix |
| 03 code-smell | Localized dict | 🔴 | PR-2.2/2.3 |
| 03 | lang:str (entidades) | 🟠 | PR-2.2 |
| 03 | lang:str (read-path use cases) | 🔵 | PR-5.1 |
| 03 | MetadataReconciler (anemic+shotgun) | 🟠 | PR-4.4 |
| 03 | force:bool (boolean blindness) | 🟠 | PR-4.4 |
| 03 | Confidence float | 🟡 | PR-6.3 |
| 03 | int/float seconds | 🔵 | PR-6.3 |
| 03 | ConflictCandidate (data clump) | 🟡 | PR-6.4 |
| 03 | ScanRun.summary stringly | 🟡 | PR-6.5 |
| 03 | "Unknown" resolution sentinel | 🟡 | PR-6.5 |
| 03 | (paths, by_path) data clump | 🟡 | PR-6.5 |
| 03 | upsert episode/season (feature envy) | 🟡 | PR-6.5 |
| 03 | temporal coupling markers | 🟡 | PR-6.6 |
| 03 | library list[dict] request models | 🟡 | PR-6.8 |
| 03 | scan_schedule cron | 🔵 | PR-6.8 |
| 03 | item_count denormalizado | 🟡 | PR-6.7 |
| 03 | with_updates muta a fonte | 🟡 | PR-6.2 ⚠️ |
| 03 | episode_composite_id format | 🟡 | PR-6.9 |
| 03 | codec/format str | 🔵 | PR-6.9 |
| 03 | subtitle_track sentinel | 🔵 | PR-6.10 |
| 03 | directors/writers list[str] | 🔵 | won't-fix |
| 03 | library_id:str | 🔵 | adiado |
| 04 coupling | F1 | 🔴 | PR-3.3 |
| 04 | F2 | 🟠 | PR-3.2 |
| 04 | F3 | 🟠 | PR-3.1 |
| 04 | F4 / F6 | 🟠/🟡 | PR-3.5 |
| 04 | F5 | 🟡 | PR-3.4 |
| 04 | F7 | 🟡 | vigiar (sancionado) |
| 04 | F8 | 🟡 | vigiar (aliviado por PR-3.1) |
| 04 | F9 | 🔵 | PR-6.11 |
| 04 | F10 | 🔵 | sem ação |
| 05 doc-drift | #1 envelope | 🔴 | PR-D1 |
| 05 | regra módulos não importam | 🟠 | PR-D4 + corrigido por Fase 3 |
| 05 | PresentationException | 🟠 | PR-D3 |
| 05 | módulos 4 vs 9 | 🟡 | PR-D4 |
| 05 | pagination v3 vs código | 🟡 | PR-D1 |
| 05 | i18n catálogo / api-i18n-guide | 🟠/🟡 | PR-D2 |
| 05 | contagens endpoints/testes | 🟡 | PR-D4 |
| 05 | ADR-008 tree | 🔵 | PR-D4 |
| 05 | localização sem ADR | 🟡 | PR-2.1 |
| 05 | notifications/preferences sem ADR | 🔵 | PR-D4 |

---

## Resumo de esforço por fase

| Fase | PRs | Esforço agregado | Migration? | ADR? |
|---|---|---|---|---|
| 1 Docs | 4 | XS–S (horas) | Não | Não |
| 2 LocalizedMetadata | 3 | G (dias) | **Não** (wire preservado) | **ADR-023** |
| 3 Cross-BC | 5 | M–G (dias–semanas) | Não | nota ADR-008/009 |
| 4 Gateways + Reconciler | 4–5 | M–G (dias) | Não | Não |
| 5 Lang read-path | 1 | M | Não | Não |
| 6 Cleanup | 11 | XS–M cada (independentes) | Só PR-6.7 talvez | Não |

**Total: ~28 PRs.** Caminho mínimo de maior impacto: **Fase 1 → PR-6.2 → Fase 2 →
Fase 3** já fecha os 3 críticos e os 11 altos.
