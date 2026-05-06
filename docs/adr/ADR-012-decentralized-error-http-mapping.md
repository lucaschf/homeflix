# ADR-012: Registry Descentralizado de Error HTTP Mapping

**Status:** Aceito
**Data:** 2026-05-06
**Deciders:** Lucas Cristovam
**Technical Story:** Inversão consciente do trade-off documentado em `docs/standards/exception-hierarchy-clean-architecture.md` §4 (Trade-off Pragmático).

---

## Contexto

Hoje a hierarquia de exceções carrega o HTTP status como propriedade da própria classe. `CoreException` define `http_status = 500` como default, e cada subclasse em `building_blocks/{domain,application,infrastructure}/errors.py` sobrescreve a propriedade para o status apropriado (404, 422, 503, etc.). O handler global em `src/building_blocks/presentation/exception_handlers.py` lê `exc.http_status` direto.

Esse design foi adotado conscientemente como trade-off pragmático e está documentado em `docs/standards/exception-hierarchy-clean-architecture.md` §4 ("Princípios de Design — Trade-off Pragmático"). A justificativa original era evitar um mapper externo cheio de condicionais.

Dois sintomas tornaram o trade-off menos atrativo conforme o projeto evoluiu:

1. **Vazamento de HTTP no domain.** `building_blocks/domain/errors.py` e o erros de domínio dos módulos (ex.: `modules/identity/domain/errors.py:58,88`) declaram `http_status` — a camada conceitualmente mais pura está acoplada a uma noção de transporte. Mesmo com poucos casos hoje (apenas 2 overrides em módulos), é dívida arquitetural que cresce conforme novos BCs aparecem.

2. **Espalhamento da decisão de status.** Quando um módulo precisa de um status não-default (ex.: 409 para conflito específico), a única opção é overridar a property na classe — não há ponto único onde se vê "todos os codes deste BC e seus statuses". A revisão de PR fica mais difícil porque a decisão está distribuída entre N classes.

A inspiração concreta vem do projeto `valid` (ADR-0008 daquele projeto), que enfrentou um problema relacionado mas mais agudo: lá havia um dict centralizado em `building_blocks` listando codes de módulos específicos, violando a regra de dependência. O HomeFlix nunca chegou a ter essa violação porque optou pela property — mas o custo da property é o vazamento de HTTP no domínio.

## Decisão

Adotamos um **registry descentralizado de mapeamento `error_code → http_status`**, registrado por Bounded Context no bootstrap da aplicação. A propriedade `http_status` é removida de todas as classes de exceção. O handler global resolve o status consultando o registry pelo `code` da exceção.

### Estrutura

```
src/
├── building_blocks/
│   └── presentation/
│       ├── error_mapping.py        # registry + GENERIC_HTTP_STATUSES + resolvers
│       └── exception_handlers.py   # passa a usar resolve_http_status(exc.code)
└── modules/
    └── <bc>/
        ├── bootstrap.py            # setup() registra o mapping do BC
        └── presentation/
            └── error_mapping.py    # {BC}_HTTP_STATUSES (apenas codes do BC)
```

### Regras

1. **`building_blocks/presentation/error_mapping.py`** expõe:
   - `_REGISTRY: dict[str, int]` (privado, mutável só via `register_http_statuses`)
   - `GENERIC_HTTP_STATUSES: dict[str, int]` — codes transversais (`DOMAIN_VALIDATION_ERROR`, `RESOURCE_NOT_FOUND`, `GATEWAY_TIMEOUT`, etc.) auto-registrado no import.
   - `register_http_statuses(mapping: dict[str, int]) -> None` — único ponto de mutação do registry. Idempotente (re-registrar o mesmo code com o mesmo status é no-op). Registrar um code já existente com status diferente é erro de programação — levanta exceção em vez de sobrescrever silenciosamente.
   - `resolve_http_status(code: str, default: int = 500) -> int`
   - `resolve_error_type(http_status: int) -> str` — substitui `CoreException._get_error_type()` (status → `"validation_error"` / `"not_found_error"` / etc).

