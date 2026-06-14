# ADR-016: MediaType como Value Object compartilhado

**Status:** Aceito
**Data:** 2026-05-31
**Deciders:** Lucas Cristovam
**Technical Story:** Revisão de code smells (Fase 1) — o discriminador "movie | series" é stringly-typed em estado persistido e em eventos de domínio.

---

## Contexto

O conceito "que tipo de mídia é esta" (filme ou série) aparece em pelo menos **onze** lugares do código, sob **três vocabulários** e com graus de tipagem inconsistentes:

**Cru (`str`), incluindo estado persistido e contrato entre Bounded Contexts:**

- `MediaConflict.candidate_a_type` / `candidate_b_type` — `str`, **persistido** em `media_conflicts` (coluna `String(20)`).
- `MediaCreatedEvent.media_type` / `MediaEnrichedEvent.media_type` — `str = ""`, produzidos com literais `"movie"`/`"series"` e consumidos por outro BC (`catalog_requests`).
- `ConflictCandidateSummary.media_type`, `GetFeaturedInput.media_type` — `str`.
- Comparações com literal espalhadas: `!= "movie"` (`resolve_media_conflict.py:171`, `list_conflicts.py:121`), `== "series"` (`search_catalog.py`, `get_featured_media.py`, `list_genres.py`), etc.

**Já tipado, mas com vocabulários divergentes:**

- `MediaTypeFilter = Literal["movie", "series"]`, `SearchInput.media_type = Literal["movie", "series"]` — vocabulário interno.
- `admin_relink_dtos.MediaType = Literal["movie", "tv"]`, `tmdb_lookup_dtos.LookupMediaType = Literal["movie", "tv"]` — vocabulário **TMDB** (`tv`, não `series`), correto na borda porque espelha `/search/tv`.

**Três enums `StrEnum` que cobrem o mesmo conceito, sem fonte única:**

- `shared_kernel.value_objects.media_type.CollectionMediaType` — `MOVIE="movie"`, `SERIES="series"`.
- `catalog_requests…RequestedMediaType` — `MOVIE="movie"`, `SERIES="series"` (idêntico ao anterior).
- `watch_progress…WatchableMediaType` — `MOVIE="movie"`, `EPISODE="episode"` (**conceito diferente**: granularidade de playback é por episódio, não por série).

### Dano concreto

O `candidate_*_type` é **gravado no banco** sem qualquer validação (a coluna `String(20)` aceita qualquer string). Um typo do detector (`"movies"`, `"Movie"`) grava sem erro; na leitura, `_ensure_movie_pair` o trata como tipo não suportado e o conflito fica **permanentemente irresolvível** pela UI — perda silenciosa de uma linha do queue de conflitos. O mesmo risco vale para o contrato entre BCs: `OnMediaEnrichedHandler` (em `catalog_requests`) faz `RequestedMediaType(event.media_type)` e, se o literal divergir, engole o evento num `except ValueError` e a request **nunca vira fulfilled**.

Hoje os literais coincidem por acaso — não há tipo que garanta isso.

## Decisão

Nós iremos **promover um único `MediaType` canônico** para o discriminador filme/série e adotá-lo de forma incremental (Strangler Fig), começando pelos pontos de maior dano (estado persistido e eventos).

1. **Lar canônico: `shared_kernel`.** O `MediaType` vive em `src/shared_kernel/value_objects/media_type.py`. É obrigatório que esteja no shared_kernel — os eventos de domínio do BC `media` carregam o tipo e são consumidos por `catalog_requests`; tipá-los com um enum do BC `media` violaria a regra de dependência (ADR-008/009). O shared_kernel é o único lar que todos os BCs podem importar.

2. **Generalizar o que já existe, não criar um quarto enum.** O arquivo `shared_kernel/value_objects/media_type.py` já contém `CollectionMediaType(MOVIE, SERIES)` — exatamente os membros canônicos. Renomeamos a classe para `MediaType` e mantemos `CollectionMediaType = MediaType` como **alias de compatibilidade** para não tocar os ~25 arquivos de `collections` neste momento.

   ```python
   class MediaType(StrEnum):
       MOVIE = "movie"
       SERIES = "series"

   # Back-compat alias — remover quando collections migrar (ver Strangler Fig).
   CollectionMediaType = MediaType
   ```

3. **Vocabulário TMDB (`tv`) fica na borda.** `tv` é o vocabulário da API TMDB (`/search/tv`) e permanece nos DTOs/adapters de borda (`admin_relink_dtos`, `tmdb_lookup_dtos`, `TmdbClient`). A conversão `tv ↔ MediaType.SERIES` acontece **explicitamente no ACL/adapter**, nunca deixando `tv` entrar em domínio, evento ou persistência.

4. **`WatchableMediaType` permanece separado.** `movie | episode` é outro conceito (granularidade de progresso de reprodução, que é por episódio). Não é unificado com `MediaType` — fundi-los representaria estado ilegal (`SERIES` não é um alvo válido de progresso).

