# ADR Index — HomeFlix

Roteador "tópico/sintoma → qual ADR ler". Use quando precisar de detalhe sobre uma decisão específica.

Os ADRs vivem em `docs/adr/` no repositório do HomeFlix. **Sempre consulte o ADR completo no repo** antes de propor mudança que conflita com a decisão.

## Por tópico

### Domain Models (Pydantic, validação, estrutura)

→ **ADR-001** (`docs/adr/ADR-001-pydantic-domain-models.md`)

Cobre:
- Por que Pydantic encapsulado em vez de dataclass puro ou attrs
- Hierarquia: `DomainModel` → `ValueObject` / `CompoundValueObject` / `StringValueObject` / `IntValueObject` / `DomainEntity` / `AggregateRoot`
- Configuração padrão (`validate_assignment`, `extra='forbid'`, `frozen=True`)
- `DomainValidationError` encapsulando `pydantic.ValidationError`
- Protocol `SupportsUpdates` para tipagem de objetos com `with_updates()`

Consultar quando: criar novo VO, entity, ou aggregate. Decidir entre `StringValueObject` e `CompoundValueObject`. Tipar funções que aceitam objetos com `with_updates`.

### IDs de agregados (formato, geração, persistência)

→ **ADR-002** (`docs/adr/ADR-002-prefixed-external-ids.md`)

Cobre:
- Formato `{prefix}_{base62_12chars}` (16 chars total)
- Por que prefixed em vez de UUID, auto-increment, ULID, hashids
- Mapeamento de prefixos: `mov`, `ser`, `ssn`, `epi`, `prg`, `wls`, `fav`, `lst`, `gnr`, `scn`, `lib`
- `external_id` separado de `internal_id` na persistência
- Implementação de `ExternalId` e typed aliases (`MovieId`, `SeriesId`, etc.)

Consultar quando: adicionar novo tipo de agregado (precisa de novo prefixo). Decidir como expor IDs em rotas. Implementar mapper entity ↔ SQLAlchemy model.

### Estrutura de pastas / organização do projeto

→ **ADR-008** (`docs/adr/ADR-008-screaming-architecture.md`) — **substitui ADR-003**

Cobre:
- Por que migrar de "camadas na raiz" para "módulos como eixo primário"
- `building_blocks/` (técnico) vs `shared_kernel/` (negócio cross-module)
- Estrutura interna de cada módulo: `domain/`, `application/`, `infrastructure/`, `presentation/`
- Regra: módulos não importam entre si
- Onde fica infraestrutura compartilhada (`src/infrastructure/`)
- Imports permitidos vs proibidos

Consultar quando: criar novo bounded context. Decidir onde colocar uma classe nova (qual módulo, qual camada). Refatorar import cross-module.

⚠️ ADR-003 ainda existe no repo mas está marcado como **Substituído**. Sempre referencie ADR-008.

### Dependency Injection / Composition Root

→ **ADR-004** (`docs/adr/ADR-004-dependency-injection.md`)

Cobre:
- Por que `dependency-injector` em vez de `python-injector` ou Depends puro
- Use cases puros (sem `@inject` no construtor)
- Wiring `@inject`/`Provide` **somente** em routes
- Containers organizados por responsabilidade: `infrastructure`, `repositories`, `use_cases/<bc>`
- Composition root em `config/containers/main.py`
- Como testar use cases (sem container, mock direto no construtor)

Consultar quando: adicionar nova dependência. Criar novo bounded context (precisa de novo container). Testar use case. Decidir lifecycle (Singleton vs Factory).

### Library como entidade (configuração de fontes de mídia)

→ **ADR-005** (`docs/adr/ADR-005-library-as-configuration-entity.md`)

Cobre:
- Por que Library é entidade de domínio, não config global
- `LibraryType` (movies/series/mixed), `MetadataProvider` (TMDB/OMDB/TVDB), `SubtitleMode`
- `LibrarySettings` (preferred audio/subtitle, scan schedule)
- `AudioTrack` e `SubtitleTrack` como VOs
- Lógica de seleção de faixas (`TrackSelector`)
- Posicionamento: BC `library` separado de `media`

Consultar quando: criar feature relacionada a configuração de bibliotecas. Adicionar novo provedor de metadados. Lidar com seleção de faixas de áudio/legenda. Adicionar novo tipo de scan.

