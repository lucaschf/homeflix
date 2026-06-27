# 📑 Doc Drift Audit — HomeFlix backend (snapshot)

| | |
|---|---|
| **Projeto** | HomeFlix (backend) |
| **Modo** | Auditoria de snapshot (READ-ONLY) — repo inteiro, não diff |
| **Escopo** | ADRs 001–022, `docs/standards/*`, `.claude/CLAUDE.md`, `docs/roadmap.md`, docstrings (spot-check) vs. `src/` |
| **Branch** | develop @ 25b5211 |
| **Skill** | doc-drift-audit |
| **Drift encontrado** | 10 achados (8 confiança ≥ 0.8) |

## Tabela de severidade

| Severidade | Qtde |
|---|---|
| 🔴 Crítico | 1 |
| 🟠 Alto | 2 |
| 🟡 Médio | 5 |
| 🔵 Baixo | 2 |
| **Total** | **10** |

---

## 🔴 Crítico

### [CONTRADIÇÃO] CLAUDE.md "API Response Standard (resumo)" descreve um envelope que o código não usa `.claude/CLAUDE.md` (seção *API Response Standard (resumo)*) (confiança: 0.92)
**Doc afirma:** CLAUDE.md ensina o envelope de sucesso como
`{"data": {...}, "meta": {"request_id": "..."}}` (single) e
`{"data": [...], "meta": {"request_id": "...", "pagination": {...}}}` (collection).
**Código agora:** `src/building_blocks/presentation/responses.py:73` →
`{"type": resource_type, "data": data}`; `:101` →
`{"type": "list", "data": data, "metadata": {"pagination": {...}}}`. O `request_id`
vai para o **header** (`request_context.py:64`, `X-Request-Id`), nunca no corpo.
**Por que diverge:** três erros num só bloco — (1) o campo obrigatório `type` está
ausente no resumo; (2) a chave é `metadata`, não `meta`; (3) `request_id` não existe
no payload. Um implementador que seguir o CLAUDE.md monta um envelope incompatível com
todo o resto da API e com o parser do frontend.
**Sugestão de atualização:** alinhar o resumo do CLAUDE.md ao
`api-response-standard-rest-v3.md` e ao `responses.py` (incluir `type`, usar
`metadata`, mover `request_id` para header).

> Drift relacionado mas inverso: o próprio `responses.py:11-15` (docstring) admite que
> a paginação está aninhada em `metadata` enquanto o standard v3 a coloca no top-level —
> ver finding médio abaixo. O standard e o código divergem entre si **e** o CLAUDE.md
> diverge de ambos.

---

## 🟠 Alto

### [CONTRADIÇÃO] "Módulos NÃO importam entre si" / ADR-009 rule #3 violado na camada de aplicação `.claude/CLAUDE.md` (regra de dependência) ↔ `docs/adr/ADR-009-cross-bc-read-ports.md:44` (confiança: 0.82)
**Doc afirma:** CLAUDE.md: *"Módulos NÃO importam entre si — usar Read Port + ACL
(ADR-009)"*. ADR-008:99 princípio #1: *"Módulos não importam entre si"*. ADR-009 regra
#3: *"Adapter é o único import cross-BC domain. Use case só conhece a port local."*
**Código agora:** imports cross-BC **fora** de `infrastructure/acl/`, na camada de aplicação:
- `src/modules/media/application/services/scan_run_service.py:21` →
  `from src.modules.library.domain.entities.library import Library` (entidade de outro BC
  importada num application service do media).
- `src/modules/media/application/use_cases/get_overview_stats.py:3` →
  `from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory`.
- `src/modules/media/application/use_cases/trigger_scan.py:6` →
  `from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory`.
