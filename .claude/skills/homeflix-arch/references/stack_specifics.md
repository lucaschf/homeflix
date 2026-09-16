# Stack Specifics — HomeFlix

Convenções por biblioteca. Carregue ao implementar código que toca
infraestrutura, presentation ou setup.

> Os snippets abaixo refletem o padrão em vigor, mas **o código é a fonte da
> verdade**. Antes de copiar um padrão daqui, abra um arquivo vizinho do mesmo
> tipo e confirme — o projeto evolui e este arquivo não é atualizado
> automaticamente.

## FastAPI (presentation)

Routes em `modules/<bc>/presentation/routes/`:

```python
from typing import Any
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer

router = APIRouter(prefix="/movies", tags=["Movies"])


@router.get("/{movie_id}")
@inject
async def get_movie(
    movie_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> dict[str, Any]:
    output = await use_case.execute(
        GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id),
    )
    return api_single("movie", asdict(output))
```

**Regras**:
- `@inject` e `Provide` **somente** em routes (ADR-004).
- O provider vem direto do sub-container do BC:
  `ApplicationContainer.media.<nome>` — não há nível `use_cases` intermediário.
- **Toda rota declara um guard de auth** via `Depends`, ou entra na allowlist de
  `tests/architecture/test_route_authentication.py` com justificativa. Checagem
  escrita no corpo do handler é invisível para esse teste.
- O envelope da resposta vem de `building_blocks/presentation/responses.py`
  (`api_single`, `api_list`), seguindo
  `docs/standards/api-response-standard-rest-v3.md`. Não monte o dict na mão.
- Status HTTP de erro **não** se decide na rota: vem do `error_mapping.py` do BC
  (ADR-012).
- Schemas de request em `modules/<bc>/presentation/schemas/`: validação de
  **formato** (Pydantic). Validação de **domínio** fica no VO. Não duplique.

## SQLAlchemy 2.0 (async)

### Model — `modules/<bc>/infrastructure/persistence/models/`

```python
class MovieModel(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    library_id: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str]
    year: Mapped[int]
```

- `external_id` separado do `id` interno (ADR-002), com índice único.
- Models **não vazam** de `infrastructure/persistence/` — converta via mapper.

### Mapper — `.../persistence/mappers/`

Converte model ↔ entity. Atenção: nem todo campo vira VO. `Movie.library_id` é
`str` de propósito (ADR-008 proíbe importar `LibraryId` do BC `library`), então o
mapper repassa direto — não "conserte" isso sem ler o comentário na entidade.

### Repositório — recebe a sessão da transação

O repositório **não** abre sessão própria e **não** recebe factory: quem
gerencia o ciclo é o Unit of Work.

```python
class SQLAlchemyMovieRepository(MovieRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
```

Sempre busque por `external_id`, nunca pelo `id` interno. Mantenha a interface
segregada (ADR-033) — repositório não é balcão de tudo.

## Unit of Work

Cada BC declara seu UoW em `modules/<bc>/application/unit_of_work.py`: uma
interface listando os repositórios que compartilham transação, mais uma factory.
A implementação vive em `.../infrastructure/persistence/sqlalchemy_unit_of_work.py`
e herda o ciclo de vida (open/commit/rollback/close, guarda contra uso aninhado)
de `building_blocks/infrastructure/sqlalchemy_unit_of_work.py`.

```python
async with uow_factory() as uow:
    movie = await uow.movies.find_by_id(movie_id)
    ...
```

Fora do `async with` os atributos de repositório não existem — acessá-los
levanta `AttributeError` de propósito.

Ao adicionar repositório novo: declare no UoW do BC **e** popule em
`_build_repositories`.

## DI Container (dependency-injector)

`src/config/containers/` tem um arquivo por bounded context, mais
`infrastructure.py` e `main.py` (composition root). **Não existe** um
`repositories.py` central — cada BC compõe o que precisa.

```python
# config/containers/watch_progress.py
class WatchProgressContainer(containers.DeclarativeContainer):
    uow_factory = providers.Dependency()
    media_lookup = providers.Dependency()   # port do ACL

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        uow_factory=uow_factory,
        media_lookup=media_lookup,
    )
```

No `main.py`, os sub-containers ficam **direto** no `ApplicationContainer`
(`media = providers.Container(MediaContainer, ...)`), e é assim que a rota os
endereça: `Provide[ApplicationContainer.media.<provider>]`.

BC com error mapping próprio também expõe `bootstrap.setup()`, chamado uma vez
pelo composition root (ADR-012).

## structlog

Configurado em `src/config/logging.py`; `get_logger(**contexto)` devolve o
logger já com bind.

```python
logger = get_logger(use_case="ScanLibrary")
logger.info("scan_started", library_id=library_id)
```

**Regras**:
- Logger é cross-cutting: acessado direto, **não injetado** no construtor.
- Domain layer **não loga**. Application, Infrastructure e Presentation logam.
- Estruturado: evento + chave-valor, nunca f-string interpolada.
- Detalhes e vocabulário de eventos: `docs/standards/logging-guide.md`.

## Testes

A convenção documentada está em `docs/standards/testing-guide.md` — leia de lá,
não daqui.

Dois pontos que importam na hora de escrever:

- **O layout real é `tests/modules/<bc>/{unit,integration,e2e}/<camada>/`**, e
  não o `tests/unit/...` que o testing-guide ainda descreve. Espelhe os vizinhos
  do módulo em que você está mexendo.
- Use case e domínio se testam **sem container**: `AsyncMock(spec=...)` no lugar
  do port ou da UoW factory, injetado direto no construtor.

`tests/architecture/` contém guardrails que o linter não pega. Se um quebrar,
leia o docstring — cada um descreve o incidente que o motivou. Não relaxe o
guardrail para a mudança passar.

## Configuração

- `src/config/settings.py` — Pydantic Settings, lê de env vars e de um `.env`
  único (veja `.env.example`). `get_settings()` devolve instância singleton,
  acessada direto — **não injetada** no construtor.
- Tunables operacionais que mudam em runtime **não** vão em env var: são
  settings persistidos em banco, por bucket (ADR-013, ADR-014).
- `pyproject.toml` — dependências, mypy (`strict`), pytest. Lint em `ruff.toml`.

## Localização

Não existe catálogo de mensagens nem diretório `locales/`. A localização é por
**dado de domínio**: campos localizados na entidade (`entity.get_title(lang)`,
ADR-023), com `lang` vindo de query param e os locales suportados em
`settings.supported_locales`.

`docs/standards/api-i18n-guide.md` descreve um design de catálogo JSON que o
projeto **não** adotou — o próprio guia avisa isso no topo. Não implemente a
partir dele.

## Arquivos a não tocar sem autorização

- Migrações em `migrations/versions/` — Alembic gerencia; edição manual quebra o
  histórico. Gere com `make migration message="..."`.
- ADRs aceitos em `docs/adr/` — ao substituir, mude o status do antigo e
  referencie o novo. Nunca reescreva a decisão original.
