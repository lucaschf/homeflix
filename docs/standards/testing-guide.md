# Testing Guide

Guia de estilo para testes no HomeFlix.

## Estrutura de Diretórios

```
tests/
├── conftest.py              # Fixtures globais
├── unit/                    # Testes unitários (sem I/O)
│   ├── conftest.py
│   └── domain/
│       ├── media/
│       │   ├── test_movie_id.py
│       │   └── test_movie.py
│       └── shared/
│           └── test_external_id.py
├── integration/             # Testes com banco/APIs
│   ├── conftest.py
│   └── repositories/
│       └── test_movie_repository.py
└── e2e/                     # Testes de API completa
    ├── conftest.py
    └── api/
        └── test_movies_endpoint.py
```

## Nomenclatura

### Arquivos

```
test_{módulo}.py
```

Exemplos:
- `test_movie_id.py`
- `test_movie_repository.py`
- `test_get_movie_use_case.py`

### Funções

```
test_should_{resultado_esperado}_when_{condição}
```

Exemplos:
- `test_should_create_id_when_prefix_is_valid`
- `test_should_raise_error_when_title_is_empty`
- `test_should_return_none_when_movie_not_found`

### Classes (opcional, para agrupar)

```python
class TestMovieId:
    def test_should_generate_with_correct_prefix(self): ...
    def test_should_raise_error_when_invalid(self): ...

class TestMovieIdEquality:
    def test_should_be_equal_when_same_value(self): ...
    def test_should_not_be_equal_when_different_value(self): ...
```

## Padrão AAA (Arrange-Act-Assert)

Estrutura em três blocos separados por linha em branco:

```python
def test_should_create_movie_id_with_valid_string():
    valid_id = "mov_2xK9mPqR7nL4"

    movie_id = MovieId(valid_id)

    assert movie_id.value == valid_id
    assert movie_id.prefix == "mov"
```

### Regras

1. **Arrange** - Setup dos dados (pode ser omitido se simples)
2. **Act** - Uma única ação sendo testada
3. **Assert** - Verificações do resultado

### Exemplos por Complexidade

**Simples (sem Arrange):**
```python
def test_should_generate_unique_ids():
    id1 = MovieId.generate()
    id2 = MovieId.generate()

    assert id1 != id2
```

**Médio:**
```python
def test_should_raise_error_when_prefix_is_invalid():
    invalid_id = "xxx_2xK9mPqR7nL4"

    with pytest.raises(DomainValidationError) as exc_info:
        MovieId(invalid_id)

    assert "prefix" in str(exc_info.value).lower()
```

**Com fixture:**
```python
def test_should_find_movie_by_id(movie_repository, sample_movie):
    movie_repository.save(sample_movie)

    found = movie_repository.find_by_id(sample_movie.id)

    assert found is not None
    assert found.id == sample_movie.id
```

**Async:**
```python
async def test_should_execute_use_case_successfully(mock_repository):
    mock_repository.find_by_id.return_value = Movie(...)
    use_case = GetMovieUseCase(mock_repository)

    result = await use_case.execute(GetMovieInput(movie_id="mov_xxx"))

    assert result.title == "Test Movie"
```

## Fixtures

### Localização

| Escopo | Onde definir |
|--------|--------------|
| Global | `tests/conftest.py` |
| Por tipo de teste | `tests/unit/conftest.py` |
| Por módulo | `tests/unit/domain/conftest.py` |

### Nomenclatura

```python
# Entidades de exemplo
@pytest.fixture
def sample_movie() -> Movie: ...

@pytest.fixture
def sample_movie_id() -> MovieId: ...

# Mocks
@pytest.fixture
def mock_movie_repository() -> Mock: ...

# Clients/Connections
@pytest.fixture
def db_session() -> AsyncSession: ...

@pytest.fixture
def test_client() -> TestClient: ...
```

### Factory Fixtures

Para criar variações:

```python
@pytest.fixture
def movie_factory():
    def _create(
        title: str = "Test Movie",
        year: int = 2024,
        **kwargs
    ) -> Movie:
        return Movie(
            id=MovieId.generate(),
            title=title,
            year=Year(year),
            **kwargs
        )
    return _create


def test_should_filter_by_year(movie_factory):
    movie_2020 = movie_factory(year=2020)
    movie_2024 = movie_factory(year=2024)
    # ...
```

## Markers

```python
# Marcar testes lentos
@pytest.mark.slow
def test_should_process_large_library(): ...

# Marcar por tipo
@pytest.mark.unit
def test_should_validate_id(): ...

@pytest.mark.integration
def test_should_persist_movie(): ...

@pytest.mark.e2e
def test_should_return_movie_list(): ...
```

Configurados em `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
    "slow: Slow tests",
]
```

## Mocking

### Preferências

1. **Injeção de dependência** > Mock (quando possível)
2. **Mock de interfaces** > Mock de implementações
3. **Fixtures** > Mock inline

### Exemplo com Use Case

```python
@pytest.fixture
def mock_movie_repository():
    return AsyncMock(spec=MovieRepository)


def test_should_return_movie_when_found(mock_movie_repository):
    expected_movie = Movie(id=MovieId.generate(), title="Test")
    mock_movie_repository.find_by_id.return_value = expected_movie
    use_case = GetMovieUseCase(movie_repository=mock_movie_repository)

    result = await use_case.execute(GetMovieInput(movie_id=expected_movie.id))

    assert result.title == "Test"
    mock_movie_repository.find_by_id.assert_called_once()
```

## Assertions

### Preferir assertions específicas

```python
# ✅ Bom
assert movie.title == "Expected Title"
assert len(movies) == 3
assert movie_id.prefix == "mov"

# ❌ Evitar
assert movie.title  # Pouco informativo
assert movies       # Não verifica quantidade
```

### Para exceções

```python
# ✅ Verificar tipo e mensagem
with pytest.raises(DomainValidationError) as exc_info:
    MovieId("invalid")

assert "prefix" in str(exc_info.value).lower()

# ✅ Ou usar match
with pytest.raises(DomainValidationError, match="prefix"):
    MovieId("invalid")
```

### Para coleções

```python
# Verificar conteúdo
assert set(result) == {movie1, movie2}

# Verificar ordem
assert result == [movie1, movie2]

# Verificar que contém
assert movie in result
```

## Anti-patterns

### ❌ Múltiplos Acts

```python
# Ruim - testando duas coisas
def test_movie_id():
    id1 = MovieId.generate()
    assert id1.prefix == "mov"
    
    id2 = MovieId("mov_abc123abc123")
    assert id2.value == "mov_abc123abc123"
```

### ✅ Separar em testes distintos

```python
def test_should_generate_with_correct_prefix():
    movie_id = MovieId.generate()

    assert movie_id.prefix == "mov"


def test_should_accept_valid_string():
    movie_id = MovieId("mov_abc123abc123")

    assert movie_id.value == "mov_abc123abc123"
```

### ❌ Lógica no teste

```python
# Ruim - lógica condicional
def test_movie_validation():
    for title in ["", None, "   "]:
        if title is None:
            with pytest.raises(TypeError):
                Movie(title=title)
        else:
            with pytest.raises(ValueError):
                Movie(title=title)
```

### ✅ Usar parametrize

```python
@pytest.mark.parametrize("invalid_title", ["", "   "])
def test_should_raise_error_when_title_is_blank(invalid_title):
    with pytest.raises(DomainValidationError):
        Movie(title=invalid_title)
```

## Checklist

Antes de commitar, verificar:

- [ ] Nome do teste descreve o comportamento esperado
- [ ] Estrutura AAA clara (Arrange/Act/Assert)
- [ ] Um único Act por teste
- [ ] Assertions específicas e informativas
- [ ] Fixtures reutilizáveis quando apropriado
- [ ] Sem lógica condicional no teste
- [ ] Testes independentes (não dependem de ordem)