**Por que diverge:** a regra textual ("o adapter é o *único* import cross-BC", "use case
só conhece a port local") é violada — use cases/services do `media` importam UoW factories
de `identity`/`library` e a entidade `Library` diretamente, sem port. Não é o ACL
sancionado pela ADR-009.
**Sugestão de atualização:** ou (a) registrar exceção explícita na ADR-009 para
orquestração multi-UoW (ex.: scan/overview), ou (b) tratar como dívida de arquitetura e
manter o ADR como está; de qualquer forma a afirmação absoluta do CLAUDE.md ("NÃO importam
entre si") precisa de ressalva.

### [OBSOLETO] Hierarquia `PresentationException` documentada não existe no código `docs/standards/exception-hierarchy-clean-architecture.md:128,867-943` (confiança: 0.83)
**Doc afirma:** o guia documenta uma camada inteira `PresentationException` com
`InvalidRequestFormatException`, `UnsupportedMediaTypeException`, `NotAcceptableException`
(árvore na linha 128-131, definições em 890-943) e o CLAUDE.md aponta este guia como
fonte para "criar/usar exceções".
**Código agora:** `grep -rn PresentationException src/` → **zero ocorrências**.
`building_blocks` define apenas `CoreException`, `DomainException`, `ApplicationException`,
`InfrastructureException` e suas subclasses (`domain/errors.py`, `application/errors.py`,
`infrastructure/errors.py`). Não há `building_blocks/presentation/errors.py`.
**Por que diverge:** um engenheiro instruído a levantar `UnsupportedMediaTypeException`
não encontra a classe. O guia descreve um ramo da hierarquia que nunca foi implementado.
**Sugestão de atualização:** marcar a seção `PresentationException` como "não
implementado / aspiracional" ou removê-la até existir o módulo correspondente.

---

## 🟡 Médio

### [CONTRADIÇÃO] Árvore de estrutura e lista de Bounded Contexts do CLAUDE.md listam 4 módulos; existem 9 `.claude/CLAUDE.md` (seções *Estrutura* e *Bounded Contexts*) (confiança: 0.95)
**Doc afirma:** o tree de `src/modules/` e a lista numerada de BCs citam apenas `media`,
`library`, `watch_progress`, `collections`.
**Código agora:** `src/modules/` contém **9** módulos: `media`, `library`,
`watch_progress`, `collections`, `catalog_requests`, `identity`, `notifications`,
`preferences`, `settings`. (O texto da "Fase Atual" já diz "9 bounded contexts", mas o
tree e a lista de BCs não foram atualizados.)
**Por que diverge:** quem procura onde mora auth/notificações/settings é levado a crer que
não existem como módulos. Inconsistência interna no próprio CLAUDE.md (tree=4 vs texto=9).
**Sugestão de atualização:** incluir os 5 módulos faltantes no tree e na lista de BCs.

### [CONTRADIÇÃO] Standard v3 coloca `pagination` no top-level; o código aninha em `metadata` `docs/standards/api-response-standard-rest-v3.md:51-68` ↔ `src/building_blocks/presentation/responses.py:101-110` (confiança: 0.9)
**Doc afirma:** v3 exibe a coleção como `{"type":"list","data":[...],"pagination":{...}}`
com `pagination` no **nível raiz** e `metadata` reservado só para `filters_applied`.
**Código agora:** `api_list` produz `{"type":"list","data":[...],"metadata":{"pagination":
{...}}}` — paginação **aninhada** em `metadata`. O docstring `responses.py:11-15` reconhece
explicitamente o desvio ("the standard doc describes a top-level placement that can be
adopted in a future major").
**Por que diverge:** cliente que lê o standard acessa `resp.pagination`; o real é
`resp.metadata.pagination`.
**Sugestão de atualização:** anotar no standard v3 a divergência atual (paginação em
`metadata`) ou versionar o standard para refletir a implementação vigente.

### [OBSOLETO] CLAUDE.md aponta i18n para `i18n/locales/{en,pt-BR}/` — diretório inexistente `.claude/CLAUDE.md` (checklist #8) (confiança: 0.85)
**Doc afirma:** checklist de feature, item 8: *"i18n: traduções em
`i18n/locales/{en,pt-BR}/`"*.
**Código agora:** não existe `i18n/`, `locales/` nem catálogo JSON de tradução
(`find` por `pt-BR/`, `i18n`, `*locale*.json` → vazio). A i18n é feita por **campos
localizados por entidade** (`get_title(lang)` em `movie.py`/`series.py`/`season.py`/
`episode.py`) com `lang` vindo de query param (`movie_routes.py:58 lang: str = "en"`).
**Por que diverge:** o checklist manda criar arquivos num diretório que não existe e que
não corresponde ao mecanismo real (campos localizados em DB, não message catalogs).
**Sugestão de atualização:** reescrever o item 8 para "adicionar campos localizados na
entidade + enrichment por locale (TMDB)"; remover o caminho `i18n/locales/`.

### [OBSOLETO] api-i18n-guide descreve message-catalogs JSON + Accept-Language que não são usados `docs/standards/api-i18n-guide.md:32-58,68-73,175-201` (confiança: 0.7)
**Doc afirma:** o guia especifica resolução por header `Accept-Language` com q-values,
header `Content-Language` na resposta, diretório `locales/` com namespaces JSON e
`SUPPORTED_LOCALES = ["en","pt-BR","pt","es"]` carregados de arquivos.
**Código agora:** i18n real = `lang` query param (`movie_routes.py:58`) +
`entity.get_title(lang)`; locales suportados são **config-driven** via
`settings.py:176 supported_locales` (default `["en","pt-BR"]`), não a lista do guia; não há
parsing de Accept-Language nem catálogos JSON.
**Por que diverge:** o guia descreve uma arquitetura de i18n (catálogos de mensagem) que o
backend não implementa; a localização é por dado de domínio enriquecido do TMDB.
**Sugestão de atualização:** reescrever o guia para o modelo real (campo `lang`,
`supported_locales` config-driven, localização por entidade) ou marcá-lo como design
não adotado.

### [CONTRADIÇÃO] Contagens de endpoints/testes desatualizadas `.claude/CLAUDE.md:186` e `docs/roadmap.md:69,114` (confiança: 0.9)
**Doc afirma:** CLAUDE.md:186 e roadmap:69 — *"107 endpoints REST ... 2 530+ testes"*;
roadmap:114 (entrada mais recente) — *"112 REST API endpoints ... 2 660+ tests"*.
**Código agora:** `grep '@router.(get|post|put|patch|delete)'` → **132** rotas;
`281` arquivos `test_*.py` com **2 941** funções `test_*`.
**Por que diverge:** ambos os números (107/2530 e 112/2660) estão defasados frente a
132/2941. Métricas factuais erradas.
**Sugestão de atualização:** atualizar para ~132 endpoints / ~2940 testes (ou remover os
números fixos e referir um comando de contagem).

---

## 🔵 Baixo

### [OBSOLETO] ADR-008 "Estrutura Adotada" reflete só media+library e prevê eventos em shared_kernel `docs/adr/ADR-008-screaming-architecture.md:28-95,99` (confiança: 0.55)
**Doc afirma:** o tree da ADR mostra apenas `modules/media` e `modules/library`;
`config/containers/` lista só `media.py` e `library.py`; princípio #1 diz "comunicação
futura via integration events **no shared_kernel**".
**Código agora:** 9 módulos; `config/containers/` tem 11 arquivos (um por BC +
`infrastructure.py`/`main.py`); integration events vivem em
`modules/<bc>/domain/events.py` (não em shared_kernel) e **já** são usados em produção
(event handlers cross-BC), não "futuramente".
**Por que diverge:** ADR é um registro datado (2026-04-02) — o tree é snapshot histórico
e por isso a severidade é baixa; ainda assim o status "Aceito" + o princípio #1 sobre
shared_kernel descrevem um mecanismo que não foi o adotado.
**Sugestão de atualização:** nota de revisão na ADR-008 esclarecendo que eventos ficam no
domínio de cada BC e que o nº de módulos cresceu (sem reescrever o snapshot original).

### [LACUNA] Módulos `notifications` e `preferences` sem ADR e fora da lista de ADRs do CLAUDE.md `docs/adr/` / `.claude/CLAUDE.md` (confiança: 0.6)
**Doc afirma:** a lista de ADRs ativos no CLAUDE.md vai até ADR-022; não há ADR para
`notifications` nem `preferences`.
**Código agora:** existem `src/modules/notifications/` e `src/modules/preferences/` como
BCs completos (4 camadas, rotas, containers).
**Por que diverge:** `identity`→ADR-010, `catalog_requests`→ADR-022, `settings`→ADR-013/014,
mas `notifications`/`preferences` não têm registro de decisão. Lacuna menor (preferences é
pequeno; notifications nasceu junto da ADR-022 mas o publishing/transport não está coberto).
**Sugestão de atualização:** avaliar um ADR curto para notifications (transport/fanout) se
a decisão for relevante; caso contrário, registrar como deliberadamente sem ADR.

---

## 🟡 Lacunas de documentação (resumo)

- **Iniciativa de localização sem ADR** (confiança 0.7): comportamento cross-cutting
  significativo — `supported_locales` config-driven (`settings.py:176`), enriquecimento
  TMDB por locale para temporadas/episódios, campos `localized` por entidade, indexação
  FTS5 de campos localizados — **não tem ADR**. `catalog_requests` tem ADR-022, mas a
  localização-como-arquitetura (a decisão de migrar de hardcoded en+pt-BR para
  config-driven + localização per-entity) ficou sem registro. Candidato a ADR.
- **PresentationException** (ver Alto): documentada, não implementada — gap inverso
  (doc sem código).
- **i18n message-catalog** (ver Médio): guia descreve sistema não implementado.

## 🗺️ Cobertura

| Símbolo/decisão | Doc relacionado | Status |
|---|---|---|
| Envelope de resposta (`api_single`/`api_list`) | CLAUDE.md resumo / standard v3 | 🔴 drift (3 lugares) |
| Regra "módulos não importam entre si" | CLAUDE.md / ADR-008 / ADR-009 | 🔴 drift (application layer) |
| Hierarquia de exceções | exception-hierarchy doc | 🟠 PresentationException ausente |
| i18n (`lang` param, `get_title`, `supported_locales`) | CLAUDE.md #8 / api-i18n-guide | 🟠 drift (catálogo inexistente) |
| Lista de módulos/BCs | CLAUDE.md tree+BC list / ADR-008 tree | 🟡 4 listados, 9 reais |
| Contagem endpoints/testes | CLAUDE.md:186 / roadmap | 🟡 107·112 vs 132; 2530·2660 vs 2941 |
| Prefixed IDs `mov_`/`ser_` (ADR-002) | ADR-002 | ✅ consistente (ExternalId em building_blocks) |
| Exception base classes (Core/Domain/Application/Infrastructure) | exception-hierarchy doc | ✅ batem com `errors.py` |
| ACL ports cross-BC (`infrastructure/acl/*`) | ADR-009 | ✅ padrão seguido na maioria dos pares |
| Catalog Requests subscriptions/fanout | ADR-022 | ✅ atualizado junto do código |
| Localização (config-driven/per-entity) | — | 🟡 sem ADR |
| notifications / preferences | — | 🟡 sem ADR |

## ✅ Higiene boa

- **ADR-022** (catalog requests subscriptions + fanout) foi escrito junto da feature e bate
  com o código atual (`modules/catalog_requests`, event handlers, ACL).
- **ADR-010/011** (identity/auth) e **ADR-013/014** (settings) cobrem corretamente seus
  módulos.
- `responses.py:11-15` documenta **honestamente** seu próprio desvio do standard v3
  (paginação em `metadata`) — boa sinalização, ainda que o standard devesse ser
  reconciliado.
- A hierarquia de exceções de domínio/aplicação/infra do guia bate 1:1 com
  `building_blocks/*/errors.py` (só a camada de apresentação está sobre-documentada).

## 🤔 Baixa confiança (verificar manualmente)

- ADR-008 snapshot histórico (0.55) — listado em Baixo; pode-se decidir não tocar ADRs
  datados por política.
- notifications/preferences sem ADR (0.6) — pode ser ausência deliberada.
