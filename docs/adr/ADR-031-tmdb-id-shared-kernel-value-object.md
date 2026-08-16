# ADR-031: TmdbId como Value Object no Shared Kernel

**Status:** Aceito
**Data:** 2026-08-16
**Deciders:** Lucas Cristovam
**Technical Story:** Roadmap 2.2 (Primitive Obsession) — follow-up do audit do bounded context `catalog_requests`, após a migração `poster_url → ImageUrl` (PR #381). Continuação incremental do ADR-018.

---

## Contexto

O identificador numérico do TMDB (`tmdb_id`) é a referência externa que amarra o catálogo aos metadados. Ele já é modelado como Value Object — `TmdbId(IntValueObject)`, em `src/modules/media/domain/value_objects/tmdb_id.py`, que valida "inteiro positivo" — e está **plenamente adotado no bounded context `media`**: `Movie.tmdb_id` e `Series.tmdb_id` são `TmdbId | None`, e os mappers/use cases (`get_collection_by_tmdb_id`, `relink_movie`, `relink_series`, `promote_movie_to_series`, `_metadata_field_merge`) operam sobre o VO.

Fora do `media`, porém, o mesmo conceito ainda trafega como primitivo:

- `CatalogRequest.tmdb_id` é `int` cru (e `collection_tmdb_id: int | None` idem). Toda a família de use cases e DTOs de `catalog_requests` fala `int`.
- A validação "positivo" não é aplicada nesse contexto: nada impede um `tmdb_id=0` ou negativo de ser persistido.

A causa de o `catalog_requests` não reusar o VO é estrutural, não de descuido: o `TmdbId` vive **dentro** do módulo `media`, e a regra de dependência do projeto (CLAUDE.md; ADR-008) proíbe um módulo importar de outro (`modules → shared_kernel → building_blocks`). Para `catalog_requests` consumir o VO seria preciso ou (a) importar de `media` — proibido — ou (b) duplicar o VO — divergência de validação garantida.

O `shared_kernel/value_objects` já é, por precedente, a casa dos conceitos de valor que **múltiplos** contextos compartilham: `MediaType` e `ImageUrl` (ambos usados por `media` e `catalog_requests`), além dos identificadores `MediaId`, `MovieId`, `SeriesId`, `UserId`, `LibraryId`. O `TmdbId` é exatamente dessa natureza — uma referência externa cross-cutting — mas ficou alojado num único módulo por ter nascido lá primeiro.

O ADR-018 já ratificou a regra geral ("identificadores de domínio como Value Objects nas fronteiras") e listou explicitamente o `catalog_requests` como dívida diferida (bucket Strangler-Fig). Este ADR resolve o passo que falta para o `tmdb_id`: **onde o VO deve morar** para poder ser adotado sem violar a fronteira de módulos.

> **Nota:** a decisão aqui **não** é "criar o VO `TmdbId`" — esse VO já existe e está em uso. A decisão é **promovê-lo ao shared kernel** e adotá-lo nos demais contextos que falam TMDB.

## Decisão

Nós iremos **mover o `TmdbId` de `src/modules/media/domain/value_objects/` para `src/shared_kernel/value_objects/`** e exportá-lo no `__all__` do pacote, tornando-o o VO canônico e único para o identificador do TMDB em todo o sistema.

Em seguida, adotá-lo nos contextos que hoje usam o primitivo, de forma incremental (Strangler-Fig), seguindo o mesmo padrão já aplicado em `poster_url → ImageUrl` (PR #381):

1. **`media`** passa a re-exportar o `TmdbId` do `shared_kernel` no seu pacote `domain/value_objects/__init__.py` — exatamente como já faz com `FilePath`, `ImageUrl` e `MediaId`. Com isso, os importadores internos do `media` (entities, mappers, use cases) que fazem `from ...media.domain.value_objects import TmdbId` continuam funcionando sem alteração.
2. **`catalog_requests`** passa a tipar `CatalogRequest.tmdb_id` como `TmdbId` (e `collection_tmdb_id: TmdbId | None`), com um `@field_validator(mode="before")` que normaliza o `int` recebido no boundary — igual ao validador de `poster_url`.
3. **As bordas permanecem `int`**: a coluna do banco, os DTOs de Input/Output e os schemas HTTP continuam `int`. A conversão para o VO acontece uma única vez ao cruzar para o domínio; o mapper e o `from_entity` desembrulham via `.value`.

O `payload` JSON opaco de `notifications` (que carrega `tmdb_id` como parte de um dict de deep-link) **não** é alvo desta migração — não é um campo tipado do domínio, e sim um blob de transporte.

## Consequências

### Positivas

- Um único ponto de validação para "TMDB id válido" em todo o sistema; `catalog_requests` passa a rejeitar ids não-positivos, hoje aceitos.
- Elimina a impossibilidade estrutural: `catalog_requests` reusa o VO sem importar de `media` e sem violar a regra de dependência (ADR-008).
- Consistência com o precedente já estabelecido (`MediaType`, `ImageUrl` no shared kernel) — a linguagem ubíqua do TMDB fica no lugar previsível.
- Avança um item concreto do roadmap 2.2 e do bucket diferido do ADR-018, mantendo o padrão de migração pequeno e revisável.

### Negativas

- O `shared_kernel` cresce com mais um VO — precisa permanecer genuinamente cross-BC (é, pois `media` + `catalog_requests` o usam) para não virar depósito.
- O pacote `media.domain.value_objects` passa a re-exportar mais um VO do shared kernel — porém isso já é convenção do arquivo (`FilePath`, `ImageUrl`, `MediaId`), então não introduz padrão novo.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Import quebrado após a movimentação | Baixa | Baixo | Gate de `mypy src` (0 erros) + suíte já pega qualquer import solto antes do merge. |
| Divergência transitória (VO em dois caminhos) durante a migração | Baixa | Baixo | Fazer a movimentação e a atualização dos imports do `media` no **mesmo** PR; nada de re-export permanente. |
| VO acabar usado por um só BC no fim (não justificar shared kernel) | Baixa | Médio | Só promover porque há ≥2 consumidores reais (`media` e `catalog_requests`); se `catalog_requests` não migrasse, a promoção não se justificaria. |

## Alternativas Consideradas

### 1. Manter `TmdbId` privado do `media` e duplicar um VO em `catalog_requests`

Cada módulo teria seu próprio `TmdbId`.

**Rejeitado porque:** duplica a regra de validação em dois lugares que inevitavelmente divergem, contradizendo o motivo de o conceito ser um VO. É o anti-padrão que o ADR-018 combate.

### 2. `catalog_requests` importar `TmdbId` direto de `media`

Reusa o VO existente sem movê-lo.

**Rejeitado porque:** viola a regra de dependência entre módulos (ADR-008; CLAUDE.md) e acopla os dois bounded contexts por um caminho de import — exatamente o que a arquitetura de módulos evita.

### 3. Deixar `tmdb_id` como `int` no `catalog_requests`

Aceitar o primitivo fora do `media`.

**Rejeitado porque:** é o Primitive Obsession que o roadmap 2.2 quer eliminar; mantém a validação ausente nesse contexto (aceita id ≤ 0) e a assimetria "VO no `media`, `int` no resto".

### 4. Criar um novo `TmdbId` do zero no shared kernel

Escrever o VO como se não existisse.

**Rejeitado porque:** o VO já existe e é adequado (`IntValueObject`, valida positivo); recriá-lo descartaria histórico e testes. A ação correta é mover, não reescrever.

## Referências

- ADR-008: Screaming Architecture com Módulos (regra de dependência entre módulos)
- ADR-018: Identificadores de domínio como Value Objects nas fronteiras (regra geral; bucket diferido)
- PR #381: `refactor(catalog-requests): type poster_url as ImageUrl VO` (padrão de migração espelhado aqui)
- `docs/roadmap.md` — item 2.2 (Primitive Obsession)

---

## Notas de Implementação

**Movimentação (passo 1):** o arquivo é movido sem alteração de conteúdo.

```
git mv src/modules/media/domain/value_objects/tmdb_id.py \
       src/shared_kernel/value_objects/tmdb_id.py
```

`src/shared_kernel/value_objects/__init__.py` passa a exportar `TmdbId`. Em `media`, apenas o
`domain/value_objects/__init__.py` muda: a linha que importava o VO do módulo local passa a importá-lo
do shared kernel (`from src.shared_kernel.value_objects.tmdb_id import TmdbId`), mantendo o VO no `__all__`
como re-export — idêntico ao que o arquivo já faz com `FilePath` e `ImageUrl`. Os importadores internos do
`media` não mudam. `catalog_requests` importa direto de `src.shared_kernel.value_objects` (não pode usar o
re-export do `media`, por ser cross-module).

**Adoção em `catalog_requests` (passo 2), espelhando `poster_url`:**

```python
from src.shared_kernel.value_objects import TmdbId

class CatalogRequest(AggregateRoot[CatalogRequestId]):
    tmdb_id: TmdbId
    collection_tmdb_id: TmdbId | None = None

    @field_validator("tmdb_id", "collection_tmdb_id", mode="before")
    @classmethod
    def _convert_tmdb_id(cls, v: int | TmdbId | None) -> TmdbId | None:
        if v is None or isinstance(v, TmdbId):
            return v
        return TmdbId(v)
```

**Bordas continuam `int`:** o mapper desembrulha com `entity.tmdb_id.value` (e `collection_tmdb_id.value if … else None`); `to_entity` passa o `int` cru e o validador converte. Os DTOs e schemas HTTP não mudam.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-08-16 | Lucas Cristovam | Criação inicial |
