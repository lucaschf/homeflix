# ADR-023: Metadados Localizados como Value Object

**Status:** Aceito
**Data:** 2026-06-27
**Deciders:** Lucas
**Technical Story:** Auditoria de arquitetura (achado crítico de modelagem) — `docs/audits/03-code-smells.md` e `06-remediation-plan.md` (Fase 2)

---

## Contexto

A iniciativa de localização (ADR sem registro até aqui — config-driven via
`settings.supported_locales`, enriquecimento TMDB por locale, ordenação/busca
localizadas) materializou os metadados por idioma das quatro entidades de conteúdo
(`Movie`, `Series`, `Season`, `Episode`) como um **dicionário aninhado não-tipado**:

```python
# src/modules/media/domain/entities/movie.py
localized: dict[str, dict[str, Any]] = Field(default_factory=dict)
```

A forma persistida é um JSON chaveado por locale, com **chaves internas mágicas**:

```json
{
  "en":    {"title": "...", "synopsis": "...", "tagline": "...",
            "genres": ["..."], "logo_path": "...", "poster_path": "...",
            "backdrop_path": "..."},
  "pt-BR": {"title": "...", "synopsis": "..."}
}
```

(`Movie`/`Series` usam o conjunto completo; `Season`/`Episode` só `title`/`synopsis`.)

Esse dado atravessa o sistema inteiro como `dict`/`Any`:

1. **Domínio** — ~24 acessores do tipo
   `str(self.localized.get(lang, {}).get("title") or self.title.value)`, com o
   parâmetro `lang: str = "en"` cru (os VOs `LanguageTag`/`LanguageCode` existem mas
   não são usados aqui).
2. **Aplicação** — montado/mesclado em funções soltas
   (`_localized_metadata_helpers.merge_localized_metadata` / `build_localized_text`),
   parametrizadas por um `force: bool`.
3. **Persistência** — serializado com `json.dumps(entity.localized)` no mapper
   (coluna `Text`) e **relido via SQL** `json_extract(localized, '$.<lang>.title')`
   para ordenação localizada e projeção de busca.

### Problema

`Any` desliga o type checker exatamente sobre um dado **persistido e relido por
caminho SQL que depende de strings literais**. Uma chave interna ou de locale
digitada errada grava dado que **silenciosamente nunca faz round-trip na leitura** —
corrupção de dado persistido sem erro. Isso **já ocorreu**: as variantes movie/series
do merge divergiram (a de movie carregava `tagline`, a de series a descartava),
conforme registra o docstring de `_localized_metadata_helpers`. A regra de fallback
("localizado, senão o campo base") está duplicada em ~24 acessores; as chaves mágicas
vivem em três camadas independentes (acessor, helper de merge, SQL `json_extract`).

A auditoria classificou este como o único achado **crítico** de modelagem.

## Decisão

**Introduziremos um Value Object `LocalizedMetadata` para representar os metadados
por idioma, eliminando o `dict[str, dict[str, Any]]` da camada de domínio e de
aplicação.** A serialização para `dict`/JSON acontece **apenas na borda de
persistência**.

Desenho:

- Um registro por-locale tipado (`LocalizedFields`) com todos os campos **opcionais**
  (`title`, `synopsis`, `tagline`, `genres`, `logo_path`, `poster_path`,
  `backdrop_path`). Entidades leves (`Season`/`Episode`) simplesmente não preenchem
  artwork/genres — o mesmo tipo serve às duas formas.
- Um contêiner `LocalizedMetadata` mapeando **`LanguageTag` → `LocalizedFields`**,
  com:
  - acessores de leitura com fallback **centralizado num único lugar**
    (`get(field, lang)` / `title_for(lang, default)` etc.);
  - `merge(other, policy)` para fundir overrides do provider (substitui a lógica
    espalhada dos helpers; o `policy` antecipa o `MergePolicy` da Fase 4, ADR a
    seguir);
  - `to_serializable()` / `from_serializable()` para a borda de persistência.
- Os acessores de entidade passam a aceitar `LanguageTag` (coagindo a string crua
  **uma vez** na borda).

