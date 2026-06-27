# 04 — Auditoria de Acoplamento Inter-Módulos (Bounded Contexts)

**Tipo:** READ-ONLY. Nenhum código-fonte foi alterado.
**Framework:** Coupling risk = **Integration Strength × Distance × Volatility** (Vlad Khononov).
**Skill:** `coupling-analysis`
**Data:** 2026-06-27

## Escopo

Análise de acoplamento entre os bounded contexts do backend HomeFlix, com foco
nos seis módulos pedidos (`media`, `library`, `watch_progress`, `collections`,
`building_blocks`, `shared_kernel`) mais as arestas **entrantes** vindas de
`catalog_requests`, `identity`, `notifications`, `preferences` e `settings`,
pois essas contam como acoplamento sobre os seis.

Referências aplicadas: **ADR-008** (módulos não se importam; `modules →
shared_kernel → building_blocks`), **ADR-009** (toda leitura cross-BC passa por
**Read Port local + ACL adapter** no consumidor).

### Eixos de pontuação

- **Integration Strength** (pior → melhor): *intrusive* (entra no interno do
  outro: entidade/aggregate, ORM model) > *functional/model* (compartilha
  conhecimento de um modelo) > *contract* (port publicada, DTO estável).
- **Distance:** mesmo módulo (baixo) < shared_kernel/building_blocks (esperado)
  < outro bounded context (alto).
- **Volatility:** acoplar a coisa que muda muito (entidade de domínio, ORM
  model, runtime settings) é pior que acoplar a contrato estável.

---

## Matriz de Dependências de Módulos

Mecanismo: **direct** (import interno cru — violação), **acl** (Read Port + ACL
adapter, ADR-009 conforme), **acl-uow** (ACL adapter que importa a *UoW factory*
do provedor — superfície ampla, tolerado), **event** (assina *domain event* do
provedor via event bus), **auth** (crosscut de auth do `identity`), **port-impl**
(implementa uma port definida no outro módulo), **dep** (helper de presentation
publicado), **config** (importa `RuntimeSettings`/VO do `settings`), **sk** (via
shared_kernel — esperado/permitido).

| Importador ↓ \ Provedor → | media | library | watch_progress | collections | identity | settings | catalog_requests | notifications |
|---|---|---|---|---|---|---|---|---|
| **media** | — | **direct** + acl-uow | acl | — | acl-uow + **direct(use-case UoW)** + auth | **config** | port-impl | — |
| **library** | acl-uow | — | — | — | auth | — | — | — |
| **watch_progress** | event + acl-uow | — | — | — | event + dep | — | — | — |
| **collections** | event + acl-uow | — | acl-uow | — | event + dep | — | — | — |
| **catalog_requests** | event + acl | — | — | — | auth | — | — | — |
| **identity** | — | — | — | — | — | **config** | — | — |
| **notifications** | — | — | — | — | auth | — | port-impl | — |
| **preferences** | — | — | — | — | dep | — | — | — |
| **settings** | — | — | — | — | auth | — | — | — |

Todos os módulos dependem de `shared_kernel` e `building_blocks` (esperado — não
listado na matriz). Não há ciclos de **import** entre módulos; os pares
bidirecionais (`media ↔ catalog_requests`, `media ↔ watch_progress`) são
quebrados por port em direções separadas (ADR-009 §5), exceto o ciclo lógico
`media ↔ library` que tem uma perna **direct** (ver F1/F2).

### Observações estruturais

- **`integration_events` está vazio.** `src/shared_kernel/integration_events/`
  contém só um `__init__.py` com docstring. A abstração de *integration event*
  prometida pelo ADR-008 ("comunicação futura via integration events") e pelo
  ADR-009 (alternativa 3) **nunca foi construída**. Toda comunicação
  event-driven cross-BC assina **domain events** crus do provedor (F3).
- **12 ACL adapters / 24 ports** já existem — o padrão ADR-009 está amplamente
  adotado e funcionando. As violações são exceções pontuais, não a regra.

---

## Achados (ordenados por severidade)

### F1 — `media` importa o aggregate `Library` do BC `library` `[CRÍTICO]`

- **arquivo:linha:** `src/modules/media/application/services/scan_run_service.py:21`
  (`from src.modules.library.domain.entities.library import Library`); usado em
  `run_scan(self, run_id: ScanRunId, library: Library)` (:86).