2. **Cada BC com codes próprios** declara `src/modules/{bc}/presentation/error_mapping.py` com um dict `{BC}_HTTP_STATUSES` listando **todos** os codes do BC (inclusive os que herdam status de uma base — repetir a entrada explicitamente, porque o registry é flat e indexado por code, não por classe).

3. **Cada BC com codes próprios** expõe `src/modules/{bc}/bootstrap.py` com `def setup() -> None` que importa o dict e chama `register_http_statuses({BC}_HTTP_STATUSES)`.

4. **Composition root** (`src/main.py` ou `ApplicationContainer.wire()`) chama `_bootstrap_modules()` **antes** de `register_exception_handlers(app)`. A função invoca cada `bootstrap.setup()` individualmente:

   ```python
   def _bootstrap_modules() -> None:
       from src.modules.identity import bootstrap as identity_bootstrap
       identity_bootstrap.setup()
       # outros BCs aqui conforme aparecem codes próprios
   ```

5. **Domain não conhece HTTP.** Nenhuma classe de exceção em `building_blocks/{domain,application,infrastructure}/errors.py` ou em `modules/*/domain/errors.py` declara `http_status`. A propriedade é removida.

6. **BCs sem codes próprios não precisam de bootstrap.** Hoje apenas `identity` tem codes que não são genéricos. Os outros (`media`, `library`, `watch_progress`, `collections`) reutilizam codes genéricos via `ResourceNotFoundException.for_resource(...)` etc — não precisam de `error_mapping.py` ou `bootstrap.py` enquanto não introduzirem code próprio.

### Migração

A mudança é estrutural mas a transição é segura quando feita em 3 PRs sequenciais:

1. **Introduzir o registry, manter a property.** Cria `error_mapping.py`, `GENERIC_HTTP_STATUSES`, resolvers. Bootstrap do `identity` registra `IDENTITY_HTTP_STATUSES`. Nenhum comportamento muda — `exc.http_status` ainda é a fonte da verdade. Adiciona test que valida cobertura: cada subclasse de `CoreException` no projeto tem entrada no registry.

2. **Inverter a fonte da verdade no handler.** `core_exception_handler` passa a usar `resolve_http_status(exc.code)` em vez de `exc.http_status`. Comportamento idêntico se o registry estiver completo (garantido pelo teste de cobertura do PR 1).

3. **Remover `http_status` das exceptions.** Property sai de todas as 18 subclasses em `building_blocks/` + 2 overrides em `modules/identity/`. `CoreException._get_error_type()` sai. Os 18 testes que assertam `exc.http_status == X` migram para `resolve_http_status("CODE") == X` ou `response.status_code == X` (E2E).

## Consequências

### Positivas

- **Domain puro de HTTP.** `domain/`, `application/` e `infrastructure/` deixam de mencionar HTTP em qualquer lugar. A camada de transporte vive 100% em `presentation/`.
- **Decisão localizada por BC.** O `error_mapping.py` de cada BC é o ponto único onde se vê todos os codes do BC e seus statuses. Review de PR fica direto.
- **Modularidade real.** Se um BC for extraído para outro serviço, seu mapping vai junto — não há property espalhada por classes.
- **Open/Closed mantido.** Adicionar um novo BC com codes próprios não toca `building_blocks` — basta criar o `error_mapping.py` e o `bootstrap.py` do BC.
- **Resolução de error type também migra.** O dict `_STATUS_TO_ERROR_TYPE` (hoje duplicado em `exception_handlers.py:24` e `errors.py:175`) consolida em um lugar.

### Negativas

