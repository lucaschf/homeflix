# Auditoria 01 — Clean Architecture / DDD

**Escopo:** auditoria READ-ONLY da direção de dependências, isolamento de bounded
contexts (ADR-008/009), pureza de domínio (ADR-001/017) e shape de use cases nos
seis alvos: `src/modules/media`, `src/modules/library`, `src/modules/watch_progress`,
`src/modules/collections`, `src/building_blocks`, `src/shared_kernel`. Metodologia:
skills `homeflix-arch` + `clean-arch-python` e os ADRs do projeto. Todos os números de
linha foram verificados lendo os arquivos. A estrutura geral é sólida — Screaming
Architecture bem aplicada, ports/ACL presentes onde a leitura cross-BC é correta; os
achados concentram-se em **leituras cross-BC feitas por atalho** (importar UoW/entidade
de outro módulo em vez de Port+ACL+DTO) e em pequenos desvios de direção de dependência.

## Resumo por severidade

| Módulo | Crítico | Alto | Médio | Baixo |
|---|---|---|---|---|
| media | 0 | 3 | 4 | 0 |
| library | 0 | 0 | 1 (ref. sistêmico) | 0 |
| watch_progress | 0 | 0 | 1 | 1 |
| collections | 0 | 0 | 1 | 1 |
| building_blocks | 0 | 0 | 0 | 1 |
| shared_kernel | 0 | 0 | 0 | 0 |
| **Total** | **0** | **3** | **7** | **3** |

> O achado "rotas importam `identity.infrastructure` (auth + UserModel ORM)" é
> **sistêmico** (~15 arquivos em media + 1 em library). Está contado uma vez em media
> (M-7) e referenciado em library.

---

## media

### A-1 — Application service importa entidade de domínio de outro BC · ALTO
- **arquivo:linha**: `src/modules/media/application/services/scan_run_service.py:21`
- **evidência**: `from src.modules.library.domain.entities.library import Library`
- **root cause**: o orquestrador de scan trafega o agregado `Library` de outro BC
  diretamente, em vez de um DTO local obtido via Read Port + ACL. Acopla a aplicação de
  `media` ao modelo de domínio interno de `library` — qualquer mudança no agregado
  `Library` repercute em `media`.
- **skill + confiança**: homeflix-arch (ADR-008/009) · 0.9

### A-2 — Leitura cross-BC via UoW alheia (identity) em vez de Read Port · ALTO
- **arquivo:linha**: `src/modules/media/application/use_cases/get_overview_stats.py:3`
- **evidência**: `from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory`
  — a própria docstring admite "Cross-BC reads (the users count) go through the identity
  UoW factory injected at the composition root".
- **root cause**: contagem de usuários (leitura cross-BC) é feita pegando emprestada a
  Unit of Work de `identity`, contornando o padrão ADR-009 (Port local + adapter ACL +
  DTO). O consumidor passa a depender da infraestrutura transacional do produtor.
- **skill + confiança**: homeflix-arch (ADR-009) · 0.9

### A-3 — Leitura cross-BC via UoW alheia (library) em vez de Read Port · ALTO
- **arquivo:linha**: `src/modules/media/application/use_cases/trigger_scan.py:6`
- **evidência**: `from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory`
- **root cause**: mesmo anti-padrão de A-2 — para resolver uma `Library` o use case
  importa e usa a UoW de `library`. O caminho correto seria `LibraryLookupPort` +
  adapter em `media/infrastructure/acl/` retornando um DTO próprio.
- **skill + confiança**: homeflix-arch (ADR-009) · 0.9

### M-4 — Repositório de domínio depende de tipo da application layer · MÉDIO
- **arquivo:linha**: `src/modules/media/domain/repositories/movie_repository.py:7`
  (idem `series_repository.py:7`, `media_conflict_repository.py:5`)
- **evidência**: `from src.building_blocks.application.pagination import PaginatedResult`
- **root cause**: a interface de repositório vive no domínio mas seu tipo de retorno
  (`PaginatedResult`) mora em `building_blocks/application`. Direção invertida:
  domínio → application. O contrato de paginação é parte do contrato de repositório e
  deveria estar em `building_blocks/domain` (ou um VO de paginação no domínio).
- **skill + confiança**: clean-arch-python · 0.85

