# ADR-025: Reconciliação de Metadados de Provider é Concern de Application

**Status:** Aceito
**Data:** 2026-06-29
**Deciders:** Lucas
**Technical Story:** Backlog F-1 (`docs/audits/07-phase6-backlog.md`) — achado code-smell ALTO (conf 0.85): Anemic Domain Model + Shotgun Surgery na regra fill-if-empty dos use cases `enrich_movie/series_metadata`.

---

## Contexto

A auditoria de code-smells apontou (ALTO, conf 0.85) que a regra de reconciliação "provider ⇄ entidade" (fill-if-empty / overwrite) vive nos use cases `enrich_movie_metadata` e `enrich_series_metadata`, e não no domínio — caracterizando **Anemic Domain Model** (a entidade é um saco passivo de campos; o "como mesclar dados do provider" mora fora dela) e **Shotgun Surgery / Divergent Change** (adicionar um campo de metadado exigia editar os dois use cases).

A proposta literal da auditoria — um domain service `MetadataReconciler` ou `entity.merged_with(metadata, policy)` — esbarra num obstáculo arquitetural concreto e **já foi recusada duas vezes** em revisão (mr-review do #331 e nota explícita do Card D #345): a reconciliação **lê DTOs de port da camada de application** (`MediaMetadata`, `SeasonMetadata`, `EpisodeMetadata`, `CollectionMetadata`, `LocalizedTextFields` em `media/application/ports`). Um domain service ou método de entidade que recebesse esses DTOs faria `domain → application`, invertendo a regra de dependência do ADR-008.

A "regra de reconciliação", olhada de perto, são quatro responsabilidades distintas:

1. **Política de merge** (fill-if-empty vs overwrite) — **já está no domínio** (`MergePolicy.should_write` / `.overwrites`, extraída no #331).
2. **Classificação por-campo** — quais campos são always-overwrite, quais fill-if-empty, e guards especiais (duração probada nunca é sobrescrita; `end_year` é limpo no overwrite para não tropeçar no invariante `end_year >= start_year`; título de filme segue o TMDB enquanto o de série é scanner-derived).
3. **Tradução provider-DTO → VO de domínio** — `Title(...)`, `[Genre(g) ...]`, `ImageUrl(...)`, conversão de `CastMember`, mapeamento de `LocalizedFields`.
4. **Orquestração de coleções-filhas** — caminhar seasons → episodes, multi-segmento, índice TMDB.

Itens 3 e 4 são inerentemente de application/ACL. O item 1 já está no domínio. O ponto de fricção é só o item 2, e ele está expresso **em termos** do item 3 (lê a forma do DTO do provider).

## Decisão

Nós manteremos a reconciliação de metadados de provider na **camada de application**, e a tornaremos explícita como tal:

- O **domínio** é dono da *política* (`MergePolicy`) e dos *invariantes* (as entidades `Movie`/`Series`/`Season`/`Episode` validam na construção e em `with_*`).
- A **application** é dona da *preferência de fonte por-campo* entre valor armazenado e candidato do provider — porque essa preferência é definida sobre DTOs do provider (concern de ACL/tradução de fonte externa).
- A duplicação entre os dois use cases é consolidada num **reconciler compartilhado** (`media/application/use_cases/_metadata_field_merge.py`): `reconcile_common_fields` cobre os campos idênticos (ids do provider, o `COMMON_FILL_IF_EMPTY` partilhado por filme e série, cast e overlay localizado) num lugar só; cada use case sobrepõe apenas suas regras genuinamente divergentes de always-overwrite.

Não criaremos um `MetadataReconciler` no domínio nem um `entity.merged_with(metadata, ...)` que receba DTOs do provider, porque isso inverteria a regra de dependência do ADR-008.

## Consequências

### Positivas

- Adicionar um campo de metadado compartilhado por filme e série passa a ser uma edição em **um** lugar (`COMMON_FILL_IF_EMPTY`), eliminando o Shotgun Surgery / Divergent Change que motivou o achado.
- A regra de dependência (`modules → shared_kernel → building_blocks`, domínio não importa application) fica preservada e a decisão fica *discoverable* na base de ADRs — o item da auditoria não ressurge sem contexto.
- O domínio continua dono do que é de fato invariante (validação) e da política (`MergePolicy`); a fronteira fica nítida.

### Negativas

- A metade "Anemic Domain" do achado fica conscientemente **não-endereçada no sentido purista**: os guards por-campo (duração, end_year, identidade do título) continuam expressos na application, não como comportamento da entidade.
- O reconciler compartilhado é duck-typed (`entity: Any`) sobre Movie/Series — abre mão de checagem estática de tipo no acesso a `.cast`/`.localized` em troca de não duplicar a lógica por tipo.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| As regras de reconciliação crescerem (conflito por-campo, proveniência, estratégias por-campo) e a application virar o lugar errado | Baixa | Médio | Este ADR é o ponto de revisita (Strangler): se as regras enriquecerem, mover o item 2 para a entidade via VO de domínio (a application traduz DTO → VO; a entidade reconcilia) — sem inverter dependência |
| Um campo divergente ser adicionado por engano no mapa comum | Baixa | Baixo | `COMMON_FILL_IF_EMPTY` é só o subconjunto partilhado; extras type-specific ficam no use case; testes de enrich cobrem ambos os caminhos |

## Alternativas Consideradas

### 1. `MetadataReconciler` domain service / `entity.merged_with(metadata, policy)`

Mover a regra inteira para um domain service ou método de entidade que receba o DTO do provider.

**Rejeitado porque:** o DTO (`MediaMetadata` et al.) vive em `application/ports`; recebê-lo no domínio inverte `domain → application` (ADR-008). Já recusado em duas revisões (#331, #345).

### 2. VOs de "merge input" no domínio (`entity.merged_with(candidate_vo, policy)`)

A application traduz o DTO do provider em VOs de enrichment do domínio (`MovieEnrichment`, `SeriesEnrichment`, …); a entidade reconcilia sobre esses VOs.

**Rejeitado (por ora) porque:** introduz 4 VOs paralelos que espelham os campos opcionais das entidades — risco de só realocar o `MediaMetadata` para dentro do domínio sob outro nome, trocando "anêmico" por "domínio gordo", a custo alto em código core (enrich, data-mutating). Fica como o caminho de revisita se as regras crescerem.

### 3. Won't-fix puro

Fechar o item sem refactor, alegando que a política já está no domínio.

**Rejeitado porque:** deixaria o Shotgun Surgery (duplicação filme/série) de pé; a consolidação tem valor real e baixo risco.

## Referências

- ADR-008 (Screaming Architecture — módulos isolados, regra de dependência)
- ADR-009 (Cross-BC Read Ports) — para reads de domínio cross-BC, não é o caso aqui
- ADR-001 (Pydantic para Domain Models), ADR-017 (Invariantes na camada de domínio) — o domínio segue dono dos invariantes
- `src/modules/media/domain/value_objects/merge_policy.py` (`MergePolicy`, #331)
- `src/modules/media/application/use_cases/_metadata_field_merge.py` (reconciler compartilhado)
- `docs/audits/07-phase6-backlog.md` (item F-1) e `docs/audits/03-code-smells.md` (achado ALTO)

---

## Notas de Implementação

```python
# media/application/use_cases/_metadata_field_merge.py
COMMON_FILL_IF_EMPTY = {  # partilhado por filme e série
    "synopsis": ("synopsis", None),
    "genres": ("genres", lambda v: [Genre(g) for g in v]),
    ...
}

def reconcile_common_fields(entity, metadata, *, policy, fill_if_empty):
    updates = {}
    set_provider_ids(updates, metadata)              # tmdb_id / imdb_id / original_title
    set_if_missing(updates, metadata, entity, fill_if_empty, policy=policy)
    set_cast_if_missing(updates, metadata, entity, policy=policy)
    loc = merge_media_localized(entity.localized, metadata, policy=policy)
    if loc is not None:
        updates["localized"] = loc
    return updates

# enrich_movie_metadata.py — só o que diverge fica aqui
updates = reconcile_common_fields(movie, metadata, policy=policy,
    fill_if_empty={**COMMON_FILL_IF_EMPTY, "tagline": ..., "collection": ..., ...})
if metadata.title: updates["title"] = Title(metadata.title)   # movie: always-overwrite
...
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-29 | Lucas | Criação inicial |