### Variantes de arquivos (múltiplas resoluções por mídia)

→ **ADR-006** (`docs/adr/ADR-006-media-file-variants.md`)

Cobre:
- Como uma mídia (Movie/Episode) pode ter múltiplos `MediaFile` (720p, 1080p, 4K)
- `AudioTrack`/`SubtitleTrack` ficam dentro de `MediaFile`, não direto na entity
- Resolution, VideoCodec, HDRFormat como VOs

Consultar quando: trabalhar com player/streaming. Adicionar suporte a novo codec/HDR. Importar mídia que tem múltiplas versões.

### Imutabilidade `with_*`/`without_*`

→ **ADR-007** (`docs/adr/ADR-007-immutable-entities-with-convention.md`)

Cobre:
- Por que `frozen=True` em entidades (não só VOs)
- Convenção `with_X` para adicionar/modificar, `without_X` para remover
- Retorno de `Self` em todos os métodos de mutação
- `with_atomic_updates()` faz bump automático de `updated_at` via `setdefault`
- `touch()` foi removido (incompatível com imutabilidade)
- Comportamento `no-op`: retornar `self` quando não há mudança (duplicata, item inexistente)

Consultar quando: criar entity nova. Adicionar método de modificação em entity existente. Refatorar método imperativo herdado. Decidir comportamento de borda (duplicata, item ausente).

### Cross-BC Read Ports + ACL

→ **ADR-009** (`docs/adr/ADR-009-cross-bc-read-ports.md`)

Cobre:
- Por que módulos não importam entre si direto
- Estrutura: port em `application/ports/`, adapter em `infrastructure/acl/`
- DTOs locais ao consumidor (não promover pra `shared_kernel` sem evidência)
- Wiring: receber repo do provider via `providers.Dependency()` no container do consumidor
- Quando aceitar import direto entre infras (ciclo de wiring inviável)
- Por que NÃO usar domain events agora (complexidade desnecessária)

Consultar quando: detectar import cross-module. Implementar feature que exibe dado de múltiplos BCs (ex: home screen). Decidir se uma leitura cross-BC vale port ou se é caso de mover responsabilidade.

### Identity / User / Profile / Auth context

→ **ADR-010** (`docs/adr/ADR-010-identity-bounded-context.md`)

Cobre:
- Novo BC `identity` com `User` (auth root) e `Profile` (personalization context, referenciado cross-BC)
- FastAPI Users como **biblioteca base** de autenticação (signup, login, password reset, email verification) — estratégia concreta de transport/storage de sessão definida em ADR-011
- ID strategy: UUID interno no DB (compat FastAPI Users) + prefixed `external_id` no domain/API (`usr_xxx`, `prf_xxx`) via mapper
- Prefixos `usr` e `prf` adicionados ao `ExternalId.VALID_PREFIXES`
- `profile_id` propagado **explicitamente** via Input dataclass — proibido `contextvars`/middleware mágico
- `get_current_profile` FastAPI dependency resolve `profile_id` uma vez por request (validando ownership user↔profile)
- BCs consumidores (`watch_progress`, `collections`, `preferences`) ganham `profile_id` em agregado e usam `ProfileLookupPort` (ADR-009)

Consultar quando: criar feature que toca dados pessoais (precisa de `profile_id` no Input). Adicionar autorização/role check. Decidir como passar contexto de request a um use case. Implementar endpoint que requer login. Adicionar novo prefixo de ID ao registro.

### Authentication Strategy / Session Storage / Cookie

→ **ADR-011** (`docs/adr/ADR-011-authentication-strategy.md`)

Cobre:
- FastAPI Users `AuthenticationBackend` = `DatabaseStrategy` + `CookieTransport`
- Sessão server-side em tabela `access_tokens` (token opaco, não JWT)
- Cookie `homeflix_session` com `HttpOnly` + `Secure` + `SameSite=Strict`
- Expiração fixa de 90 dias desde a criação (sem slidable — `DatabaseStrategy` não suporta nativo; trade-off aceito para uso doméstico)
- `current_profile_id` armazenado na sessão (suporta multi-device com profiles independentes)
- Revogação imediata via `DELETE FROM access_tokens` (logout, kill switch, admin "deslogar dispositivo")
- CSRF mitigado por `SameSite=Strict` + CORS allowlist; double-submit token diferido para se relaxar SameSite
- Schema permite OAuth providers (Google etc.) e bearer JWT (mobile) como adições paralelas no futuro

