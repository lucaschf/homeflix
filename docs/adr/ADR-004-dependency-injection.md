# ADR-004: Injeção de Dependências com dependency-injector

**Status:** Aceito  
**Data:** 2025-01-28  
**Deciders:** Lucas  
**Technical Story:** Definir estratégia de DI que não acople use cases ao container

---

## Contexto

Em Clean Architecture, as camadas internas (Domain, Application) não devem conhecer detalhes de infraestrutura. Isso inclui o mecanismo de injeção de dependências.

Precisamos de uma estratégia que:

1. **Não polua use cases** - Use cases recebem interfaces, não sabem do container
2. **Centralize a composição** - Um lugar só monta o grafo de dependências
3. **Integre bem com FastAPI** - Funcione com o sistema de Depends
4. **Seja testável** - Fácil de substituir dependências em testes

## Decisão

**Adotamos `dependency-injector` com injeção via construtor puro nos use cases.**

### Princípio: Use Cases são Agnósticos ao Container

```python
# ✅ CORRETO - Use case não sabe que container existe
class GetMovieUseCase:
    def __init__(self, movie_repository: MovieRepository):  # Interface!
        self._movie_repository = movie_repository
    
    async def execute(self, movie_id: str) -> MovieOutput:
        movie = await self._movie_repository.find_by_id(MovieId(movie_id))
        if not movie:
            raise ResourceNotFoundException.for_resource("Movie", movie_id)
        return MovieOutput.from_entity(movie)


# ❌ ERRADO - Use case acoplado ao container
class GetMovieUseCase:
    @inject  # NÃO FAÇA ISSO
    def __init__(self, movie_repository: MovieRepository = Provide[Container.movie_repo]):
        ...
```

### Onde o Container Vive

O container é configurado apenas na **Composition Root** (`main.py` ou `config/container.py`):

```
src/
├── domain/                    # 🟢 Zero conhecimento de DI
│   └── media/
│       └── repositories.py    # Interface MovieRepository
│
├── application/               # 🟢 Zero conhecimento de DI  
│   └── media/
│       └── use_cases/
│           └── get_movie.py   # Recebe interface no __init__
│
├── infrastructure/            # 🟡 Implementações concretas
│   └── persistence/
│       └── repositories/
│           └── movie.py       # SQLAlchemyMovieRepository
│
├── config/
│   └── container.py           # 🔴 ÚNICO lugar que conhece o container
│
└── main.py                    # 🔴 Composition Root
```

## Implementação

### 1. Interface no Domain (Pura)

```python
# domain/media/repositories.py
from abc import ABC, abstractmethod
from domain.media.entities import Movie
from domain.shared.models import MovieId

class MovieRepository(ABC):
    """Interface for movie persistence operations."""
    
    @abstractmethod
    async def find_by_id(self, movie_id: MovieId) -> Movie | None:
        """Find a movie by its external ID."""
        ...
    
    @abstractmethod
    async def save(self, movie: Movie) -> Movie:
        """Persist a movie."""
        ...
```

### 2. Use Case na Application (Puro)

```python
# application/media/use_cases/get_movie.py
from dataclasses import dataclass
from domain.media.repositories import MovieRepository  # Interface!
from domain.shared.models import MovieId
from application.shared.exceptions import ResourceNotFoundException

@dataclass
class GetMovieInput:
    movie_id: str

@dataclass
class GetMovieOutput:
    id: str
    title: str
    year: int
    duration_display: str

class GetMovieUseCase:
    """Retrieve a movie by ID."""
    
    def __init__(self, movie_repository: MovieRepository):
        # Recebe INTERFACE, não implementação concreta
        self._movie_repository = movie_repository
    
    async def execute(self, input: GetMovieInput) -> GetMovieOutput:
        movie_id = MovieId(input.movie_id)
        movie = await self._movie_repository.find_by_id(movie_id)
        
        if not movie:
            raise ResourceNotFoundException.for_resource("Movie", input.movie_id)
        
        return GetMovieOutput(
            id=str(movie.id),
            title=movie.title,
            year=movie.year.value,
            duration_display=movie.duration.to_display(),
        )
```

### 3. Container (Organizado por Responsabilidade)

Os containers são organizados em módulos separados para manter o código gerenciável:

```
config/
├── containers/
│   ├── __init__.py              # Exporta ApplicationContainer
│   ├── main.py                  # Container principal (compõe tudo)
│   ├── infrastructure.py        # Database, APIs externas
│   ├── repositories.py          # Implementações de repositórios
│   └── use_cases/
│       ├── __init__.py
│       ├── media.py             # Use cases de mídia
│       ├── progress.py          # Use cases de progresso
│       └── collections.py       # Use cases de coleções
├── container.py                 # Re-export para compatibilidade
└── settings.py
```

**Container de Infraestrutura:**

```python
# config/containers/infrastructure.py
class InfrastructureContainer(containers.DeclarativeContainer):
    config = providers.Dependency(instance_of=Settings)
    
    database = providers.Singleton(
        Database,
        url=config.provided.database_url,
    )
    
    tmdb_client = providers.Singleton(
        TMDBClient,
        api_key=config.provided.tmdb_api_key,
    )
```

**Container de Use Cases (por bounded context):**

```python
# config/containers/use_cases/media.py
class MediaUseCaseContainer(containers.DeclarativeContainer):
    # Dependências injetadas pelo container pai
    movie_repository = providers.Dependency()
    tmdb_client = providers.Dependency()
    
    get_movie = providers.Factory(
        GetMovieUseCase,
        movie_repository=movie_repository,
    )
    
    scan_library = providers.Factory(
        ScanLibraryUseCase,
        movie_repository=movie_repository,
        tmdb_client=tmdb_client,
    )
```

**Container Principal (Composição):**

