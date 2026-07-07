# ADR-028: Semântica de uso da hierarquia de exceções de domínio

**Status:** Aceito
**Data:** 2026-07-07
**Decisores:** Lucas Cristovam

## Contexto

A hierarquia de exceções de domínio existe desde a fundação e vive em
`src/building_blocks/domain/errors.py`:

```
CoreException                          # code="…" (raiz técnica, i18n via message_code)
 └── DomainException                   # DOMAIN_ERROR            (HTTP 422 via ADR-012)
      ├── DomainValidationException    # DOMAIN_VALIDATION_ERROR (422)
      ├── BusinessRuleViolationException  # BUSINESS_RULE_VIOLATION (422)
      ├── DomainNotFoundException      # DOMAIN_NOT_FOUND        (404)
      └── DomainConflictException      # DOMAIN_CONFLICT         (409)
```

A **semântica de quando usar cada subclasse nunca foi registrada como decisão** —
ela vive apenas nas docstrings das classes. Na prática, o código já a segue com
disciplina. Auditoria (jul/2026) sobre `src/`:

| Sinal | Estado real |
|---|---|
| `raise DomainException(` cru (base) | **0** — ninguém instancia a base diretamente |
| `raise DomainValidationException` | 14 (+ factories `from_violations`, `single_field`, `from_pydantic_errors`) |
| `raise BusinessRuleViolationException` | 17 — **todos com `rule_code`** |
| `raise DomainNotFoundException` | 1 (+ factory `for_entity`) |
| `raise DomainConflictException` | 1 |

O módulo `media` inclusive já mantém uma classe de constantes tipadas
`MediaRuleCodes` (`SEASON_SERIES_MISMATCH`, `INTRO_EXCEEDS_DURATION`,
`MEDIA_CONFLICT_ALREADY_RESOLVED`, …) em vez de strings soltas.

**Este ADR não corrige uma bagunça — ratifica a convenção já praticada e a trava
contra regressão.** O valor é triplo:

1. **Registro explícito** — a decisão sai das docstrings e vira critério de review
   e de onboarding, com uma árvore de decisão canônica.
2. **Trava anti-regressão** — hoje há 0 raises da base crua e 17/17 `rule_code`
   preenchidos; sem enforcement, o primeiro atalho corrói o sinal silenciosamente.
3. **Sinergia com o que já existe** — o mapping error→HTTP (ADR-012) e a
   observabilidade por `code`/`rule_code` só rendem se a subclasse certa e o
   `rule_code` certo forem lançados. Ratificar fecha o lado domínio do contrato
   que o ADR-012 abre no lado transporte.

## Decisão

**Todo `raise` de exceção de domínio DEVE usar a subclasse semanticamente mais
específica**, segundo a árvore de decisão (na ordem; parar no primeiro match):

| # | Teste mental | Exceção |
|---|---|---|
| 1 | "Fomos buscar um agregado/entidade e não estava lá?" | `DomainNotFoundException` (preferir `.for_entity(type, id)`) |
| 2 | "Conflito com estado existente?" (duplicado, versão, concorrência) | `DomainConflictException` |
| 3 | "O objeto pode existir com esse valor? Não — dado estruturalmente inválido" | `DomainValidationException` (preferir factories) |
| 4 | "Objeto válido em si, mas o negócio proíbe a operação agora?" | `BusinessRuleViolationException` — **`rule_code` obrigatório** |
| 5 | "Contrato técnico do próprio framework de domínio?" | `DomainException` cru — ÚNICO uso legítimo |

Regras complementares:

- **`DomainException` cru (base) é reservado a invariantes de framework de
  domínio** — casos sem subclasse semântica (falha de contrato técnico das
  próprias bases). Na prática, deve permanecer em **0 raises fora de
  `src/building_blocks/domain/`**. Fora dali, usar a base é violação por padrão.
- **`rule_code` é obrigatório em todo `BusinessRuleViolationException`.** Reusar
  códigos existentes antes de cunhar novos; em módulos com muitos códigos, agrupá-los
  numa classe de constantes tipadas (padrão exemplar: `MediaRuleCodes` no BC `media`)
  em vez de strings soltas. Códigos em uso hoje: `MEDIA_ALREADY_EXISTS`,
  `CUSTOM_LIST_NAME_DUPLICATE`, `CUSTOM_LIST_LIMIT_EXCEEDED`,
  `CUSTOM_LIST_ITEM_LIMIT_EXCEEDED`, `CUSTOM_LIST_ITEM_DUPLICATE`, mais a família
  `MediaRuleCodes`.