- **root cause:** *Integration Strength = intrusive* (o pior caso): um serviço
  de aplicação do Media recebe o **aggregate root** de outro BC como parâmetro,
  não um DTO/port. *Distance = alto* (cruza fronteira de BC). *Volatility =
  alta* — `Library` é uma entidade de domínio que evolui (settings, tracks,
  paths). Qualquer mudança no aggregate `Library` arrasta o serviço de scan do
  Media. É exatamente o acoplamento que o ADR-009 nasceu para eliminar.
- **skill + confiança:** `coupling-analysis`, 0.95
- **evidence:** assinatura `run_scan(..., library: Library)` força o Media a
  conhecer o shape completo do aggregate do Library, sem port nem ACL.

### F2 — Use cases / routes do `media` importam *UoW factories* de outros BCs (bypass de ACL) `[ALTO]`

- **arquivos:linha:**
  - `src/modules/media/application/use_cases/get_overview_stats.py:3`
    (`IdentityUnitOfWorkFactory` direto em um use case)
  - `src/modules/media/application/use_cases/trigger_scan.py:6`
    (`LibraryUnitOfWorkFactory` em um use case)
  - `src/modules/media/presentation/routes/scan_routes.py:13`
    (`LibraryUnitOfWorkFactory` na camada de presentation)
- **root cause:** ADR-009 §3 diz que o **use case só conhece a port local**; a
  ACL vive na infra. Aqui a camada de aplicação (e até presentation) importa a
  *Unit of Work* completa de outro BC, dando acesso a **todos** os repositórios
  do provedor (superfície enorme) em vez de um contrato read-only mínimo.
  *Strength = functional/model* (conhece a UoW do outro BC), *Distance = alto*,
  *Volatility = média*. O próprio docstring de `get_overview_stats` admite o
  atalho ("same pattern the trigger-scan use case uses").
- **skill + confiança:** `coupling-analysis`, 0.9
- **evidence:** três call-sites em camadas application/presentation importando
  `*UnitOfWorkFactory` de `identity`/`library` sem port intermediária.

### F3 — Consumidores assinam *domain events* crus do provedor (sem integration-event contract) `[ALTO]`

- **arquivos:linha (representativos):**
  - `src/modules/collections/application/event_handlers/on_movie_merged.py:11`
    e `on_movie_promoted_to_series.py:11` → `media.domain.events`
  - `src/modules/watch_progress/.../on_movie_merged.py:7`,
    `on_movie_promoted_to_series.py:7` → `media.domain.events`
  - `src/modules/catalog_requests/.../on_media_enriched.py:13` →
    `media.domain.events.MediaEnrichedEvent`
  - `src/modules/collections/.../on_user_deleted.py:10` e
    `src/modules/watch_progress/.../on_user_deleted.py:7` →
    `identity.domain.events.UserDeletedEvent`
- **root cause:** *Strength = model coupling* sobre um artefato **interno de
  domínio** do provedor. Os 5 consumidores acoplam à classe de *domain event*
  do `media`/`identity` (que carrega VOs de domínio como `MovieId`/`SeriesId`).
  Como `shared_kernel/integration_events` está vazio, não existe um contrato de
  evento publicado e estável — o evento muda junto com o domínio (*Volatility
  média-alta*), cruzando fronteira de BC (*Distance alto*). Renomear/alterar um
  domain event do Media quebra 3+ BCs silenciosamente (shotgun surgery).
- **skill + confiança:** `coupling-analysis`, 0.85
- **evidence:** 5 arestas event-driven, todas importando de `*.domain.events`;
  pacote `integration_events` desabitado.

### F4 — `RuntimeSettings`/VOs do `settings` espalhados pela infra (e um use case) do `media` `[ALTO]`

- **arquivos:linha:** 8 sites em `media` →
  `src/modules/media/infrastructure/streaming/hls_service.py:68`,
  `.../thumbnail_service.py:36`, `.../scrub_preview_locator.py:18`,
  `infrastructure/audio/audio_extractor.py:32`,
  `infrastructure/video/credits_detector.py:47`, `.../frame_hasher.py:30`, e
  **`application/use_cases/detect_movie_conflicts.py:32-33`**
  (`settings.domain.value_objects.ScanDedupConfig` +
  `settings.infrastructure.runtime_settings.RuntimeSettings`).
