---
name: homeflix-arch
description: Apply HomeFlix-specific architectural conventions when working in the HomeFlix codebase. Use when creating, reviewing, or refactoring code in HomeFlix — modules, bounded contexts, entities (Movie, Series, Season, Episode, Library, Profile, WatchProgress), ports, Unit of Work, repositories, use cases. Triggers on file paths under src/modules/, src/building_blocks, src/shared_kernel, on mentions of MovieId/SeriesId/LibraryId/ProfileId/ExternalId or of a cross-BC read port, on questions like "como faço X no HomeFlix?", "isso segue os ADRs?". This skill complements clean-arch-python — load both together.
---

# HomeFlix Architecture Profile

Esta skill aplica as **convenções específicas do HomeFlix**. Ela carrega junto
com o núcleo `clean-arch-python` (princípios universais) e adiciona o
vocabulário, os anti-padrões e o **processo de diagnóstico** do projeto.

## Hierarquia de fontes

Esta skill **não é** a fonte da verdade sobre a estrutura do código. A ordem é:

1. **O código** — `src/modules/` diz quais bounded contexts existem, não uma
   lista escrita em lugar nenhum.
2. **Os ADRs** (`docs/adr/`, índice em `docs/adr/README.md`) — decisões e suas
   justificativas.
3. **`CLAUDE.md` na raiz do repo** — convenções operacionais, gates, layout.
4. **Esta skill** — como conduzir o trabalho: diagnóstico, ranking de opções,
   anti-padrões a sinalizar, como comunicar conflito com ADR.

Quando esta skill divergir do código ou de um ADR, **o código e o ADR ganham** —
e vale avisar o usuário que a skill envelheceu.

Esta skill é versionada no repo (`.claude/skills/homeflix-arch/`). Mudança de
convenção e atualização desta skill cabem no **mesmo PR** — é isso que evita o
drift que já a deixou cinco meses atrás do código.

Se um pedido conflita com um ADR, **aponte o ADR específico** e explique a
justificativa antes de implementar ou recusar.

## Stack

- **Linguagem**: Python 3.12+ (mypy `strict`)
- **Web**: FastAPI (async)
- **ORM**: SQLAlchemy 2.0+ (async, `Mapped`)
- **DI**: `dependency-injector`
- **Validação**: Pydantic v2 (encapsulado via `building_blocks.domain`)
- **Logging**: `structlog`
- **Testes**: `pytest`, `pytest-asyncio`, `AsyncMock`
- **Scheduling**: APScheduler (`src/infrastructure/scheduling/`)

Detalhes de uso por biblioteca: `references/stack_specifics.md`.
Roteamento tópico → ADR: `references/adr_index.md`.

## Convenções que dão errado em silêncio

O layout de pastas e a regra de dependência estão no `CLAUDE.md` do repo —
não os repita de memória. O que segue é o que um agente erra sozinho.

### Identificadores (ADR-002, ADR-018)

IDs externos têm formato `{prefixo}_{base62_12chars}`. Cada tipo é uma
**subclasse de `ExternalId` com `EXPECTED_PREFIX`**, não uma entrada numa lista
central:

```python
class MovieId(ExternalId):
    EXPECTED_PREFIX: ClassVar[str] = "mov"
```

Adicionar agregado novo = criar a subclasse, não editar um registro global.

O ADR-018 vai além do ADR-002: identificador **não trafega como `str` cru** entre
camadas ou BCs. ID malformado numa ACL vira *default-deny silencioso* —
indistinguível de acesso removido de propósito. Valide na borda, trafegue VO.

⚠️ Exceção real, não descuido: `Movie.library_id` é `str`, com comentário
explicando que `LibraryId` vive em outro BC e o ADR-008 proíbe o import. Ao
encontrar `str` onde caberia VO, **leia o comentário antes de "corrigir"** —
pode ser a tensão ADR-008 × ADR-018 já resolvida de propósito.

**Anti-padrão**: `int` ou `UUID` como id de agregado.

### Imutabilidade (ADR-007)

Agregados e entidades são `frozen=True`. Mutação retorna nova instância:

```python
movie = movie.with_genre(Genre("Sci-Fi"))   # ✅ novo
movie = movie.without_path(old_path)        # ✅ novo (ou self, se no-op)
```

Os `with_*` se apoiam em `with_updates(**kwargs)`
(`building_blocks/domain/entity.py`), que faz `setdefault` em `updated_at` — não
passe timestamp na mão.

