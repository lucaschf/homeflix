# ADR-018: Identificadores de domínio como Value Objects nas fronteiras

**Status:** Proposto
**Data:** 2026-06-04
**Deciders:** Lucas Cristovam
**Technical Story:** Revisão de code smells (Fase 4) — identificadores e enums de domínio atravessando fronteiras de camada e de Bounded Context como `str` cru, sem validação.

---

## Contexto

O ADR-002 estabeleceu IDs externos prefixados como VOs tipados (`MovieId`, `LibraryId`, `ProfileId`...). Na prática, porém, três fluxos importantes carregam identificadores como `str` cru muito além da borda HTTP:

**1. `Profile.allowed_library_ids: list[str]` (identity → media, ACL de acesso)**

O campo que controla **quais bibliotecas um profile pode ver** é uma lista de strings da entidade até o consumidor cross-BC:

- Entidade: `profile.py:63` — `list[str]`; `Profile.create()` e `with_allowed_library_ids()` aceitam strings sem validar formato.
- DTOs (`ProfileOutput`, `CreateProfileInput`, `UpdateProfileInput`), schemas e rotas: `list[str]` de ponta a ponta.
- Persistência: coluna JSON; o decode (`profile_mapper.py:_decode_allowed_libraries`) coage lixo a `[]` com WARNING, mas **um ID malformado dentro da lista** (`"lib123"`, `"mov_..."`, typo) passa intacto.
- Cross-BC: `ProfileLibraryAccessPort` (em `media`) retorna `list[str]`, consumido por ~16 use cases de catálogo para filtrar leituras.

Dano: um ID inválido na ACL nunca casa com biblioteca nenhuma — **default-deny silencioso por typo**, indistinguível de "acesso removido de propósito". Nenhuma camada valida o formato `lib_xxx` em escrita.

**2. Role de usuário sem validação até o use case (identity)**

`CreateAdminUserRequest.role: str` e `UpdateUserRoleRequest.role: str` **sem constraint de enum** no schema; os DTOs de aplicação repetem `str`; a conversão `UserRole(input_dto.role)` só acontece dentro do use case. Um `"adminn"` atravessa presentation e application inteiras até estourar como `ValueError` genérico — em vez de erro 422 de validação na borda, com enum documentado no OpenAPI.

**3. `media_id: str` espalhado (4 BCs, ~66 ocorrências)**

`watch_progress` (entidade `WatchProgress.media_id`, repositórios, DTOs), `collections` (`WatchlistItem`, `CustomListItem`), eventos de domínio de `media` (`media_id`, `winner_id`, `candidate_*_id`...) e `catalog_requests` carregam IDs de mídia como `str`. O BC `media` já possui `MediaId = MovieId | SeriesId | SeasonId | EpisodeId` e `parse_media_id()` (`media/domain/value_objects/media_id.py`), mas são module-local — os outros BCs não podem importá-los (ADR-008/009).

**Pré-requisito estrutural:** `LibraryId` é module-local em `modules/library/domain/value_objects/library_id.py`. O item 1 exige que `identity` (entidade) e `media` (port) o usem — impossível sem violar a regra de dependência.

## Decisão

Nós iremos **tipar identificadores e enums de domínio como VOs em toda fronteira de camada e de BC**, com `str` cru permitido apenas na borda HTTP (schemas Pydantic) e na coluna do banco. A conversão acontece **uma vez, na primeira fronteira**, e o tipo flui validado dali em diante.

1. **Promover `LibraryId` ao shared_kernel** (`src/shared_kernel/value_objects/library_id.py`), seguindo o precedente do `MediaType` (ADR-016): é consumido por `library` (dono), `identity` (ACL do profile) e `media` (port de filtragem). O módulo `library` mantém re-export de compatibilidade enquanto seus ~13 arquivos migram incrementalmente.

2. **`Profile.allowed_library_ids: list[LibraryId]`.** A entidade, `Profile.create()` e `with_allowed_library_ids()` passam a aceitar/normalizar `LibraryId` (com `field_validator` convertendo `str` validado, no padrão do `CustomList.convert_name`). DTOs de aplicação carregam `list[str]` **já validados** na conversão do use case ou tipados — a escrita de um ID malformado falha na borda, não vira default-deny silencioso.

3. **Política de leitura da ACL persistida: descartar entrada inválida com WARNING (default-deny por entrada).** Divergência deliberada do ADR-016 (que valida com erro explícito no mapper): para **controle de acesso**, uma linha corrompida não pode nem conceder acesso nem derrubar o profile inteiro na leitura. Entrada inválida é dropada e logada — mesma filosofia do `_decode_allowed_libraries` atual, agora por item.

4. **`ProfileLibraryAccessPort` (media) retorna `list[LibraryId]`.** Com o VO no shared_kernel, o contrato cross-BC fica tipado legalmente; os ~16 use cases de catálogo comparam `LibraryId == LibraryId` em vez de strings.

5. **Role validado na presentation.** `CreateAdminUserRequest.role` e `UpdateUserRoleRequest.role` tipados com `UserRole` (StrEnum funciona nativamente em Pydantic e gera enum no OpenAPI); DTOs de aplicação tipados com `UserRole`; as conversões `UserRole(input_dto.role)` nos use cases desaparecem. Erro de role inválido vira 422 na borda.