- **Falha de persistência/gateway NUNCA usa esta hierarquia** — território das
  exceções de `application`/`infrastructure` (`ApplicationException`,
  `RepositoryException`, `GatewayException`).
- **Testes unitários DEVEM assertar a subclasse específica** (e o `rule_code`,
  quando `BusinessRuleViolationException`), nunca a base `DomainException` genérica.

### Fronteira: erros do BC Identity

O BC `identity` modela vários erros na **hierarquia de application**
(`ProfileNotFoundException(ResourceNotFoundException)`,
`ProfileOwnershipViolation(ForbiddenOperationException)`,
`CannotDeleteLastProfileError(ApplicationException)`, …), não na hierarquia de
domínio. Isso é **intencional e fora do escopo deste ADR**: são erros de caso de
uso / autorização, não invariantes de agregado. Este ADR rege apenas a árvore de
`DomainException`; a escolha domínio-vs-application permanece guiada pelas
docstrings das bases e por ADR-017 (invariantes de domínio na camada de domínio).

## Opções consideradas

### Opção A — `DomainException` único + discriminação por string `code`

Uma classe, discriminação por `code`/`message_code` string. Rejeitada: o mapping
error→HTTP por tipo/registry (ADR-012) fica cego, handlers precisam inspecionar
strings, e não há exaustividade verificável. É justamente o que a hierarquia atual
já evita — formalizar A seria regressão.

### Opção B — Hierarquia de subclasses com semântica registrada + `rule_code` (escolhida)

Subclasses carregam a semântica grossa (validação / regra / not-found / conflito)
e habilitam mapping e handling por tipo; `rule_code` carrega a granularidade fina
para observabilidade sem explosão de classes (uma classe por regra seria dezenas
de tipos). **É o estado atual do código** — esta opção o ratifica e o protege.

### Opção C — Result Pattern para todas as falhas de domínio

Migrar toda falha de domínio para um tipo `Result` explícito na assinatura.
Rejeitada como regra geral: mudança invasiva em toda a API de domínio sem ganho
proporcional. Exceções de domínio permanecem para violações de invariante e
guards — condições que o chamador não trata como fluxo normal. Onde a falha é
resultado *esperado* do caso de uso, o projeto já usa retorno explícito na camada
de application; as duas abordagens coexistem com fronteira clara (domínio =
exceção; caso de uso com falha esperada = retorno).

## Consequências

**Positivas:**
- Dashboards/alertas por `code` e `rule_code` têm sinal real (ex.: pico de
  `MEDIA_ALREADY_EXISTS` sinaliza scan duplicando; `*_LIMIT_EXCEEDED` sinaliza UX).
- O mapping error→HTTP (ADR-012) resolve status com precisão por `code`.
- Testes ficam sensíveis a regressão semântica.
- Onboarding e review ganham um critério único (a árvore de decisão) em vez de
  ler docstring por docstring.

**Negativas / aceitas:**
- **Não há backlog de migração relevante** — o código já está conforme (0 raises
  da base, 17/17 `rule_code`). O custo é só manter a disciplina em código novo:
  **boy-scout rule** (código tocado segue o ADR; nada de migração em massa).
- Novos BCs com códigos de regra próprios devem decidir cedo se agrupam em uma
  classe de constantes (recomendado a partir de ~3 códigos) ou usam literais.
- Classificação correta da subclasse e do `rule_code` é regra **semântica**, não
  mecânica — exige code review. A árvore de decisão deste ADR é o critério.

**Enforcement:**
- **Determinístico (CI):** `raise DomainException(` (a base) fora de
  `src/building_blocks/domain/` falha o pipeline — ratchet que mantém o 0 atual.
  <!-- TODO(Lucas): adicionar step de grep/ruff-custom no job de lint da CI -->
- **Semântico (code review de MR):** escolha da subclasse e presença/reuso de
  `rule_code`, usando a árvore de decisão deste ADR como critério — já coberto
  pelo subagente de code-smell/arch do fluxo `mr-review`.

## Referências

- ADR-012 — Registry descentralizado de error→HTTP mapping (resolve status por
  `code`; este ADR garante que o `code` certo é lançado)
- ADR-017 — Invariantes de domínio na camada de domínio (fronteira domínio vs application)
- `docs/standards/exception-hierarchy-clean-architecture.md` — hierarquia completa
  (domain + application + infrastructure) e semântica das bases
- `src/building_blocks/domain/errors.py` — definição da hierarquia e docstrings-fonte
- `src/modules/media/…` — `MediaRuleCodes` como padrão exemplar de `rule_code` tipado
- `src/modules/identity/domain/errors.py` — erros modelados na hierarquia de
  application (fora do escopo, ver §Fronteira)
