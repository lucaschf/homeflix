# Clean Architecture Decisions

Decisões pragmáticas para casos comuns em Clean Architecture no HomeFlix.

## Princípio Geral

Clean Architecture preza por **separação de concerns** e **testabilidade**, mas não significa injetar tudo. A regra é:

> **Injetar dependências que afetam comportamento e precisam ser mockadas em testes.**

Cross-cutting concerns (logging, config) e utilitários simples (UUID, datetime) podem ser usados diretamente quando não comprometem a testabilidade.

---

## Settings/Config

### Decisão: Acesso direto via `get_settings()`

```python
# ✅ Pragmático - acesso direto
class TMDBClient:
    def __init__(self):
        self._settings = get_settings()
        self._base_url = self._settings.tmdb_base_url

# ❌ Over-engineering - injeção desnecessária
class TMDBClient:
    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key
```

### Motivo

- Settings são valores estáticos, não comportamento
- Em testes, usar `.env.test` ou `monkeypatch`
- Mesmo tratamento que Logger

### Exceção

Se precisar testar com diferentes configurações no mesmo teste:

```python
# Quando precisar variar config em testes
class SomeService:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
```

---

## DateTime/Clock

### Decisão: Depende do caso de uso

| Cenário | Abordagem |
|---------|-----------|
| Audit (`created_at`, `updated_at`) | Direto |
| Regra de negócio (`expires_at`, `valid_until`) | Injetado |

### Audit - Direto

```python
# Entity
class Movie(AggregateRoot):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Teste - só verifica se existe
def test_should_set_created_at():
    movie = Movie(title="Inception", ...)
    
    assert movie.created_at is not None
```

### Regra de Negócio - Injetado

```python
# Entity - recebe o timestamp
class Subscription(AggregateRoot):
    def renew(self, renewed_at: datetime, duration_days: int = 30) -> None:
        self.expires_at = renewed_at + timedelta(days=duration_days)
    
    def is_active(self, now: datetime) -> bool:
        return self.expires_at > now

# Use Case - fornece o timestamp
class RenewSubscriptionUseCase:
    async def execute(self, subscription_id: str) -> Subscription:
        subscription = await self._repository.find(subscription_id)
        subscription.renew(renewed_at=datetime.now(UTC))
        await self._repository.save(subscription)
        return subscription

# Teste - controle total do tempo
def test_should_expire_after_30_days():
    now = datetime(2025, 1, 1, tzinfo=UTC)
    subscription = Subscription(...)
    
    subscription.renew(renewed_at=now, duration_days=30)
    
    assert subscription.is_active(now + timedelta(days=29)) is True
    assert subscription.is_active(now + timedelta(days=31)) is False
```

---

## UUID Generation

### Decisão: Direto, exceto quando precisar de determinismo

```python
# ✅ Pragmático - direto no factory
class MovieId(ExternalId):
    @classmethod
    def generate(cls) -> "MovieId":
        random_part = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(12))
        return cls(f"mov_{random_part}")

# Teste - não precisa verificar o valor exato
def test_should_generate_with_correct_prefix():
    movie_id = MovieId.generate()
    
    assert movie_id.prefix == "mov"
    assert len(movie_id.random_part) == 12
```

### Quando Injetar

Se precisar de IDs determinísticos em testes de integração:

```python
# Factory que aceita valor opcional
@classmethod
def generate(cls, value: str | None = None) -> "MovieId":
    if value:
        return cls(value)
    random_part = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(12))
    return cls(f"mov_{random_part}")

# Teste com ID conhecido
def test_should_save_and_retrieve():
    movie = Movie(id=MovieId.generate("mov_test12345678"), ...)
    repository.save(movie)
    
    found = repository.find_by_id(MovieId("mov_test12345678"))
    assert found == movie
```

---

## Validação

### Decisão: Cada camada valida o que é sua responsabilidade