- **Boilerplate por BC.** Cada BC com code próprio cria 2 arquivos (`error_mapping.py` + `bootstrap.py`). Hoje seria apenas `identity`; o custo cresce linear no número de BCs com codes próprios.
- **Bug class novo: code esquecido no registry.** Se um code for adicionado a uma exceção e não ao registry, cai no default 500. Mitigação: teste de cobertura iterando todas as subclasses de `CoreException`.
- **Estado mutável global.** `_REGISTRY` é um dict mutável de módulo. Para testes, precisa de fixture `reset_registry()` em `conftest.py` para isolamento.
- **Ordem de bootstrap importa.** `register_exception_handlers` antes de `_bootstrap_modules` faz tudo cair em 500. Mitigação: smoke test que dispara uma `ResourceNotFoundException` e confirma 404.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Code adicionado sem entrada no registry vira 500 silencioso | Média | Médio | Teste de cobertura: itera `CoreException.__subclasses__()` recursivamente e garante `resolve_http_status(cls.code) != default` |
| Conflito de codes entre BCs (mesmo code com statuses diferentes) | Baixa | Médio | `register_http_statuses` levanta erro em conflito real (mesmo key, valor diferente). Re-registro idempotente do mesmo valor é no-op |
| Bootstrap rodar fora de ordem em testes / scripts ad-hoc | Baixa | Baixo | Container expõe método `bootstrap_modules()` chamado por `main.py` e por `conftest.py` global. Scripts ad-hoc que pulam composition root recebem 500 — comportamento esperado |
| `valid` ADR-0008 evoluir para algo diferente | Baixa | Baixo | A decisão aqui é independente. Não somos obrigados a copiar mudanças futuras do `valid` |

## Alternativas Consideradas

### 1. Manter `http_status` como property (status quo)

Continuar com o trade-off pragmático documentado em `exception-hierarchy-clean-architecture.md` §4.

**Rejeitado porque:** vaza HTTP no domain. Hoje custa pouco (2 overrides), mas o custo é incremental — cada novo BC com status custom paga o preço.

### 2. Mapper baseado em classes (MRO walk)

`HTTPStatusMapper` com `_STATUS_MAP: dict[Type[CoreException], int]` que percorre `__mro__` para resolver. É a alternativa que a seção "HTTP Status Mapper (Abordagem Purista)" do standards doc descrevia.

**Rejeitado porque:** acopla o mapper às classes de exceção (precisa importar todas as subclasses no dict). Adicionar uma nova subclasse exige editar o mapper central — viola Open/Closed em `building_blocks`. Indexar por `code` (string) é mais frouxo e mais fácil de evoluir.

### 3. Subclasses mais granulares em `building_blocks`

Adicionar `ConflictException` (409), `BusinessRuleViolation` (422), etc. nas bases. Os 2 overrides em `identity` desapareceriam por herança.

**Rejeitado porque:** resolve o sintoma de hoje sem atacar o problema (HTTP continua na classe). Funcionaria como medida paliativa, mas adia a decisão estrutural.

### 4. Eager registration via import side-effects

Cada `modules/<bc>/__init__.py` chama `register_http_statuses(...)` no top-level — zero bootstrap explícito.

**Rejeitado porque:** import side-effects são padrão que evitamos no projeto. Bootstrap explícito no composition root é coerente com ADR-004 (DI via `dependency-injector`).

### 5. Atributo na classe registrado pelo metaclass

`CoreException.__init_subclass__` lê o `code` e o `http_status` da classe e popula o registry automaticamente. Mantém HTTP na classe mas centraliza a fonte da verdade.

**Rejeitado porque:** ainda mantém HTTP no domain. A decisão aqui é remover o vazamento, não centralizá-lo de outra forma.

## Referências

- `docs/standards/exception-hierarchy-clean-architecture.md` — atualizado em conjunto com este ADR (§4 invertido, seção "HTTP Status Mapper" reescrita).
- `docs/adr/ADR-008-screaming-architecture.md` — organização por BC que este ADR estende para o cross-cutting concern de error mapping.
- `docs/adr/ADR-004-dependency-injection.md` — composition root é o ponto canônico de bootstrap.
- `docs/adr/ADR-009-cross-bc-read-ports.md` — mesma filosofia: cada BC declara seu próprio contrato em vez de depender de um registry central.
- `src/building_blocks/presentation/exception_handlers.py` — handler global afetado pelo PR 2 da migração.
- `src/modules/identity/domain/errors.py:58,88` — únicos overrides de `http_status` em código de módulo hoje.

---

## Notas de Implementação

### Esqueleto do registry