### M-5 — Infra de media tipada contra a infra de settings (cross-BC) · MÉDIO
- **arquivo:linha**: `src/modules/media/infrastructure/streaming/hls_service.py:68`
  (idem `streaming/thumbnail_service.py:36`, `streaming/scrub_preview_locator.py:18`,
  `video/credits_detector.py:47`, `video/frame_hasher.py:30`, `audio/audio_extractor.py:32`)
- **evidência** (todas sob `if TYPE_CHECKING:`):
  `from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings`
- **root cause**: serviços de infraestrutura de `media` são tipados contra o holder
  concreto `RuntimeSettings` de outro BC. É só type-coupling (TYPE_CHECKING), mas amarra
  `media` à implementação concreta de `settings` em vez de um Protocol/port de config
  local. Severidade contida por ser type-only.
- **skill + confiança**: homeflix-arch (ADR-009) · 0.7

### M-6 — Use case de conflitos com type-import cross-BC de settings · MÉDIO
- **arquivo:linha**: `src/modules/media/application/use_cases/detect_movie_conflicts.py:32-33`
- **evidência** (sob `if TYPE_CHECKING:`):
  `from src.modules.settings.domain.value_objects import ScanDedupConfig`
  e `from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings`
- **root cause**: application de `media` referencia VO de domínio + infra concreta de
  `settings`. Type-only, mas a configuração cross-BC deveria chegar como DTO/port local.
- **skill + confiança**: homeflix-arch (ADR-009) · 0.65

### M-7 — Rotas importam a INFRAESTRUTURA de identity (auth + UserModel ORM) · MÉDIO (sistêmico)
- **arquivo:linha**: `src/modules/media/presentation/routes/movie_routes.py:11-12`
  e ~14 outras rotas (`stream_routes.py:25-26`, `series_routes.py:11-12`,
  `scan_routes.py:11-13`, `tmdb_lookup_routes.py:21-22`, todos os `admin_*_routes.py`).
- **evidência**:
  `from src.modules.identity.infrastructure.auth import current_admin_user` e
  `from src.modules.identity.infrastructure.persistence.models.user_model import UserModel`
- **root cause**: a presentation de `media` depende da **infraestrutura** de `identity`
  — em particular do modelo ORM `UserModel`, usado como tipo do usuário injetado. Mistura
  fronteira de auth com modelo de persistência de outro BC. O contrato de auth deveria
  ser exposto como dependência de presentation (ex.: um `AuthenticatedUser`/DTO ou um
  `Depends` reexportado), não o ORM. Pervasivo, daí "sistêmico".
- **skill + confiança**: clean-arch-python + homeflix-arch · 0.8

**Saudável em media**: domínio sem imports de FastAPI/SQLAlchemy; uso de
`pydantic.Field/model_validator` no domínio é sancionado pelo ADR-001 (não é violação);
catálogo rico de ports em `application/ports/`; ACL em `infrastructure/acl/`;
`scan_run_service`/`job_run_service` são orquestração legítima (não contêm regra de
domínio).

---

## library

### Ref. M-7 — Rota importa infra de identity · MÉDIO (parte do sistêmico)
- **arquivo:linha**: `src/modules/library/presentation/routes/library_routes.py:11-12`
- **evidência**: mesmos imports `identity.infrastructure.auth` + `UserModel`.
- **root cause**: idêntico a M-7.
- **skill + confiança**: clean-arch-python · 0.8

**Saudável em library**: domínio puro; invariantes em `Library`/VOs (ADR-017);
`TrackSelector` corretamente em `domain/services/`; leitura cross-BC exposta via
`application/ports/media_count_query_port.py` + ACL. Sem leaks de SQLAlchemy/FastAPI no
domínio ou application.

---

## watch_progress

### M-8 — Event handlers importam domain events de outros BCs (sem integration event) · MÉDIO
- **arquivo:linha**: `src/modules/watch_progress/application/event_handlers/on_movie_merged.py:7`
  (idem `on_movie_promoted_to_series.py:7` → `media.domain.events`;
  `on_user_deleted.py:7` → `identity.domain.events`)
- **evidência**: `from src.modules.media.domain.events import MovieMergedEvent`
- **root cause**: o consumidor acopla-se às **classes de domain event internas** do
  produtor. `src/shared_kernel/integration_events/` existe mas está **vazio** (só
  docstring) — a abstração de integration event pretendida nunca foi construída, então
  domain events fazem o papel de contrato de integração cross-BC, ferindo o isolamento
  do ADR-008 ("módulos NÃO importam entre si").