6. **`media_id` tipado — diferido, incremental.** Exige promover `MediaId`/`parse_media_id` (ou um subconjunto) ao shared_kernel e tocar ~29 arquivos em 4 BCs. Entra no bucket diferido desta ADR, a ser atacado por módulo (eventos de `media` primeiro — contrato cross-BC — depois `watch_progress`, `collections`, `catalog_requests`), no padrão Strangler Fig do ADR-016.

### Ordem de migração

| Fase | Escopo | Dano endereçado |
|------|--------|-----------------|
| 4a | `LibraryId` no shared_kernel + re-export de compatibilidade em `library` | Pré-requisito estrutural |
| 4b | `Profile.allowed_library_ids` tipado + mapper (drop-and-warn por entrada) + `ProfileLibraryAccessPort` tipado | Default-deny silencioso na ACL |
| 4c | Role com `UserRole` em schemas + DTOs de identity | Validação tardia / OpenAPI sem enum |
| Diferido | `media_id` tipado por módulo; migrar imports de `LibraryId` para o shared_kernel e remover o re-export | Dívida de padrão |

## Consequências

### Positivas

- Um ID de biblioteca malformado falha **na escrita** (422/erro de domínio) em vez de virar acesso silenciosamente negado meses depois.
- O contrato cross-BC identity→media fica tipado; impossível passar um `mov_xxx` onde se espera biblioteca.
- OpenAPI documenta o enum de role; clientes erram menos e o erro chega como validação, não como 500/ValueError.
- O caminho para tipar `media_id` fica pavimentado (mesmo padrão, mesmo lar).

### Negativas

- Mais um VO no shared_kernel — o kernel cresce, e crescimento indiscriminado o transforma em "lixão comum" (mitigado: só entram VOs consumidos por 2+ BCs, como `MediaType`).
- Re-export de compatibilidade em `library` é indireção temporária até a migração dos imports.
- Conversões `str ↔ VO` adicionais em mappers e DTOs — verbosidade real, ganho de segurança que precisa justificá-la (aqui justifica: ACL e contrato cross-BC).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Linhas persistidas com IDs inválidos na ACL passam a ser dropadas na leitura (mudança de comportamento observável) | Baixa | Baixo | Hoje esses IDs já não concedem acesso (nunca casam); o drop+WARNING torna o estado corrompido visível em log em vez de silencioso |
| Re-export de `LibraryId` esquecido e nunca removido | Média | Baixo | Card no bucket diferido desta ADR (mesmo tratamento do alias `CollectionMediaType` no ADR-016) |
| Tipar o port quebra consumidores de catálogo em cascata | Baixa | Médio | Port + adapter + 16 use cases migram no mesmo PR (4b); suíte de catálogo cobre os filtros |

## Alternativas Consideradas

### 1. Manter `str` e validar pontualmente nos use cases

**Rejeitado porque:** repete o anti-padrão que o ADR-017 acabou de remover — a mesma validação copiada em N use cases, divergindo com o tempo. A ACL continuaria aceitando lixo em escrita.

### 2. `identity` definir seu próprio `LibraryId`

VO duplicado no BC identity, sem promover ao shared_kernel.

**Rejeitado porque:** dois VOs distintos com o mesmo prefixo `lib` para o mesmo conceito; o port de `media` precisaria de um terceiro ou continuaria em `str`. O shared_kernel existe exatamente para isso (FilePath, LanguageCode, MediaType, ProfileId já moram lá).

### 3. Importar `LibraryId` de `modules/library` diretamente

**Rejeitado porque:** viola a regra de dependência entre módulos (ADR-008) e o isolamento por ports (ADR-009).

### 4. Tipar tudo de uma vez (incluindo `media_id`)

**Rejeitado porque:** ~29 arquivos extras em 4 BCs num PR só. O padrão Strangler Fig do ADR-016 mostrou que migração incremental por dano funciona melhor; `media_id` já é prefixado e parseável, o dano é menor que o da ACL.

## Referências

- ADR-002 — Prefixed External IDs (formato e VOs de identidade)
- ADR-008 — Screaming Architecture com Módulos (regra de dependência)
- ADR-009 — Cross-BC Read Ports + ACL (contratos entre BCs)
- ADR-016 — MediaType como VO compartilhado (precedente de promoção ao shared_kernel + alias + Strangler Fig)
- ADR-017 — Invariantes de domínio na camada de domínio (regra única, sem cópias por use case)

---

## Notas de Implementação

Leitura da ACL persistida — drop-and-warn por entrada (default-deny):

```python
def _decode_allowed_libraries(profile_external_id: str, raw: str | None) -> list[LibraryId]:
    ...  # coerção de lixo estrutural a [] como hoje
    valid: list[LibraryId] = []
    for item in decoded:
        try:
            valid.append(LibraryId(str(item)))
        except DomainValidationException:
            _logger.warning(
                "[identity] Invalid library id in allowed_library_ids; dropping entry",
                profile_external_id=profile_external_id,
                entry=item,
            )
    return valid
```

Role na borda (presentation) — enum direto no schema:

```python
class UpdateUserRoleRequest(BaseModel):
    role: UserRole  # StrEnum: valida na borda e documenta o enum no OpenAPI
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-04 | Lucas Cristovam | Criação inicial (Proposto) |