```python
# src/building_blocks/presentation/error_mapping.py
from src.config.logging import get_logger

_REGISTRY: dict[str, int] = {}
_STATUS_TO_ERROR_TYPE: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    409: "conflict_error",
    422: "validation_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "bad_gateway_error",
    503: "service_unavailable_error",
    504: "gateway_timeout_error",
}

GENERIC_HTTP_STATUSES: dict[str, int] = {
    "DOMAIN_VALIDATION_ERROR": 422,
    "DOMAIN_BUSINESS_RULE_VIOLATION": 422,
    "DOMAIN_NOT_FOUND": 404,
    "USE_CASE_VALIDATION_ERROR": 422,
    "RESOURCE_NOT_FOUND": 404,
    "FORBIDDEN_OPERATION": 403,
    "UNAUTHORIZED_OPERATION": 401,
    "GATEWAY_TIMEOUT": 504,
    "GATEWAY_UNAVAILABLE": 503,
    # ... lista completa derivada de building_blocks/{domain,application,infrastructure}/errors.py
}


def register_http_statuses(mapping: dict[str, int]) -> None:
    """Register a batch of code → http_status entries. Idempotent for equal values, raises on conflict."""
    for code, status in mapping.items():
        existing = _REGISTRY.get(code)
        if existing is not None and existing != status:
            raise ValueError(
                f"Conflicting http_status registration for code {code!r}: "
                f"already registered as {existing}, new value {status}"
            )
        _REGISTRY[code] = status


def resolve_http_status(code: str, default: int = 500) -> int:
    return _REGISTRY.get(code, default)


def resolve_error_type(http_status: int) -> str:
    return _STATUS_TO_ERROR_TYPE.get(http_status, "api_error")


# Auto-register building_blocks codes on import.
register_http_statuses(GENERIC_HTTP_STATUSES)
```

### Bootstrap do BC

```python
# src/modules/identity/presentation/error_mapping.py
IDENTITY_HTTP_STATUSES: dict[str, int] = {
    "PROFILE_NOT_FOUND": 404,
    "PROFILE_OWNERSHIP_VIOLATION": 403,
    "NO_ACTIVE_SESSION": 401,
    "CANNOT_DELETE_LAST_PROFILE": 409,
    "NO_ACTIVE_PROFILE": 409,
}
```

```python
# src/modules/identity/bootstrap.py
def setup() -> None:
    """Bootstrap the identity module: register error→HTTP mappings."""
    from src.building_blocks.presentation.error_mapping import register_http_statuses
    from src.modules.identity.presentation.error_mapping import IDENTITY_HTTP_STATUSES

    register_http_statuses(IDENTITY_HTTP_STATUSES)
```

### Handler atualizado

```python
# src/building_blocks/presentation/exception_handlers.py
async def core_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(CoreException, exc)
    http_status = resolve_http_status(exc.code)
    error_type = resolve_error_type(http_status)
    # ... log + serialize
    return JSONResponse(status_code=http_status, content=exc.to_dict(error_type=error_type))
```

### Teste de cobertura

```python
# tests/building_blocks/unit/presentation/test_error_mapping_coverage.py
def _all_subclasses(cls):
    seen = set()
    stack = [cls]
    while stack:
        node = stack.pop()
        for sub in node.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return seen


def test_every_core_exception_subclass_has_registry_entry():
    """Guards against silent 500 fallback when a new exception is added without a registry entry."""
    from src.building_blocks.domain.errors import CoreException
    from src.building_blocks.presentation.error_mapping import resolve_http_status

    # Force-import all error modules so subclasses register.
    import src.building_blocks.domain.errors  # noqa: F401
    import src.building_blocks.application.errors  # noqa: F401
    import src.building_blocks.infrastructure.errors  # noqa: F401
    import src.modules.identity.domain.errors  # noqa: F401
    # add new BC error modules here as they appear

    missing = []
    for cls in _all_subclasses(CoreException):
        try:
            instance = cls(message="probe")
        except TypeError:
            continue  # skip abstract / dataclass-required classes; covered indirectly by their concrete subclasses
        if resolve_http_status(instance.code, default=-1) == -1:
            missing.append((cls.__name__, instance.code))
    assert not missing, f"Missing registry entries: {missing}"
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-06 | Lucas Cristovam | Criação inicial — inverte o trade-off documentado em `exception-hierarchy-clean-architecture.md` §4 |
