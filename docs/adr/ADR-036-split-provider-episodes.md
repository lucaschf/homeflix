# ADR-036: Episódios do Provider Divididos em Vários Arquivos

**Status:** Aceito
**Data:** 2026-10-01
**Deciders:** Lucas
**Technical Story:** Desenhos que exibem duas histórias por faixa de horário (ex.: `Sagwa The Chinese Siamese Cat (2001)`) são listados pelo TMDB como **40 episódios** titulados `"A / B"`, mas a coleção local tem **um arquivo por história** — 80 arquivos.

---

## Contexto

O [ADR-030](ADR-030-multi-episode-file-segments.md) trata **1 arquivo → N episódios do provider** (minissérie em um `.mkv`; e, no enrich, títulos locais `"A - B"` que somam N episódios do TMDB). Este ADR trata o caso inverso, **N arquivos → 1 episódio do provider**:

```
TMDB  S01E09  "Cat and Mouse / Stinky Tofu"
local S01E17  "Gato e Rato"        ← história 1 de E09
local S01E18  "O Queijo Fedido"    ← história 2 de E09
```

Sem tratamento, o enrich casa o local E17 com o TMDB E17 (outra faixa) e os locais E41–E80 ficam sem metadado algum.

## Decisão

**Detectar a divisão no enrich, sem mudar o modelo.** Cada arquivo local continua sendo um `Episode` próprio (identidade `(temporada, número)` intacta, com progresso, intro e créditos por história). Muda só o mapeamento local → provider, em `enrich_series_metadata.py`:

1. **Detecção** (`_detect_split_factor`): a temporada é dividida em `k` (2 a 4) quando
   - o maior número local cabe em `k` arquivos por episódio do provider (`count·(k−1) < max_local ≤ count·k`), **e**
   - a maioria dos títulos do provider tem exatamente `k` partes separadas por `" / "`.

   A contagem sozinha não basta: uma listagem incompleta no TMDB produziria a mesma razão. O separador `" / "` é o mesmo que o TMDB usa para essas faixas e que o ADR-030 usa ao combinar segmentos.
2. **Mapeamento**: o local `n` é a história `(n−1) % k` do episódio `(n−1) // k + 1`. É ancorado no número local, então um arquivo faltando não desloca os vizinhos.
3. **Campos**: o título (base e localizados) é a parte correspondente de `"A / B"`. Um título sem partes (ex.: especial em duas partes) recebe o sufixo `(Part n)`. A duração é dividida por `k`. Sinopse, still e data descrevem a faixa inteira e são compartilhados. As travas fill-if-empty / `MergePolicy` continuam as mesmas de um episódio simples.

### Convenção de nomenclatura

O número local deve seguir a ordem do provider: `S01E01`/`S01E02` = histórias 1 e 2 do E01 do TMDB. Coleções dubladas com outra ordem precisam ser renumeradas.

## Consequências

### Positivas

1. Sem migration, sem mudança de API nem de frontend.
2. Um arquivo por história preserva navegação, progresso e marcadores por história.
3. Retrocompatível: uma temporada que não satisfaz as duas condições segue exatamente o caminho anterior.

### Negativas

1. É uma heurística. Uma série cujo TMDB lista metade dos episódios com títulos `"A / B"` por outro motivo seria dividida por engano.
2. A sinopse é da faixa inteira, então as duas histórias mostram o mesmo texto.
3. Depende da ordem local bater com a do provider; não há como declarar o mapeamento manualmente.

## Alternativas Consideradas

### 1. Partes no nome do arquivo (`S01E09-pt1`, `S01E09-pt2`)

**Rejeitado porque:** exige `part` na identidade do `Episode` (`(temporada, número, parte)`), o que atravessa scanner, persistência (unique index), rotas por número de episódio, watch progress e o frontend — para um caso de enrich.

### 2. Concatenar os arquivos em um por episódio do provider

**Rejeitado porque:** destrutivo, manual por série, e perde a granularidade por história.

### 3. Fator de divisão configurado por série (admin)

**Adiado:** resolveria o falso positivo da heurística, mas exige campo no agregado, migration e endpoint. Revisitar se a detecção errar na prática.

## Referências

- [ADR-030](ADR-030-multi-episode-file-segments.md) — caso inverso (1 arquivo → N episódios)
