# CLAUDE.md — Contexto do projeto HomeFlix

Plataforma de streaming pessoal (mídia em disco local). Serve a dois
propósitos ao mesmo tempo: **lab de Clean Architecture / DDD** e
**ferramenta funcional**. Quando os dois conflitam, a arquitetura ganha —
este repo existe para praticá-la.

O frontend vive em repositório separado: [`lucaschf/homeflix-web`](https://github.com/lucaschf/homeflix-web)
(React + TypeScript). Ao depurar fluxo ponta a ponta (player, continue
watching, seleção de faixa), lembre que o cliente consome a API REST daqui
e pode ser a origem do sintoma.

## Antes de implementar

Os ADRs são **fonte da verdade** e têm precedência sobre o que estiver
escrito aqui. Se um pedido conflita com um ADR, aponte o ADR e a
justificativa antes de implementar ou recusar.

| Preciso de… | Vá para |
|---|---|
| Decisões de arquitetura (índice completo, com status) | `docs/adr/README.md` |
| Registrar nova decisão | `docs/adr/TEMPLATE.md` |
| Formato de resposta da API | `docs/standards/api-response-standard-rest-v3.md` |
| Criar/usar exceções | `docs/standards/exception-hierarchy-clean-architecture.md` |
| Decisões pragmáticas (o que injetar, o que não) | `docs/standards/clean-architecture-decisions.md` |
| Integração com API externa | `docs/standards/external-api-integration-guide.md` |
| Logging (`structlog`) | `docs/standards/logging-guide.md` |
| Convenções de teste | `docs/standards/testing-guide.md` |
| Features e regras de negócio | `docs/homeflix-requirements.md` |
| Priorização e próximos passos | `docs/roadmap.md` |

Não replique o conteúdo desses arquivos em respostas ou em código —
consulte e cite o caminho.

## Estrutura

Screaming Architecture (ADR-008): **módulo é o eixo primário**, camada
técnica é subdivisão interna.

```
src/
├── building_blocks/   # base técnica domain-agnostic (DomainModel, ExternalId, errors)
├── shared_kernel/     # VOs de negócio cross-module (FilePath, LanguageCode, ProfileId, tracks)
├── modules/<bc>/      # um bounded context por diretório
│   ├── domain/        #   entities, value_objects, repositories (ABC), services, events, rule_codes
│   ├── application/   #   use_cases, dtos, ports, unit_of_work, services, event_handlers
│   ├── infrastructure/#   persistence, acl, file_system, …
│   ├── presentation/  #   routes, schemas, dependencies, error_mapping
│   └── bootstrap.py   #   wiring do BC chamado pelo composition root
├── infrastructure/    # infra compartilhada (database, Base, scheduler)
├── config/            # settings, logging, containers/ (composition root, um por módulo)
└── main.py
```

Os bounded contexts existentes estão em `src/modules/` — consulte o
diretório em vez de confiar em qualquer lista escrita, inclusive esta.

**Regra de dependência:** `modules → shared_kernel → building_blocks`, e
dentro do módulo `presentation → application → domain ← infrastructure`.
O domínio não importa de camada nenhuma.

## Convenções que o código não deixa óbvias

Estas são as que dão errado em silêncio. As demais o linter pega.

### Entidades são imutáveis (ADR-007)

Agregados e entidades são `frozen=True`. Mutação é sempre nova instância:

```python
movie = movie.with_genre(Genre("Sci-Fi"))   # ✅
movie.genres.append(...)                     # ❌ frozen
```

Nunca adicione método imperativo (`add_x`, `set_x`, `mark_x`) em entidade.
Os `with_*` do agregado se apoiam em `with_updates(**kwargs)`
(`building_blocks/domain/entity.py`), que já faz o bump de `updated_at` —
não passe o timestamp na mão.

`AggregateRoot` acumula eventos de domínio via `add_event`; quem drena com
`pull_events()` e publica é o use case, nunca o domínio.

### Use case recebe Unit of Work e ports, não repositório solto

```python
class GetMovieByIdUseCase:
    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None: ...
```

O UoW do BC (`modules/<bc>/application/unit_of_work.py`) expõe os
repositórios que participam de uma transação; fora do `async with` os
atributos não existem. Use cases não conhecem o container — quem injeta é
a rota.

DTOs `Input`/`Output` ficam em `application/dtos/`, como
`@dataclass(frozen=True)`, **não** no arquivo do use case.

### Cross-BC é Read Port + ACL (ADR-009, ADR-024)

Módulo não importa de módulo. Para ler dado de outro BC:

1. Port no consumidor: `modules/<bc>/application/ports/<x>_port.py`
2. DTO próprio no consumidor (nunca a entity do outro BC)
3. Adapter em `modules/<bc>/infrastructure/acl/` — **único** ponto que
   importa do BC de origem
4. Wire em `config/containers/<bc>.py`

`from src.modules.media.domain...` dentro de outro módulo é o anti-padrão
que a ACL existe para evitar.

### Identificadores são VOs, inclusive nas fronteiras (ADR-002, ADR-018)

IDs externos são `{prefixo}_{base62×12}`. Cada tipo é uma subclasse de
`ExternalId` com `EXPECTED_PREFIX: ClassVar[str]`
(`building_blocks/domain/external_id.py`) — não existe lista central de
prefixos para atualizar.

`str` cru atravessando camada ou BC é o smell que o ADR-018 trata: um ID
malformado vira *default-deny silencioso*, indistinguível de acesso
removido de propósito. Valide na borda, trafegue VO.

### Exceções: código de regra no domínio, HTTP no módulo (ADR-012, ADR-028)

Violação de regra usa código do `rule_codes.py` do próprio módulo. O mapa
código → status HTTP é **descentralizado**: `presentation/error_mapping.py`
de cada BC, registrado pelo `bootstrap.py` a partir do composition root.
Não centralize e não mapeie status na rota.

`scripts/check_domain_exceptions.sh` reprova o CI quando a semântica do
ADR-028 é violada.

### Toda rota declara seu guard

Não existe middleware de autenticação. Uma rota só é protegida se a árvore
de dependências dela alcançar um guard de identity (`authenticated_user`,
`authenticated_admin`, `get_current_profile`, …). Rota sem guard e fora da
allowlist **reprova** em `tests/architecture/test_route_authentication.py`.
Rota pública é decisão deliberada, com justificativa escrita na allowlist.

### Pydantic entra encapsulado (ADR-001)

Herde de `src.building_blocks.domain.*` (`AggregateRoot`, `DomainEntity`,
VOs base). `from pydantic import BaseModel` direto no domínio é erro.

## Gates

Rodam no pre-commit e no CI. Todos bloqueiam.

```bash
make lint                      # ruff check + format --check
make typecheck                 # mypy strict em src/
make check-domain-exceptions   # ADR-028
make test                      # pytest
make docs-build                # mkdocs --strict
```

- **mypy é `strict = true`.** Sem `Any` implícito, sem função sem anotação.
- **ruff com `D` (Google) e `ERA`**: docstring obrigatória em público,
  código comentado reprova. Linha: 100.
- `conventional-pre-commit` valida a mensagem no stage `commit-msg`.
  Tipos aceitos: `feat fix docs style refactor perf test build ci chore revert`.

Outros comandos: `make dev` (porta 8005), `make test-unit`, `make test-cov`,
`make migration message="..."`, `make migrate`, `make docs`.
`make help` lista tudo.

## Testes

Layout espelha `src/`: módulo primeiro, tipo depois —
`tests/modules/<bc>/{unit,integration,e2e}/<camada>/`. Fora disso:
`tests/building_blocks/`, `tests/shared_kernel/`, `tests/infrastructure/`,
`tests/config/` e `tests/architecture/`.

```bash
pytest tests/modules/media/unit -v      # rodar um recorte
pytest tests/architecture -v            # guardrails arquiteturais
```

`tests/architecture/` trava regras que o linter não vê (autenticação
declarada nas rotas, fonte única para checagem de admin, policy explícita
em leitura cross-BC). Quebrou um desses: leia o docstring do teste antes de
mexer — cada um explica o incidente que motivou o guardrail. Não relaxe o
teste para fazer a mudança passar.

Use case e domínio se testam sem container: instancie com `AsyncMock` no
lugar do port/UoW.

## Git e commits

- **Nunca commitar direto em `develop`.** Branch a partir de
  `origin/develop`: `git checkout -b <type>/<descricao-curta> origin/develop`
- PR tem `develop` como alvo.
- Conventional Commits em inglês, subject no imperativo até ~50 chars,
  body opcional de 2-3 frases explicando o *porquê*.
- Scope é o módulo: `feat(media):`, `fix(watch_progress):`.
- **Sem atribuição de IA**: não inclua `Co-Authored-By`, menção a Claude ou
  a uso de IA em commit, PR, comentário de código ou qualquer artefato
  versionado.

PR: título em Conventional Commits, corpo com `## Summary` (bullets) e
`## Test plan` (checklist).

## Idioma

Código, commits, PRs e docstrings em **inglês**. Documentação em `docs/` e
conversa em **português**. Localização de conteúdo suporta `en` e `pt-BR`
via dado de domínio (`entity.get_title(lang)`, `settings.supported_locales`)
— não existe catálogo de mensagens nem diretório `locales/`.

## Disciplina de mudança

- Toda linha alterada rastreia para o pedido. Não "melhore" código
  adjacente, comentário ou formatação de passagem.
- Remova órfãos que **a sua** mudança criou. Dead code preexistente:
  mencione, não delete sem pedir.
- Simplicidade *dentro* da arquitetura: não invente camada que os ADRs não
  pedem — mas não corte as que pedem. VO, use case e repository são
  obrigatórios mesmo em fluxo de uso único.
- Traduza a tarefa em critério verificável antes de codar: "corrige o bug"
  vira "escreve o teste que reproduz, depois faz passar".