- **root cause:** `RuntimeSettings` é uma classe **concreta de infraestrutura**
  de outro BC, importada em 8 pontos do Media — inclusive em um **use case**,
  que ainda alcança um **VO de domínio** (`ScanDedupConfig`) do `settings`.
  *Strength = intrusive/model* (depende do interno concreto, não de uma port de
  config), *Distance = alto*, *Volatility = média* (settings é config-driven via
  ADR-013/014 e muda por feature). Sem port (ex.: `StreamingConfigPort`), uma
  refatoração de `RuntimeSettings` toca metade da infra do Media.
- **skill + confiança:** `coupling-analysis`, 0.85
- **evidence:** ADR-009 não foi aplicado ao `settings`; o BC é tratado como
  biblioteca de config importável.

### F5 — Vazamento do ORM `UserModel` do `identity` para as routes de 5 módulos `[MÉDIO]`

- **arquivos:linha (representativos):**
  `src/modules/media/presentation/routes/*` (14 pares auth+UserModel),
  `catalog_requests/.../admin_catalog_request_routes.py:21` e
  `catalog_request_routes.py:28`, `library/.../library_routes.py:12`,
  `notifications/.../notification_routes.py:12`,
  `settings/.../admin_settings_routes.py:19`.
- **root cause:** As routes importam
  `identity.infrastructure.persistence.models.user_model.UserModel` — um
  **SQLAlchemy ORM model**, artefato de **infra interna** do `identity` — só
  para anotar o parâmetro descartado `_admin: UserModel = Depends(...)`.
  *Strength = intrusive* (toca o ORM do outro BC), porém *baixa funcionalidade*
  (uso é só type hint, valor ignorado). *Distance = alto*, mas *Volatility =
  média* e disseminação alta (≈20 sites) → risco de shotgun surgery se o ORM do
  identity mudar. A dependência funcional `current_admin_user`/`current_active_user`
  é um crosscut de auth legítimo (contrato publicado); o problema é o **tipo de
  retorno** vazar o ORM em vez de um DTO/`AuthenticatedUser`.
- **skill + confiança:** `coupling-analysis`, 0.8
- **evidence:** 20+ imports do `UserModel` fora do `identity`, sempre como
  anotação de dependência de auth.

### F6 — `identity` importa `RuntimeSettings` do `settings` `[MÉDIO]`

- **arquivo:linha:** `src/modules/identity/infrastructure/storage/local_avatar_storage.py:32`.
- **root cause:** Mesma classe de problema do F4 em escala menor (1 site):
  infra do `identity` depende do interno concreto de config do `settings` sem
  port. *Strength = intrusive*, *Distance = alto*, *Volatility = média*. Isolado,
  baixo impacto, mas reforça que `settings` virou dependência ambiente global.
- **skill + confiança:** `coupling-analysis`, 0.75

### F7 — ACL adapters importam a *UoW factory* completa do provedor `[MÉDIO]`

- **arquivos:linha:**
  `collections/.../media_lookup_adapter.py:13`,
  `collections/.../progress_lookup_adapter.py:11`,
  `library/.../media_count_query_adapter.py:13`,
  `media/.../progress_lookup_adapter.py:14`,
  `media/.../library_health_adapter.py:11`,
  `media/.../profile_library_access_adapter.py:8`,
  `media/.../profile_summary_adapter.py:21`.