### Fonte única dos nomes de campo JSON (acoplamento wire ↔ SQL)

As chaves internas (`"title"`, `"synopsis"`, `"tagline"`, `"genres"`, `"logo_path"`,
`"poster_path"`, `"backdrop_path"`) ficam definidas **num único lugar** — um
`StrEnum` `LocalizedField` no módulo do VO — e são a **única** fonte dessas strings
em todo o código:

- o VO usa `LocalizedField` ao serializar/desserializar (os nomes dos campos do
  Pydantic casam com esses valores);
- os construtores de path do `json_extract` **importam** `LocalizedField` em vez de
  hardcodar `"$.{lang}.title"`. Hoje essas projeções vivem em
  `infrastructure/persistence/repositories/_genre_helpers.py`
  (`localized_title_for`, `localized_title_sort_key`); passam a montar o path a
  partir de `LocalizedField.TITLE.value`.

O acoplamento wire↔SQL é inerente ao `json_extract` e não desaparece; mas fica
concentrado numa **única constante compartilhada**, então renomear/adicionar um campo
é mudança num só símbolo e o lado SQL não pode driftar em silêncio do domínio.

### Invariante de compatibilidade (sem migration)

`to_serializable()` produz **exatamente** o mesmo JSON de hoje:

- chave externa = `LanguageTag.value` (canônico: `"en"`, `"pt-BR"`), idêntico às
  chaves atuais geradas a partir de `supported_locales`;