Nunca exponha método imperativo (`add_genre`, `mark_X`, `set_Y`) em agregado ou
entidade.

`AggregateRoot` acumula eventos via `add_event`; quem drena com `pull_events()`
e publica é o use case, nunca o domínio.

### Use case: Unit of Work + ports (ADR-004)

Use case é **puro** — recebe abstrações no construtor, não conhece container:

```python
class GetMovieByIdUseCase:
    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None: ...
```

O UoW do BC (`modules/<bc>/application/unit_of_work.py`) declara os repositórios
que participam de uma transação. Fora do `async with` os atributos não existem —
acessar levanta `AttributeError` de propósito, para o erro aparecer na chamada.

**Anti-padrão**: use case recebendo repositório solto quando o BC já tem UoW; ou
abrindo sessão por conta própria.

DTOs `Input`/`Output` vivem em `application/dtos/` como `@dataclass(frozen=True)`,
**não** no arquivo do use case.

Wiring (`@inject`, `Provide`) **somente** em routes. Container por BC em
`config/containers/<bc>.py`, composto no `ApplicationContainer`
(`config/containers/main.py`) — os sub-containers ficam direto nele
(`ApplicationContainer.media.<provider>`), sem nível `use_cases` intermediário.

### Cross-BC é Read Port + ACL (ADR-009, ADR-024)

Quando um BC precisa ler dado de outro:

1. Port no consumidor: `modules/<bc>/application/ports/<x>_port.py`
2. DTO próprio no consumidor (nunca a entity do outro BC)
3. Adapter no consumidor: `modules/<bc>/infrastructure/acl/`
4. Adapter é o **único** ponto que importa do BC de origem
5. Wire em `config/containers/<bc>.py`

**Anti-padrão**: `from src.modules.<outro>.domain...` em código de módulo.

### Exceções: código no domínio, HTTP no módulo (ADR-012, ADR-028)

Violação de regra usa código do `rule_codes.py` do próprio módulo. O mapa
código → status HTTP é **descentralizado**: `presentation/error_mapping.py` de
cada BC, registrado pelo `bootstrap.py` a partir do composition root. Não existe
handler global por BC nem mapeamento de status na rota.

`scripts/check_domain_exceptions.sh` reprova o CI quando a semântica do ADR-028
é violada.

### Autenticação é declarada, não implícita

Não há middleware de auth. Rota só é protegida se a árvore de dependências dela
alcançar um guard de identity. Rota sem guard e fora da allowlist reprova em
`tests/architecture/test_route_authentication.py`.

**Anti-padrão**: checar role dentro do corpo do handler — invisível para o teste
arquitetural, que só enxerga dependências declaradas.

### Pydantic encapsulado (ADR-001)

```python
from pydantic import BaseModel          # ❌ em domain
from src.building_blocks.domain import AggregateRoot   # ✅
```

Bases exportadas por `building_blocks.domain`: `DomainModel`, `ValueObject`,
`CompoundValueObject`, `StringValueObject`, `IntValueObject`, `FloatValueObject`,
`DateValueObject`, `ExternalId`, `DomainEntity`, `AggregateRoot`.

## Anti-padrões a sinalizar ativamente

- **Module importando module direto** — `from src.modules.X...` em `src/modules/Y/` (ADR-008/009)
- **Module importando `config/containers/`** — composition root é unidirecional
- **Método imperativo em entidade** — `movie.add_genre()` (ADR-007)
- **`int`/`UUID` como id de agregado** (ADR-002)
- **`str` cru de identificador cruzando camada** (ADR-018) — salvo exceção comentada
- **`from pydantic import BaseModel` em domain** (ADR-001)
- **`@inject`/`Provide` fora de routes** (ADR-004)
- **Use case abrindo sessão ou recebendo repo solto** onde há UoW
- **Guard de auth dentro do corpo do handler** em vez de `Depends`
- **Mapeamento de status HTTP na rota** em vez de `error_mapping.py` (ADR-012)
- **Adapter de port externo retornando VO de domínio** — usar DTO + conversão

## Diagnóstico inicial (antes de oferecer opções)

Quando o usuário pedir feature nova, **não pule pra "aqui estão as opções"**.
Três checagens, nesta ordem.

### Gate 1: Estado atual do código

Verifique no código se os pré-requisitos existem. **Leia, não chute** — o projeto
evolui rápido e qualquer lista escrita (inclusive as desta skill) envelhece.