Consultar quando: implementar login/logout/session. Tocar config de cookies. Mudar config CORS (revalidar exposição CSRF). Adicionar provider OAuth. Adicionar cliente não-browser (mobile, desktop). Implementar admin "ver/revogar sessões".

## Por sintoma no código

| Sintoma | ADR(s) relevante(s) |
|---|---|
| `from pydantic import BaseModel` em domain | ADR-001 |
| `id: UUID` ou `id: int` em entidade | ADR-002 |
| `from src.domain...` ou `from src.application...` (estrutura antiga) | ADR-008 |
| `from src.modules.X` em código de `src/modules/Y/` | ADR-009 |
| `from src.config.containers` em código de módulo | ADR-008 + ADR-004 |
| `@inject` em use case | ADR-004 |
| Método `add_X`, `mark_X`, `set_X`, `remove_X` em agregado | ADR-007 |
| Método `transition_to_*` em agregado | ADR-007 |
| `journey.touch()` (método removido) | ADR-007 |
| Adapter de port retornando VO de domínio (ex: `-> EnrichedIdentityData`) | ADR-009 (filosofia ACL) |
| Use case com lógica de scan/biblioteca embutida sem usar `Library` | ADR-005 |
| `AudioTrack` direto em `Movie` (em vez de em `MediaFile`) | ADR-006 |
| `contextvars.ContextVar` ou middleware setando `profile_id`/`user_id` global | ADR-010 |
| `id: UUID` exposto em rota ou DTO de identity (deveria ser `usr_xxx`/`prf_xxx`) | ADR-010 |
| Use case que mexe em `WatchProgress`/`CustomList`/`PlaybackPreferences` sem `profile_id` no Input | ADR-010 |
| `from fastapi_users` em código fora de `src/modules/identity/infrastructure/` | ADR-010 |
| Token JWT armazenado em `localStorage` no frontend ou retornado em response body | ADR-011 |
| `cookie_httponly=False` ou `cookie_samesite="none"` sem justificativa registrada | ADR-011 |
| Blacklist de JWT, refresh token rotation, `exp`/`iat` claims customizados | ADR-011 |

## Por pergunta comum

**"Onde coloco essa classe nova?"** → ADR-008

**"Como faço o ID desse novo agregado?"** → ADR-002 (definir prefixo + criar typed alias herdando `ExternalId`)

**"Como esse use case acessa dados de outro BC?"** → ADR-009

**"Como mockar essa dependência no teste?"** → ADR-004 (injetar direto no construtor, sem container)

**"Posso modificar este agregado in-place?"** → Não. ADR-007.

**"Posso usar BaseModel direto aqui?"** → Não. ADR-001.

**"Preciso de novo bounded context?"** → ADR-008 (critérios de quando criar BC novo)

**"Como esse use case sabe qual perfil está logado?"** → ADR-010 (`profile_id` explícito no Input dataclass; resolver via `get_current_profile` na route)

**"Posso usar contextvar pra propagar `user_id`/`profile_id`?"** → Não. ADR-010.

**"Como o usuário se mantém logado entre requests?"** → ADR-011 (sessão server-side em cookie HttpOnly, não JWT)

**"Como deslogo um usuário/dispositivo?"** → ADR-011 (`DELETE FROM access_tokens WHERE token = ?` ou `WHERE user_id = ?`)

## Adicionando novo ADR

Quando você (ou o usuário) tomar uma decisão arquitetural significativa que não está coberta:

1. Use `docs/adr/TEMPLATE.md` como base
2. Numere sequencialmente (próximo: ADR-012 ou superior)
3. Status inicial: `Proposto` → após implementação e validação: `Aceito`
4. Atualize **este índice** (`adr_index.md`) com o novo tópico
5. Se substitui ADR existente, marque o antigo como `Substituído` e referencie

Bom indicador de "isso merece ADR": a decisão vai impactar múltiplos arquivos/módulos OU envolve trade-off não-óbvio que outro dev questionaria daqui a 6 meses.