- chaves internas = as mesmas strings literais;
- campos falsy/ausentes são omitidos (preserva o comportamento "só o que o provider
  retornou").

Assim os `json_extract(localized, '$.<lang>.title')` de ordenação/busca continuam
funcionando **sem alterar schema nem dados** — não há migration.

## Consequências

### Positivas

- Estado ilegal deixa de ser representável: chave/locale inválido falha na
  construção do VO, não silenciosamente na leitura SQL.
- Chaves mágicas e regra de fallback passam a ter **uma única fonte da verdade**
  (hoje espalhadas por ~24 acessores + 2 helpers + N `json_extract`).
- Acaba a divergência movie/series (o merge vive no VO, aplicado uniformemente).
- `LanguageTag` normaliza o locale na borda (`"PT-br"` → `"pt-BR"`), eliminando o
  bug de chave não-casada do `lang: str` cru.
- **Sem migration** (wire JSON preservado).

### Negativas

- Mais código (o VO + serializadores) e uma camada de conversão na fronteira de
  persistência.
- O `json_extract` no SQL continua acoplado às strings das chaves — o VO **reduz**
  o risco ao concentrá-las no `StrEnum` `LocalizedField` que tanto o VO quanto as
  projeções SQL importam (ver "Fonte única dos nomes de campo JSON"), mas não
  elimina o acoplamento wire↔SQL: renomear um campo é uma mudança num só símbolo,
  porém ainda atravessa domínio + persistência.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Dados legados com chave de locale não-canônica (ex.: `"pt-br"`) deixam de casar após normalização via `LanguageTag` | Baixa | Médio | `supported_locales` default já é canônico (`en`, `pt-BR`); teste de round-trip sobre o dump real; se aparecer, normalizar na desserialização (`from_serializable`) |
| Regressão silenciosa na ordenação/busca por divergência VO↔`json_extract` | Média | Alto | Chaves no `StrEnum` `LocalizedField` importado pelos dois lados; teste de integração cobrindo `json_extract` + acessores do VO sobre o mesmo dado |
| Round-trip encontra chave interna desconhecida (corrupção / bug do writer) | Baixa | Médio | `from_serializable` **rejeita** chaves desconhecidas (`extra="forbid"`, ver decisão abaixo) — falha explícita em vez de perda silenciosa; teste de fidelidade dump→load→dump |

## Alternativas Consideradas

### 1. Manter `dict[str, dict[str, Any]]`

Forma atual.

**Rejeitado porque:** é a causa raiz da corrupção silenciosa já observada (drift de
`tagline`) e do bypass de type checking sobre dado persistido.

### 2. Colunas separadas por locale/campo (ou tabela `localized_metadata`)

Normalizar para colunas/linhas em vez de JSON.

**Rejeitado porque:** exige migration e faz o schema explodir por locale × campo ×
entidade; perde a flexibilidade config-driven de `supported_locales`; o ganho de
integridade é alcançável pelo VO sem tocar o banco.

### 3. `TypedDict` em vez de Value Object

Tipar a forma com `TypedDict`.

**Rejeitado porque:** `TypedDict` não valida em runtime (a chave errada ainda
round-trips), não centraliza fallback/merge como comportamento, e mantém o locale
como `str` cru — não resolve o acoplamento de chaves stringly-typed do `json_extract`.

## Referências

- `docs/audits/03-code-smells.md` — achado crítico (Stringly-Typed + Anemic).
- `docs/audits/06-remediation-plan.md` — Fase 2 (PR-2.1/2.2/2.3).
- ADR-001 (Pydantic para Domain Models), ADR-016/018 (VOs nas fronteiras).
- `src/shared_kernel/value_objects/language_tag.py` (chave do VO).

---

## Notas de Implementação

Forma alvo (conceitual):

```python
class LocalizedField(StrEnum):
    """Fonte única dos nomes de campo no JSON `localized` — VO e SQL importam daqui."""
    TITLE = "title"
    SYNOPSIS = "synopsis"
    TAGLINE = "tagline"
    GENRES = "genres"
    LOGO_PATH = "logo_path"
    POSTER_PATH = "poster_path"
    BACKDROP_PATH = "backdrop_path"


class LocalizedFields(ValueObject):
    # nomes dos campos == LocalizedField.values; extra="forbid" herdado de ValueObject
    title: str | None = None
    synopsis: str | None = None
    tagline: str | None = None
    genres: tuple[str, ...] = ()
    logo_path: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None

class LocalizedMetadata(ValueObject):
    by_locale: Mapping[LanguageTag, LocalizedFields]

    def title_for(self, lang: LanguageTag, default: str) -> str: ...
    def merge(self, other: "LocalizedMetadata", policy: MergePolicy) -> "LocalizedMetadata": ...
    def to_serializable(self) -> dict[str, dict[str, Any]]: ...   # mesmo JSON de hoje
    @classmethod
    def from_serializable(cls, raw: dict[str, dict[str, Any]] | None) -> "LocalizedMetadata": ...
```

### Estratégia de campos desconhecidos no `from_serializable` (decisão)

`from_serializable` **rejeita** chaves internas desconhecidas — `LocalizedFields`
herda `extra="forbid"` (convenção de `DomainModel`/`ValueObject` no projeto), então
uma chave que não esteja em `LocalizedField` levanta erro na desserialização. Não
preservamos campos não-modelados num "saco de extras".

Justificativa: o writer é **inteiramente controlado** (só o enrich grava `localized`,
sempre com esse conjunto fechado de chaves), então uma chave inesperada é **bug/
corrupção, não dado legítimo** — falhar explícito está alinhado à própria razão
desta ADR (acabar com a perda silenciosa) e à postura estrita do codebase. Locales
**novos** continuam aceitos livremente (são chaves do mapa externo, não campos do
registro).

Caveat de compatibilidade futura (expand/contract): para adicionar um 8º campo,
primeiro mergeie o campo opcional no `LocalizedField`/`LocalizedFields` (readers
toleram), só depois faça o writer emiti-lo — nunca emita antes do reader conhecer a
chave, senão a leitura em código antigo falha (forbid).

Faseamento (Fase 2 do plano):

- **PR-2.2** — introduzir o VO + caminho de **leitura** (acessores das 4 entidades
  via VO; `LanguageTag` nos acessores), mantendo o JSON idêntico na persistência.
- **PR-2.3** — caminho de **escrita** do enrich via VO (substitui o achatamento dos
  helpers).
- O `merge(policy)` é consumido pelo `MetadataReconciler` da **Fase 4** (ADR
  próprio), que troca o `force: bool` por `MergePolicy`.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-27 | Lucas | Criação inicial |