- A entidade/agregado mencionado existe? Com os campos/VOs que a feature usa?
- O bounded context existe? (`ls src/modules/` — não confie em lista escrita)
- Os ports cross-BC necessários existem?
- O BC tem UoW, e o repositório que a feature precisa está declarado nele?

Para cada ausente, anote: "Pré-requisito X não existe — precisa modelar antes."

### Gate 2: Ranking por viabilidade

Ordene as opções por **viabilidade no estado atual do código**, não por
completude conceitual. A primeira opção é a que funciona com o que existe hoje.

1. **Topo**: só usa código existente
2. **Meio**: adiciona 1 coisa nova (1 VO, 1 método, 1 port)
3. **Baixo**: cruza BCs, mexe em múltiplos agregados, ou depende de coisa ausente

Opção que depende de pré-requisito ausente vai marcada:

> "Opção 1 — ⚠️ **Bloqueada**: requer `intro_markers` no Episode (não existe
> hoje). Para viabilizar, ver opção 3 primeiro."

### Gate 3: Plano em fases para opções complexas

Opção que toca 2+ bounded contexts, 2+ camadas grandes, ou introduz BC novo não
vai como bloco único. Decomponha em PRs sequenciais com dependência explícita:

> **Opção 4** — 3 PRs sequenciais:
>
> - **PR 1 — Modelagem (`media`)**: VO `IntroMarkers` (ADR-001), método
>   `Episode.with_intro_markers()` (ADR-007), use case admin. Mergeable sozinho.
> - **PR 2 — Read Port (`watch_progress`)**: depende do PR 1. Port + DTO próprio
>   (ADR-009), adapter em `infrastructure/acl/`.
> - **PR 3 — Use case (`watch_progress`)**: depende do PR 2.
>
> Cada PR é revisável e mergeable sozinho.

### Quando pular o diagnóstico

Pule quando for leitura simples ("como rodo os testes?"), pedido de snippet
isolado, mudança trivial e local (campo opcional em DTO existente), ou quando o
usuário já fechou o escopo ("faz a opção 2").

Use quando for "criar use case", "implementar feature", "fazer X ponta a ponta",
quando houver ambiguidade de escopo, ou quando a feature **puder** cruzar BCs
(gatilhos: integração, consumo de dado de outro contexto, evento).

## Workflow ao criar feature

1. **Identificar o bounded context.** BC novo = estrutura completa em
   `src/modules/<bc>/` + container + bootstrap se tiver error mapping próprio.
2. **Domain primeiro**: VOs, entity/aggregate, repository interface (ABC),
   `rule_codes` para as violações novas.
3. **Cross-BC?** Port + DTO no consumidor antes do use case.
4. **Application**: DTOs em `application/dtos/`, use case recebendo UoW factory
   e ports.
5. **Infrastructure**: model SQLAlchemy, mapper, repositório concreto; declarar o
   repositório no UoW do BC.
6. **Presentation**: router, schemas, `Depends(Provide[...])`, guard de auth
   explícito, `error_mapping` se houver código novo.
7. **Container**: registrar em `config/containers/<bc>.py` e expor no
   `ApplicationContainer`.
8. **Testes**: unit no domínio (puro), integration no repositório, e2e nas rotas.
9. **Mudou decisão arquitetural?** ADR novo com `docs/adr/TEMPLATE.md`.
10. **Rodar os gates** antes de entregar: `make lint typecheck test`
    e `make check-domain-exceptions`.

## Comunicação com o usuário

Pedido que **encaixa em um ADR** — mencione:

> "Vou seguir o **ADR-009** aqui: port local em `watch_progress` com DTO próprio,
> adapter em `infrastructure/acl/`. Quer ver o esqueleto antes?"

Pedido que **conflita com um ADR** — aponte antes de implementar:

> "Isso conflita com o **ADR-007**: `add_genre` mutaria o agregado in-place, e o
> padrão é `with_genre` retornando nova instância. Sigo o ADR ou você quer
> revisitar a decisão?"

Pedido **não coberto pelos ADRs** — sinalize:

> "Não vejo isso coberto nos ADRs atuais. Sugiro implementar com o padrão X
> (alinhado ao ADR-Y) e, após validar, formalizar como ADR novo."

## Referências

- Roteamento tópico/sintoma → ADR: `references/adr_index.md`
- Convenções por biblioteca: `references/stack_specifics.md`
- Índice autoritativo de ADRs: `docs/adr/README.md` **no repo**
- Convenções operacionais e gates: `CLAUDE.md` na raiz do repo
- Núcleo Clean Arch + DDD: skill `clean-arch-python`
