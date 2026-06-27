# HomeFlix — Auditoria de Arquitetura (Sumário Executivo)

**Data:** 2026-06-27 · **Modo:** READ-ONLY (nenhum código alterado, nenhum commit) · **Branch:** `develop`

Auditoria multidimensional do backend, varrida **módulo a módulo** sobre os seis
alvos solicitados — `media`, `library`, `watch_progress`, `collections`,
`building_blocks`, `shared_kernel`. Cinco dimensões, uma skill (ou conjunto de
princípios) por dimensão. Cada achado tem `arquivo:linha`, severidade, root cause,
skill que detectou e confiança nos relatórios por dimensão.

> **Escopo.** O projeto tem **9 módulos** (`catalog_requests`, `identity`,
> `notifications`, `preferences`, `settings` além dos seis). Mantive o foco nos
> seis pedidos; arestas *de entrada* desses outros módulos sobre os seis foram
> contabilizadas (acoplamento, eventos, `UserModel`), mas seus internos não foram
> varridos. Recomendo uma segunda passada cobrindo-os.

## Relatórios por dimensão

| # | Dimensão | Skill / método | Arquivo | Achados |
|---|----------|----------------|---------|---------|
| 01 | Clean Architecture / DDD | `homeflix-arch` + `clean-arch-python` | [`01-clean-architecture.md`](01-clean-architecture.md) | 13 |
| 02 | ACL / adapters / gateways | princípios ADR-009 (sem skill dedicada) | [`02-acl-adapters.md`](02-acl-adapters.md) | 7 |
| 03 | Code smells (modelagem) | `code-smell-review` | [`03-code-smells.md`](03-code-smells.md) | 22 |
| 04 | Acoplamento (Strength×Distance×Volatility) | framework (sem skill dedicada) | [`04-coupling.md`](04-coupling.md) | 10 |
| 05 | Doc drift | `doc-drift-audit` | [`05-doc-drift.md`](05-doc-drift.md) | 10 |

**Total bruto: 62 achados** — 🔴 **3 crítico** · 🟠 **11 alto** · 🟡 **31 médio** · 🔵 **17 baixo**.

> **Atenção à sobreposição:** as três dimensões estruturais (01, 04, 05) enxergam
> em grande parte **os mesmos defeitos** por lentes diferentes. Os atalhos cross-BC
> do `media` aparecem em 01 *e* 04 *e* 05. A contagem "62" é por-lente, não por
> defeito distinto. Defeitos raiz distintos ≈ **40**. Os temas abaixo deduplicam.

---

## Veredito geral

A base está **arquiteturalmente saudável no núcleo**: `building_blocks/domain` e
`shared_kernel` não têm dependências para fora (verificado, zero ocorrências); o
domínio está livre de FastAPI/SQLAlchemy; os agregados de ciclo de vida
(`WatchProgress`, `Library`, `CustomList`, `Season`/intro, `MediaConflict`) são
ricos, não anêmicos; e onde o **ADR-009 foi seguido** (watch_progress/collections →
media via `media_lookup_port` + ACL) o isolamento é exemplar (12 adapters ACL, 24
ports, defaults deny-all corretos).

A dívida é **localizada e convergente**: concentra-se no módulo **`media`** (o maior,
~34k LOC) e em **leituras cross-BC adicionadas tardiamente** que recorreram a
atalhos em vez do mecanismo que o próprio projeto define. Não há ciclos de import
entre módulos. Não há violação crítica de direção de dependência no núcleo.

---

## Temas transversais (priorizados — atacar nesta ordem)