5. **Erro observável, não fallback silencioso.** Onde um literal externo é convertido para `MediaType` (ex.: o handler cross-BC), um membro desconhecido vira **erro observável** (logado e/ou levantado), não um `warning` que engole o evento.

### Ordem de migração (Strangler Fig)

| Fase | Escopo | Dano endereçado |
|------|--------|-----------------|
| 1.2 | `MediaType` no shared_kernel + alias; tipar `MediaConflict.candidate_*_type` + mapper; substituir literais em `resolve_media_conflict` / `list_conflicts` | Corrupção de dado **persistido** |
| 1.3 | Tipar `MediaCreatedEvent.media_type` / `MediaEnrichedEvent.media_type` | Contrato de **evento** |
| 1.4 | `OnMediaEnrichedHandler` (catalog_requests): mapa explícito + erro observável + teste de contrato | Perda silenciosa **cross-BC** |
| 1.5 | Validar `media_type` no payload de `Notification`; alinhar DTOs internos a `MediaType` | Borda |
| Diferido | Migrar `RequestedMediaType` e `CollectionMediaType` para `MediaType` e remover o alias; consolidar comparações de literal restantes | Dívida de padrão |

A coluna `candidate_*_type` permanece `String(20)` — um `StrEnum` serializa para o mesmo `"movie"`/`"series"`, então **não há migration de schema**.

## Consequências

### Positivas

- O estado persistido e os eventos passam a ser validados na fronteira do domínio: um tipo inválido falha na escrita, em vez de corromper silenciosamente uma linha.
- Fonte única para o vocabulário filme/série; o mapeamento `tv → series` fica explícito e testável num lugar.
- Reaproveita o enum existente do shared_kernel; nenhum quarto enum é criado.
- O alias mantém `collections` funcionando sem alteração, permitindo migração incremental.

### Negativas

- Coexistência temporária de `MediaType` (canônico) e dos nomes legados (`CollectionMediaType` via alias, `RequestedMediaType` por enquanto independente) até a fase diferida.
- O alias é um ponto de indireção que precisa ser removido depois para o ganho ficar limpo.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Linhas legadas em `media_conflicts` com valor fora de `{movie, series}` quebram a desserialização do mapper | Baixa | Médio | Phase 1 só gravou `"movie"`; o mapper valida via `MediaType(value)` e qualquer linha inválida vira erro explícito, não corrupção silenciosa |
| Divergência futura `series` vs `tv` ao habilitar conflitos de série | Média | Médio | Conversão `tv ↔ SERIES` centralizada no ACL com teste de contrato (Fase 1.4) |
| Alias `CollectionMediaType` esquecido e nunca removido | Média | Baixo | Card de migração diferido registrado nesta ADR |

## Alternativas Consideradas

### 1. Criar um `MediaType` novo dentro do BC `media`

Enum no domínio de `media`, como sugeriu a revisão original.

**Rejeitado porque:** os eventos (`MediaEnrichedEvent`) são consumidos por `catalog_requests`. Tipar o campo do evento com um enum do BC `media` força o consumidor a importar o domínio de outro módulo, violando ADR-008/009. O tipo precisa morar no shared_kernel.

### 2. Manter os três enums e só validar o `str` no mapper

Adicionar validação pontual em `MediaConflict` sem unificar.

**Rejeitado porque:** não resolve a divergência de vocabulário nem o contrato de evento cross-BC; deixa três fontes da mesma verdade e a comparação por literal espalhada.

### 3. Unificar também `WatchableMediaType`

Um único enum `movie | series | episode`.

**Rejeitado porque:** mistura dois conceitos. Progresso de reprodução é por episódio; `SERIES` não é um alvo válido de progresso. Unificar criaria estado ilegal representável — o oposto do objetivo.

## Referências

- ADR-002 — Prefixed External IDs (vocabulário de identidade do domínio)
- ADR-008 — Screaming Architecture com Módulos (regra de dependência)
- ADR-009 — Cross-BC Read Ports + ACL (tipos compartilhados via shared_kernel)
- ADR-015 — Scanner Deduplication (origem do `MediaConflict` e dos `candidate_*_type`)

---

## Notas de Implementação

Mapeamento de vocabulário na borda (ACL), conceitualmente:

```python
# Borda TMDB → domínio. "tv" nunca entra em domínio/evento/persistência.
_TMDB_TO_MEDIA_TYPE = {"movie": MediaType.MOVIE, "tv": MediaType.SERIES}

def to_media_type(tmdb_kind: str) -> MediaType:
    try:
        return _TMDB_TO_MEDIA_TYPE[tmdb_kind]
    except KeyError as exc:
        raise DomainValidationException(
            message=f"Unknown TMDB media kind: {tmdb_kind!r}",
            message_code="UNKNOWN_TMDB_MEDIA_KIND",
            object_type="MediaType",
        ) from exc
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-31 | Lucas Cristovam | Criação inicial (Proposto) |