- **root cause:** Padrão ADR-009 corretamente aplicado (a importação está
  **isolada no ACL adapter**, na infra do consumidor — é o lugar certo). A
  ressalva: o adapter importa a `*UnitOfWorkFactory` do provedor, expondo
  internamente **todos** os repositórios do outro BC, mais amplo que um repo
  read-only focado (o próprio ADR-009 lista esse risco — "adapter virar
  repositório mal disfarçado"). *Strength = functional/model*, *Distance =
  alto*, *Volatility = baixa* (UoW factory é interface estável). Risco contido
  porque o blast radius para no adapter; é o padrão sancionado, só monitorar.
- **skill + confiança:** `coupling-analysis`, 0.7

### F8 — `shared_kernel` acumulando VOs de identidade per-BC `[MÉDIO]`

- **arquivos:** `src/shared_kernel/value_objects/` — 12 arquivos de VO, incluindo
  `media_id.py` (`MovieId`/`SeriesId`/`SeasonId`/`EpisodeId` — linguagem do Media
  BC), `media_type.py`, `library_id.py`, `profile_id.py`, `user_id.py`,
  `episode_composite_id.py`.
- **root cause:** ADR-008 definiu shared_kernel "mínimo" (3 VOs: FilePath,
  LanguageCode, tracks). Hoje abriga identificadores que pertencem
  conceitualmente a BCs específicos (`MovieId` é do Media; `LibraryId` do
  Library; `UserId` do Identity). Foram promovidos porque domain events e ports
  precisam referenciá-los entre BCs — é a **válvula de escape do acoplamento
  F3**. Não é violação de direção (todos podem importar shared_kernel), mas é
  *drift* do shared kernel virar dumping ground de tipos cross-BC. *Strength =
  contract* (VOs estáveis), *Volatility = baixa* — por isso médio, não alto:
  centralizar tipos estáveis é aceitável, mas merece vigilância de review (ADR-008
  risco "shared_kernel crescer demais").
- **skill + confiança:** `coupling-analysis`, 0.65

### F9 — `resolve_profile_id` (presentation helper do `identity`) reusado por 4 módulos `[BAIXO]`

- **arquivos:linha:** `media/presentation/dependencies.py:10`,
  `collections/.../dependencies.py:10`, `watch_progress/.../dependencies.py:11`,
  `preferences/.../dependencies.py:10`.
- **root cause:** Importa um helper de **presentation** publicado do `identity`
  (resolução de profile a partir do request). *Strength = contract* (função
  utilitária estável de FastAPI dependency), *Volatility = baixa*. Aceitável como
  crosscut de presentation; só não há contrato formal documentando-o como API
  pública do identity.
- **skill + confiança:** `coupling-analysis`, 0.6

### F10 — Inversões de port: provedor implementa port definida no consumidor `[BAIXO]`

- **arquivos:linha:**
  `media/.../localized_title_provider_adapter.py:11` (implementa
  `catalog_requests.application.ports.LocalizedTitleProviderPort`),
  `notifications/.../notification_publisher_adapter.py:11` (implementa
  `catalog_requests...notification_publisher_port`),
  `catalog_requests/.../catalog_request_lookup_adapter.py:15` (implementa
  `media.application.ports.catalog_request_lookup_port`).
- **root cause:** Acoplamento via **contrato (port)** — o melhor caso de
  Strength. O consumidor define a port; o provedor a implementa do outro lado
  (ADR-009 conforme). A única nuance é que o adapter importa o **módulo** da port
  do outro BC, mas como é uma ABC estável (contract), *Volatility = baixa* e o
  risco é mínimo. Documentado nos próprios docstrings dos adapters. Sem ação.
- **skill + confiança:** `coupling-analysis`, 0.6

---

## Resumo de Hotspots

1. **`media` é o epicentro.** Concentra as arestas mais perigosas: F1 (import de
   aggregate `Library`), F2 (UoW bypass para `identity`+`library`), F4
   (`RuntimeSettings` em 8 sites). O par **`media ↔ library`** é o mais
   degradado — tem leitura via ACL (`library_health_adapter`) **e** três
   imports diretos que furam o padrão. Endereçar `media→library` primeiro.

2. **`integration_events` morto + assinatura de domain events crus (F3).** A
   abstração planejada não existe; 5 BCs acoplam a domain events internos. É a
   dívida arquitetural de maior alcance lateral. Promover os ~4 eventos cross-BC
   a *integration events* estáveis em `shared_kernel/integration_events`
   resolveria F3 e aliviaria a pressão sobre o shared_kernel (F8).

3. **`settings` virou dependência ambiente (F4+F6).** `RuntimeSettings` é
   importado concretamente por `media` (8x) e `identity` (1x) sem nenhuma port.
   Um `*ConfigPort` por consumidor alinharia ao ADR-009.

4. **`identity` vaza ORM via auth (F5).** O crosscut de auth é legítimo, mas o
   tipo de retorno deveria ser um DTO (`AuthenticatedUser`), não o `UserModel`
   SQLAlchemy — ~20 sites dependem hoje do interno de persistência do identity.

5. **O padrão ADR-009 está saudável onde foi aplicado** (F7/F10): 12 ACL
   adapters, 24 ports, sem ciclos de import. As violações são exceções
   localizadas, não a norma — o refactor é cirúrgico, não estrutural.