| Camada | Valida | Exemplos |
|--------|--------|----------|
| **Presentation** | Formato, tipos, campos obrigatórios | JSON válido, campos presentes |
| **Application** | Regras de aplicação, permissões | Usuário pode fazer esta ação? |
| **Domain** | Regras de negócio, invariantes | Rating entre 0-10, título não vazio |

### Exemplo Completo

```python
# Presentation - valida formato
class CreateMovieRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    year: int = Field(..., ge=1888, le=2100)
    rating: float | None = Field(None, ge=0, le=10)

# Application - valida permissões/contexto
class CreateMovieUseCase:
    async def execute(self, input: CreateMovieInput) -> Movie:
        # Verificar se já existe filme com mesmo título/ano
        existing = await self._repository.find_by_title_and_year(
            input.title, input.year
        )
        if existing:
            raise MovieAlreadyExistsException(input.title, input.year)
        
        # Domain cria e valida regras de negócio
        movie = Movie(
            id=MovieId.generate(),
            title=input.title,
            year=Year(input.year),  # Domain valida Year
        )
        return movie

# Domain - valida invariantes de negócio
class Year(IntValueObject):
    @model_validator(mode="after")
    def validate_year(self) -> "Year":
        if self.root < 1888:  # Primeiro filme da história
            raise ValueError("Year must be 1888 or later")
        return self
```

### Não Duplicar Validação

```python
# ❌ Ruim - validação duplicada
class CreateMovieRequest(BaseModel):
    year: int = Field(..., ge=1888)  # Valida aqui

class Year(IntValueObject):
    @model_validator(mode="after")
    def validate_year(self) -> "Year":
        if self.root < 1888:  # E aqui de novo
            raise ValueError(...)

# ✅ Bom - cada um valida o seu
class CreateMovieRequest(BaseModel):
    year: int  # Só tipo, Domain valida regra

class Year(IntValueObject):
    @model_validator(mode="after")
    def validate_year(self) -> "Year":
        if self.root < 1888:  # Regra de negócio aqui
            raise ValueError(...)
```

---

## Use Case Input/Output

### Decisão: Dataclass ou Pydantic simples, nunca Entity direta

```python
# ✅ Bom - Input/Output específicos
@dataclass(frozen=True)
class GetMovieInput:
    movie_id: str

@dataclass(frozen=True)
class GetMovieOutput:
    id: str
    title: str
    year: int
    rating: float | None

class GetMovieUseCase:
    async def execute(self, input: GetMovieInput) -> GetMovieOutput:
        movie = await self._repository.find_by_id(MovieId(input.movie_id))
        if not movie:
            raise MovieNotFoundException(input.movie_id)
        
        return GetMovieOutput(
            id=str(movie.id),
            title=movie.title,
            year=movie.year.value,
            rating=movie.rating,
        )

# ❌ Ruim - Entity atravessando camadas
class GetMovieUseCase:
    async def execute(self, movie_id: str) -> Movie:  # Entity vazando
        return await self._repository.find_by_id(MovieId(movie_id))
```

### Motivo

- **Desacoplamento**: Presentation não conhece Entity do Domain
- **Flexibilidade**: Output pode agregar dados de múltiplas entities
- **Versionamento**: API pode mudar sem afetar Domain

### Simplificação Aceita

Para casos simples, retornar Entity internamente e mapear no route:

```python
# Use Case retorna Entity (interno)
class GetMovieUseCase:
    async def execute(self, input: GetMovieInput) -> Movie:
        movie = await self._repository.find_by_id(MovieId(input.movie_id))
        if not movie:
            raise MovieNotFoundException(input.movie_id)
        return movie

# Route mapeia para Response (presentation)
@router.get("/{movie_id}")
async def get_movie(movie_id: str, use_case: GetMovieUseCase = Depends(...)):
    movie = await use_case.execute(GetMovieInput(movie_id=movie_id))
    return MovieResponse.from_entity(movie)  # Mapeamento aqui
```

---

## Repository