- **skill + confiança**: homeflix-arch (ADR-008/009) · 0.8

### B-9 — Presentation depende de presentation de identity · BAIXO
- **arquivo:linha**: `src/modules/watch_progress/presentation/dependencies.py:11`
- **evidência**: `from src.modules.identity.presentation.dependencies import resolve_profile_id`
- **root cause**: acoplamento presentation→presentation cross-BC. Menos grave (camada de
  borda, sem ORM), mas ainda assim uma dependência direta entre módulos.
- **skill + confiança**: homeflix-arch · 0.55

**Saudável em watch_progress**: `media_lookup_port` + adapter ACL corretos; domínio puro
com `ContinueWatchingSelector` em `domain/services/`.

---

## collections

### M-9 — Event handlers importam domain events de outros BCs (sem integration event) · MÉDIO
- **arquivo:linha**: `src/modules/collections/application/event_handlers/on_movie_merged.py:11`
  (idem `on_movie_promoted_to_series.py:11` → `media.domain.events`;
  `on_user_deleted.py:10` → `identity.domain.events`)
- **evidência**: `from src.modules.media.domain.events import MovieMergedEvent`
- **root cause**: idêntico a M-8 — consumo direto das classes de domain event do produtor
  por falta da camada de integration events em `shared_kernel`.
- **skill + confiança**: homeflix-arch (ADR-008/009) · 0.8

### B-10 — Presentation depende de presentation de identity · BAIXO
- **arquivo:linha**: `src/modules/collections/presentation/dependencies.py:10`
- **evidência**: `from src.modules.identity.presentation.dependencies import resolve_profile_id`
- **root cause**: igual a B-9.
- **skill + confiança**: homeflix-arch · 0.55

**Saudável em collections**: `media_lookup_port` + `progress_lookup_port` + dois adapters
ACL corretos; domínio puro (`Watchlist`, `CustomList`, VOs com invariantes via Pydantic
do ADR-001).

---

## building_blocks

### B-11 — Tipos de contrato de domínio residem na application layer · BAIXO
- **arquivo:linha**: `src/building_blocks/application/pagination.py` (consumido pelo
  domínio em M-4) e `src/building_blocks/application/errors.py` (consumido por
  `src/modules/identity/domain/errors.py:10`, fora do escopo dos seis alvos).
- **evidência**: `PaginatedResult` e as bases de exceção (`ResourceNotFoundException`
  etc.) ficam em `building_blocks/application` mas são necessários por contratos/erros de
  camada de domínio de vários módulos.
- **root cause**: a fronteira application/domain dentro de `building_blocks` deixa na
  application tipos que fazem parte de contratos de domínio (paginação de repositório;
  bases de exceção de domínio). Reclassificar `PaginatedResult` (e as bases de exceção
  de domínio) para `building_blocks/domain` eliminaria as direções invertidas de M-4 e do
  import em identity.
- **skill + confiança**: clean-arch-python · 0.6

**Saudável em building_blocks**: `building_blocks/domain` **não** importa de
`application/infrastructure/presentation` (verificado, zero ocorrências). Bases
`DomainModel`/`ValueObject`/`AggregateRoot` encapsulam Pydantic conforme ADR-001.

---

## shared_kernel

**Sem achados.** Verificado: nenhum import de `src.modules.*` nem de
`building_blocks.application/infrastructure/presentation` (zero ocorrências). Os VOs
(`FilePath`, `LanguageCode`, `AudioTrack`, `ImageUrl`, etc.) usam apenas
`pydantic.model_validator/Field` — sancionado pelo ADR-001. `integration_events/` está
presente porém **vazio** (relevante para M-8/M-9: a abstração existe como pasta mas não
como código).

---

## Observação cross-cutting

Os achados de maior severidade (A-1, A-2, A-3) e os médios M-8/M-9 compartilham **uma
única causa raiz**: a ausência de um mecanismo de integração cross-BC consistente. Onde
ADR-009 foi seguido (watch_progress/collections → media via `media_lookup_port` + ACL) o
isolamento é exemplar; onde a leitura cross-BC apareceu depois (media → library/identity
para stats e scan; handlers consumindo domain events) recorreu-se a atalhos: importar a
UoW/entidade alheia ou o domain event do produtor. Fechar o gap = (a) `LibraryLookupPort`
/ `IdentityCountPort` em `media` com adapters ACL, e (b) materializar
`shared_kernel/integration_events` com contratos de evento publicados.
