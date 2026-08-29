# Plano de Remediação de Débito Técnico — Backend

> Origem: auditoria multi-agente de 2026-08-16 (6 dimensões de varredura +
> verificação adversarial). 8 achados confirmados + ~12 menções. O design
> geral é saudável (0 bugs ativos, 0 TODO/FIXME, 0 testes pulados); a dívida
> é quase toda **estrutural e concentrada no módulo `media`** (39.8k LOC,
> ~10× o próximo).

## Status (atualizado)

| Onda | Estado | Notas |
|------|--------|-------|
| 0 — Quick wins | ✅ concluída | type-safety (53→ menos `type:ignore`), testes RLE-PGS + FrameHasher, `UserId` VO |
| 1 — Higiene arquitetural | ✅ concluída | auth guards ADR-024, settings port, split de erros identity, test-gaps |
| 2 — ADRs | ✅ concluída | ADR-032 (decompor `media`) + ADR-033 (ISP repos) |
| 3 — Enablers | ✅ concluída | ISP repos (role-interfaces) + `hls_service` 1824→671 LOC |
| 4.1 — Extrair streaming | ✅ concluída | módulo `streaming` (HLS/probe/thumbnail/now-playing/OCR); `MediaPlaybackLookupPort`; smoke ok |
| 4.2 — Extrair metadata | ✅ concluída | módulo `metadata` (TMDB provider + artwork); enrichment ficou no catálogo consumindo o provider port |
| 4.3 — Playback-markers read-model | ⏸️ **adiada** | única fatia com migration de schema + backfill no DB real; maior risco, menor payoff — adiada por decisão explícita |
| 5.1 — Splits de container | ✅ concluída | via 4.1/4.2 (`StreamingContainer`/`MetadataContainer`); `media.py` 919→727 LOC |
| 5.2 — God-files restantes | 🔄 em andamento | `tmdb_client`/`movie_repository`/`series_repository` (Extract-Class) |

## Princípios de sequência

1. **Ganhos baratos e seguros primeiro** — momentum e redução de risco latente.
2. **ADRs antes dos refactors grandes** — decisões documentadas.
3. **Enablers antes das extrações** — ISP de repositórios e split do
   `hls_service` preparam o terreno.
4. **Strangler-Fig nas extrações** — um subdomínio por vez, streaming primeiro
   (menor fricção; o seam já existe).
5. **Cleanup por último** — splits de container seguem as extrações.

---

## Onda 0 — Quick wins: type-safety + testes

Baixo risco, alto sinal. PRs pequenos.

| # | Item | Esforço |
|---|------|---------|
| 0.1 | `detect_movie_conflicts`: tipar `uow: MediaUnitOfWork`, remover os **4 `type: ignore[attr-defined]`** do caminho destrutivo de auto-merge (inclui `uow.movies.delete`) e corrigir o comentário de "ciclo de import" (falso — o arquivo já tem `from __future__ import annotations` + import sob `TYPE_CHECKING`). | small |
| 0.2 | Cluster type-safety: `_genre_helpers` (união sync/async nunca awaited), `credits_detection_job._set` (mismatch id/kind — escreveria `EpisodeId` no UPDATE de movies), `search_tmdb_titles._ParsedQuery` (união discriminada), + LOW: `setting_mapper`, `FileVariantMixin.with_updates`, `track_naming`. | small |
| 0.3 | Testes do decoder **RLE-PGS** (`pgs_parser._decode_rle` por branch: run curto `0x01..0x3F`, estendido `0x40`, colorido `0x80`, overflow com clamp, linhas mistas). | small |
| 0.4 | Testes do **FrameHasher** (`_hash_raw_frames` real sobre bytes rgb24 sintéticos + cross-check `imagehash.dhash`). | small |
| 0.5 | `Notification`/`Setting` `recipient_user_id: str` → `UserId` VO (continua o 2.2 Primitive Obsession). | small |

## Onda 1 — Higiene arquitetural