### 🔴 TEMA A — Ausência de mecanismo de integração cross-BC consistente
**Corroborado por:** Clean Arch (F1/F2/F3 alto) · Coupling (F1 crítico, F2/F3 alto) · Doc-drift (#2 alto)
**Epicentro:** `media`. **Root cause único:** o ADR-009 (Read Port + ACL + DTO)
foi seguido nas primeiras leituras cross-BC; as posteriores pegaram atalhos. O
pacote `src/shared_kernel/integration_events/` foi previsto mas está **vazio** — a
abstração de contrato de integração nunca foi construída, então cada consumidor
improvisou.

Defeitos que compõem o tema:
- `media/application/services/scan_run_service.py:21` — importa a **entidade de
  domínio `Library`** de outro BC e a passa para `run_scan()` (acoplamento
  intrusivo; **F1 crítico de coupling**).
- `media/application/use_cases/get_overview_stats.py:3` e `trigger_scan.py:6` —
  pegam emprestadas `IdentityUnitOfWorkFactory` / `LibraryUnitOfWorkFactory` em vez
  de Read Port (a própria docstring de `get_overview_stats` admite o atalho).
- `watch_progress`/`collections` `event_handlers/*.py` — assinam as **classes de
  domain event internas** de `media`/`identity` (5 consumidores), sem contrato de
  integration event.
- `UserModel` (ORM do identity) **vaza para ~20 sites de rotas** em 5 módulos via o
  crosscut de auth (deveria retornar DTO).

**Direção de correção:** materializar `shared_kernel/integration_events` com
contratos versionados; promover as três leituras de `media` a Read Ports + ACL;
trocar `UserModel` por um `AuthenticatedUser` DTO no crosscut de auth. É a maior
alavanca de redução de risco da base.

### 🔴 TEMA B — Metadados localizados como `dict` não-tipado (corrupção silenciosa)
**Corroborado por:** Code-smell (#1 **crítico**) · Doc-drift (gap: iniciativa sem ADR)
`localized: dict[str, dict[str, Any]]` com chaves mágicas, espalhado por 4
entidades (`movie`/`series`/`episode`/`season`) + use cases de enrich, persistido e
relido via SQL `json_extract`. Uma chave digitada errado **nunca dá round-trip e
falha em silêncio** — e isso **já aconteceu** (tagline perdida entre as variantes
movie/series, conforme a própria docstring). A iniciativa de localização (config-
driven, season/episode, catalog-requests, ordenação) é transversal e **não tem ADR**.

**Direção:** extrair um VO `LocalizedMetadata`; escrever o ADR da localização.

### 🟠 TEMA C — Política de negócio e perda de sinal nos gateways de provider do `media`
**Corroborado por:** ACL (4 médios) · Code-smell (boolean blindness `force`)
A ACL de metadados decide regras que pertencem ao domínio / descarta sinal do
provider:
- `tmdb_client.py:1096,1153` — **jurisdição de content-rating hardcoded** (`BR or
  US`), colapsando as demais.
- `tmdb_client.py:266-292` — `HTTPError`/não-200 colapsam no **mesmo `None` de um
  404 real** (provider-down vira "não encontrado"); inconsistente com os paths de
  search que fazem `raise_for_status()`.
- `media_probe_service.py:403-405` — probe **fabrica** uma disposição de áudio
  default (`tracks[0]`) que o container nunca declarou (concern do `TrackSelector`
  da Library).
- `scanner.py:160-161` — raiz desmontada/ausente **pulada em silêncio**,
  indistinguível de raiz vazia (reconcile poderia ler "disco desmontado" como
  "tudo deletado").
- `force: bool` atravessa ~12 funções de enrich bifurcando fill-vs-overwrite de
  forma invisível → `MergePolicy` enum.

### 🟠 TEMA D — Drift em documentação fundacional (engana quem implementa)
**Corroborado por:** Doc-drift (#1 crítico, #3 alto, + médios)
- **CLAUDE.md ensina o envelope de response errado** (`{"data","meta",request_id no
  body}`) vs. o real `responses.py:73,101` (`{"type","data","metadata"}`,
  `request_id` em header). 🔴
- `PresentationException` + 3 subclasses **totalmente documentadas** em
  `exception-hierarchy-clean-architecture.md:128,867-943` mas **inexistentes** no
  código (`grep` zero). 🟠
- Listas de módulos/BC mostram **4, a realidade é 9** (CLAUDE.md e ADR-008 com a
  árvore desatualizada — contradição interna com a própria seção "Fase Atual").
- **i18n docs descrevem um sistema que não existe** (`i18n/locales/{en,pt-BR}/` +
  Accept-Language); o real é query param `lang` + `get_title(lang)` config-driven.
- Contagens estagnadas: endpoints 107→**132 reais**; testes 2530→**2941 reais**.

### 🟠 TEMA E — Regra de merge provider⇄entidade anêmica e repetida (Shotgun Surgery)
**Corroborado por:** Code-smell (#2 alto)
A regra de merge metadado-provider está **copiada ~23×** em
`enrich_movie/series_metadata.py`; `Movie`/`Series` não têm `merged_with`. Uma
mudança na regra obriga edição em muitos pontos. → domain service `MetadataReconciler`.

### 🟡 TEMA F — Primitive Obsession em fronteiras de idioma e em request models
**Corroborado por:** Code-smell (#4 alto + médios)
`lang: str = "en"` cru em ~20 accessors de entidade + 14 use cases enquanto
`LanguageTag`/`LanguageCode` existem **sem uso** (tag inválida cai no fallback em
silêncio). Library aceita `list[dict[str, Any]]` na borda. Candidatos a VO:
`Confidence [0,1]`, modelos de request tipados.

---

## Lista mestra por severidade (top do funil)

### 🔴 Crítico (3 defeitos raiz distintos)
1. **Coupling F1** — `media/application/services/scan_run_service.py:21` importa o
   agregado `Library` de outro BC. *(Tema A)*
2. **Code-smell #1** — `localized: dict[str, dict[str, Any]]` em 4 entidades; já
   causou perda de dado silenciosa. *(Tema B)*
3. **Doc-drift #1** — `CLAUDE.md` documenta envelope de response incompatível com
   `responses.py`. *(Tema D)*

### 🟠 Alto (núcleo, deduplicado)
- Atalhos de UoW cross-BC: `get_overview_stats.py:3`, `trigger_scan.py:6` *(Tema A)*
- 5 consumidores assinam domain events crus; `integration_events` vazio *(Tema A)*
- `UserModel` ORM em ~20 sites de rotas *(Tema A)*
- `force: bool` (boolean blindness) em ~12 funções de enrich *(Tema C)*
- Regra de merge copiada ~23× / entidades sem `merged_with` *(Tema E)*
- `lang: str` cru com VOs existentes não usados *(Tema F)*
- `PresentationException` documentada mas inexistente *(Tema D)*

*(Médios e baixos — 48 itens — detalhados nos relatórios por dimensão.)*

---

## Ordem de ataque recomendada

1. **Doc-drift de alta alavancagem, baixo custo** (Tema D): corrigir o envelope no
   CLAUDE.md, o `PresentationException` fantasma, as listas de módulos e o i18n.
   Barato, evita que novos PRs herdem o erro. *(horas)*
2. **VO `LocalizedMetadata` + ADR de localização** (Tema B): estanca corrupção
   silenciosa ativa. *(dias)*
3. **Mecanismo de integração cross-BC** (Tema A): `integration_events` + promover as
   3 leituras de `media` a Read Port/ACL + `AuthenticatedUser` DTO. Maior redução de
   risco estrutural. *(dias–semanas; faseável)*
4. **Limpeza dos gateways de provider** (Tema C) e **`MetadataReconciler`** (Tema E):
   movem política para o domínio e param a perda de sinal. *(dias)*
5. **Primitive Obsession de idioma** (Tema F): incremental, casa com o passo 2.

> **Nota sobre acoplamento bom:** o `shared_kernel` (~14 arquivos) e
> `building_blocks` (~23) ainda são pequenos e estáveis — **não** estão virando
> dumping ground. Manter assim ao materializar os integration events (contratos
> finos, não modelos de domínio compartilhados).