### Decisão: Retorna Entity do Domain, mapeia internamente

```python
# Interface no Domain
class MovieRepository(ABC):
    @abstractmethod
    async def find_by_id(self, movie_id: MovieId) -> Movie | None: ...
    
    @abstractmethod
    async def save(self, movie: Movie) -> None: ...

# Implementação na Infrastructure
class SQLAlchemyMovieRepository(MovieRepository):
    async def find_by_id(self, movie_id: MovieId) -> Movie | None:
        async with self._session_factory() as session:
            model = await session.get(MovieModel, movie_id.value)
            return model.to_entity() if model else None  # Mapeia para Entity
    
    async def save(self, movie: Movie) -> None:
        async with self._session_factory() as session:
            model = MovieModel.from_entity(movie)  # Mapeia de Entity
            session.add(model)
            await session.commit()
```

### Models de Persistência (Infrastructure)

```python
# SQLAlchemy Model - conhece Entity para mapear
class MovieModel(Base):
    __tablename__ = "movies"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    year: Mapped[int]
    rating: Mapped[float | None]
    
    def to_entity(self) -> Movie:
        return Movie(
            id=MovieId(self.id),
            title=self.title,
            year=Year(self.year),
            rating=self.rating,
        )
    
    @classmethod
    def from_entity(cls, entity: Movie) -> "MovieModel":
        return cls(
            id=entity.id.value,
            title=entity.title,
            year=entity.year.value,
            rating=entity.rating,
        )
```

---

## Exceptions

### Decisão: Específicas por contexto, hierarquia clara

```
HomeflixException (base)
├── DomainException
│   ├── InvalidMovieRatingException
│   └── MovieReleaseDateInFutureException
├── ApplicationException
│   ├── MovieNotFoundException
│   └── MovieAlreadyExistsException
└── InfrastructureException
    ├── DatabaseConnectionException
    └── TMDBApiException
```

### Quando Criar Exception Específica?

| Critério | Criar Específica? |
|----------|-------------------|
| Precisa de tratamento diferente no handler? | ✅ Sim |
| Tem dados específicos para incluir? | ✅ Sim |
| É só uma variação de mensagem? | ❌ Não, use genérica |

### Exemplo

```python
# ✅ Específica - tem dados e tratamento próprio
class MovieNotFoundException(ResourceNotFoundException):
    def __init__(self, movie_id: str):
        super().__init__(
            resource_type="Movie",
            resource_id=movie_id,
            error_code="MOVIE_NOT_FOUND",
        )

# ❌ Desnecessária - só muda mensagem
class InvalidMovieTitleException(DomainException): ...
class InvalidMovieYearException(DomainException): ...
class InvalidMovieRatingException(DomainException): ...

# ✅ Melhor - genérica com contexto
raise DomainValidationError(
    errors=[{"field": "title", "message": "Title cannot be empty"}]
)
```

---

## Resumo das Decisões

| Tópico | Decisão |
|--------|---------|
| **Settings** | `get_settings()` direto |
| **Logger** | `get_logger()` direto |
| **DateTime** | Direto para audit, injetado para regras de negócio |
| **UUID** | Direto, exceto quando precisar determinismo |
| **Validação** | Presentation = formato, Domain = regras de negócio |
| **Use Case I/O** | Dataclass/Pydantic simples, não Entity |
| **Repository** | Retorna Entity, mapeia internamente |
| **Exceptions** | Específicas quando precisar tratamento diferente |

---

## Checklist de Code Review

Antes de aprovar um PR, verificar:

- [ ] Domain não tem imports de infrastructure (logging, settings, etc.)
- [ ] Use Cases recebem dependências via construtor (exceto logger/settings)
- [ ] Validação de negócio está no Domain, não na Presentation
- [ ] Repository retorna Entity, não Model de persistência
- [ ] Exceptions têm `error_code` para tradução na Presentation
- [ ] DateTime é injetado quando há lógica de tempo a testar