| # | Item | Esforço |
|---|------|---------|
| 1.1 | Publicar os guards de auth em `identity/presentation/public.py` e migrar os **21 importadores** que furam o contrato do ADR-024 (importam de `identity.infrastructure.auth`). | medium |
| 1.2 | `UpdateSettingUseCase` → `RuntimeSettingsInvalidatorPort` (reforça ADR-004; hoje depende da classe concreta `RuntimeSettings`). | small |
| 1.3 | Separar `identity/domain/errors.py` (domínio) de um novo `identity/application/errors.py`. | small |
| 1.4 | Test-gaps: integração do `LibraryRepository` (upsert + branch restore-on-save) e rotas de `stream_routes.py` (558 LOC, sem teste). | medium |

## Onda 2 — ADRs das decisões grandes

| # | Item |
|---|------|
| 2.1 | **ADR** — Decomposição do `media` em subdomínios: estratégia, ordem (streaming → metadata → markers), contratos cross-BC (ports/ACL, ADR-009/024). |
| 2.2 | **ADR** — Interface Segregation em repositórios: "um port por razão-de-mudar" (precedente idiomático já existe: `intro_detection_run_repository`, `scan_run_repository`, `media_conflict_repository`, `subtitle_ocr_run_repository`). |

## Onda 3 — Enablers (preparar a extração)

| # | Item | Esforço |
|---|------|---------|
| 3.1 | **ISP** nos repositórios `series`/`movie`: extrair role-interfaces (`ArtworkMirrorRepository`, `IntroDetectionRepository`, `CreditsDetectionRepository`, `ScrubPreviewRepository`) + repo de catálogo enxuto; a classe SQLAlchemy pode implementar várias contra a mesma tabela. **Desbloqueia a extração dos subdomínios.** | large |
| 3.2 | **Extract-Class** no `hls_service.py`: os 7 seams (`HlsCacheStore`, `FfmpegProcessManager`, `TranscodeCommandBuilder`, `HardwareAccelerationProbe`, `SubtitlePipeline`, `MasterPlaylistWriter`, `ProbeCacheStore`); `HlsService` vira orquestrador fino implementando `HlsPlaylistPort`. **Prepara o streaming para sair limpo.** | large |

## Onda 4 — Extrações (Strangler-Fig, uma por vez)

| # | Item | Esforço |
|---|------|---------|
| 4.1 | Novo módulo **`playback`/`streaming`**: mover streaming (infra + application + use cases), wire via ports/ACL, container próprio. O seam já existe (importa zero entidades; opera via `HlsPlaylistPort`). | large |
| 4.2 | **Metadata/Enrichment + Artwork** como módulo Supporting; resolver o `uow.movies.save` do enrich com evento `MetadataResolved` ou write-port estreito. | large |
| 4.3 | **Playback-markers** (intro/créditos/scrub) como read-model por `media_id`, tirando as colunas dos agregados de catálogo. | large |

## Onda 5 — Cleanup

| # | Item | Esforço |
|---|------|---------|
| 5.1 | Splits de container (`StreamingContainer`, `MetadataContainer` compostos no `main.py`); `config/containers/media.py` (919 LOC) encolhe. | medium |
| 5.2 | God-files restantes: `movie_repository` (segregar + `MovieRelinkQueries` + `FtsQueries` comum), `tmdb_client` (`TmdbResponseMapper` puro + `ContentRatingPolicy` movida para o domínio). | large |

---

## Cobertura dos achados

- **Confirmados (8):** RLE-PGS → 0.3; extrair streaming → 4.1; god-repos (interface) → 3.1; god-object hls → 3.2; series_repo impl → 3.1/4.x; type-safety auto-merge → 0.1; FrameHasher → 0.4; container media → 5.1.
- **Menções (~12):** type-safety cluster → 0.2; auth guards ADR-024 → 1.1; RuntimeSettings port → 1.2; identity errors → 1.3; test-gaps Library/stream_routes → 1.4; UserId Notification → 0.5; movie_repo/tmdb_client → 5.2.

## O que preservar (não regredir)

Zero bugs ativos, zero TODO/skip; seams já desenhados antes da extração
(streaming não importa entidades); padrão de port estreito já idiomático;
god-objects pré-refatorados; boundary `str→VO` consistente onde aplicado;
container composto por módulo já é o padrão-alvo.