```python
# config/containers/main.py
class ApplicationContainer(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=["presentation.api.v1.routes.media", ...]
    )
    
    config = providers.Singleton(Settings)
    
    # Sub-containers
    infrastructure = providers.Container(
        InfrastructureContainer,
        config=config,
    )
    
    repositories = providers.Container(
        RepositoryContainer,
        database=infrastructure.database,
    )
    
    # Use cases organizados por bounded context
    class use_cases(containers.DeclarativeContainer):
        media = providers.Container(
            MediaUseCaseContainer,
            movie_repository=repositories.movie_repository,
            tmdb_client=infrastructure.tmdb_client,
        )
        
        progress = providers.Container(
            ProgressUseCaseContainer,
            progress_repository=repositories.progress_repository,
        )
```

### 4. Integração com FastAPI

```python
# presentation/api/v1/routes/media.py
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from config.container import Container
from application.media.use_cases.get_movie import GetMovieUseCase, GetMovieInput

router = APIRouter(prefix="/movies", tags=["Movies"])

@router.get("/{movie_id}")
@inject
async def get_movie(
    movie_id: str,
    use_case: GetMovieUseCase = Depends(Provide[Container.get_movie_use_case]),
):
    """Get a movie by ID."""
    result = await use_case.execute(GetMovieInput(movie_id=movie_id))
    return {"data": result}
```

**Note:** O decorator `@inject` e `Provide` ficam APENAS na camada de presentation (routes). Os use cases continuam puros.

### 5. Composition Root (main.py)

```python
# main.py
from fastapi import FastAPI
from config.container import Container

def create_app() -> FastAPI:
    container = Container()
    container.wire()  # Conecta o wiring aos módulos configurados
    
    app = FastAPI(title="HomeFlix")
    app.container = container  # Disponibiliza para shutdown
    
    # Include routers
    from presentation.api.v1.routes import media, progress
    app.include_router(media.router, prefix="/v1")
    app.include_router(progress.router, prefix="/v1")
    
    return app

app = create_app()
```

### 6. Testes (Sem Container!)

```python
# tests/unit/application/test_get_movie.py
import pytest
from unittest.mock import AsyncMock

from application.media.use_cases.get_movie import GetMovieUseCase, GetMovieInput
from application.shared.exceptions import ResourceNotFoundException
from domain.media.entities import Movie

class TestGetMovieUseCase:
    @pytest.fixture
    def mock_repository(self):
        return AsyncMock()
    
    @pytest.fixture
    def use_case(self, mock_repository):
        # Injeta mock diretamente - sem container!
        return GetMovieUseCase(movie_repository=mock_repository)
    
    async def test_returns_movie_when_found(self, use_case, mock_repository):
        # Arrange
        movie = Movie(id=MovieId("mov_abc123"), title="Test", ...)
        mock_repository.find_by_id.return_value = movie
        
        # Act
        result = await use_case.execute(GetMovieInput(movie_id="mov_abc123"))
        
        # Assert
        assert result.title == "Test"
    
    async def test_raises_not_found_when_missing(self, use_case, mock_repository):
        mock_repository.find_by_id.return_value = None
        
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(GetMovieInput(movie_id="mov_xxx"))
```

## Consequências

### Positivas

1. **Use cases 100% puros** - Não importam nada de DI
2. **Testabilidade** - Injeta mocks direto no construtor
3. **Flexibilidade** - Pode trocar a lib de DI sem mudar use cases
4. **Single Responsibility** - Container só monta grafo de dependências
5. **Integração FastAPI** - Wiring automático funciona bem

### Negativas

1. **Mais uma dependência** - `dependency-injector` no projeto
2. **Curva de aprendizado** - Precisa entender a lib
3. **Boilerplate no container** - Precisa registrar cada dependência

### Se Precisar Trocar a Lib de DI

Apenas estes arquivos mudam:
- `config/container.py`
- `presentation/api/v1/routes/*.py` (decorators)
- `main.py`

**Zero mudanças em:**
- `domain/*`
- `application/*`
- `infrastructure/*` (exceto composition)

## Alternativas Consideradas

### 1. python-injector

```python
from injector import Module, provider, Injector

class AppModule(Module):
    @provider
    def provide_movie_repo(self, db: Database) -> MovieRepository:
        return SQLAlchemyMovieRepository(db)
```

**Considerado, mas preterido:**
- Menos exemplos com FastAPI
- Documentação mais fraca
- Funcionalidade similar

### 2. FastAPI Depends Puro (Manual)

```python
def get_movie_repository():
    return SQLAlchemyMovieRepository(get_db())

def get_use_case(repo = Depends(get_movie_repository)):
    return GetMovieUseCase(repo)
```

**Rejeitado:**
- Muito boilerplate
- Difícil gerenciar lifecycle (singletons)
- Não escala bem

### 3. Sem DI Container

```python
# main.py - montar tudo manualmente
db = Database(settings.db_url)
movie_repo = SQLAlchemyMovieRepository(db)
get_movie_uc = GetMovieUseCase(movie_repo)
```

**Rejeitado:**
- Não escala
- Difícil gerenciar singletons
- Composition root vira bagunça

## Referências

- [dependency-injector Docs](https://python-dependency-injector.ets-labs.org/)
- [FastAPI + dependency-injector](https://python-dependency-injector.ets-labs.org/examples/fastapi.html)
- [Clean Architecture - Composition Root](https://blog.ploeh.dk/2011/07/28/CompositionRoot/)

---

## Checklist de Implementação

- [ ] Instalar `dependency-injector` no pyproject.toml
- [ ] Criar `config/container.py`
- [ ] Configurar wiring nos routes
- [ ] Inicializar container no `main.py`
- [ ] Criar primeiro use case com injeção
- [ ] Escrever testes sem container
