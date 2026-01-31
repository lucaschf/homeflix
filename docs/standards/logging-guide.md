# Logging Guide

Guia de estilo para logging no HomeFlix usando `structlog`.

## Clean Architecture e Logging

### Logging é um Cross-Cutting Concern

Logging não é regra de negócio - é observabilidade. Por isso, tratamos de forma pragmática:

| Dependência | Injetar via DI? | Motivo |
|-------------|-----------------|--------|
| **Repository** | ✅ Sim | Afeta comportamento, precisa mockar |
| **External API** | ✅ Sim | Afeta comportamento, precisa mockar |
| **Logger** | ❌ Não | Cross-cutting, não afeta resultado |
| **Clock/Time** | ⚠️ Depende | Se precisar testar tempo, injeta |

### Por que Logger não é injetado?

1. **Não afeta comportamento** - Remover logs não muda o resultado
2. **Testabilidade preservada** - Não precisa mockar em testes unitários
3. **Reduz boilerplate** - Evita passar logger em todo construtor
4. **Padrão da indústria** - Abordagem comum em projetos Python

```python
# ❌ Purista demais - boilerplate desnecessário
class GetMovieUseCase:
    def __init__(self, repository: MovieRepository, logger: Logger):
        self._repository = repository
        self._logger = logger

# ✅ Pragmático - aceito pela comunidade
class GetMovieUseCase:
    def __init__(self, repository: MovieRepository):
        self._repository = repository
        self._logger = get_logger().bind(use_case="GetMovie")
```

### Quem pode logar?

| Camada | Loga? | Motivo |
|--------|-------|--------|
| **Domain** | ❌ Não | Deve ser puro, sem dependências externas |
| **Application** | ✅ Sim | Orquestra operações, ponto ideal para observar |
| **Infrastructure** | ✅ Sim | I/O, queries, chamadas externas |
| **Presentation** | ✅ Sim | Requests, responses, erros HTTP |

### Regra de Ouro

```
Domain = Regras de negócio puras (lança exceções)
Application/Infra/Presentation = Orquestra e observa (loga)
```

---

## Configuração

O logging é configurado automaticamente no startup da aplicação:

- **Development**: Console colorido, formato legível
- **Production**: JSON, para log aggregators (ELK, Datadog, etc.)

A configuração é baseada em:
- `APP_ENV`: development vs production
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Uso Básico

```python
from src.config.logging import get_logger

logger = get_logger()

# Log simples
logger.info("User logged in")

# Log com contexto (key-value pairs)
logger.info("User logged in", user_id="123", action="login")

# Níveis de log
logger.debug("Detailed info for debugging")
logger.info("General information")
logger.warning("Something unexpected but not critical")
logger.error("Error occurred", error=str(e))
logger.critical("System is down")
```

## Context Binding

Use `bind()` para adicionar contexto que persiste em todas as chamadas:

```python
# Bind uma vez, usa em todos os logs
logger = get_logger().bind(request_id="req_abc123", user_id="usr_456")

logger.info("Processing request")      # Inclui request_id e user_id
logger.info("Fetching from database")  # Inclui request_id e user_id
logger.info("Request completed")       # Inclui request_id e user_id
```

### Contexto por Camada

```python
# Em um middleware ou route
logger = get_logger().bind(request_id=request_id)

# Em um use case
logger = get_logger().bind(request_id=request_id, use_case="GetMovie")

# Em um repository
logger = get_logger().bind(request_id=request_id, repository="MovieRepository")
```

## Output

### Development (Console)

```
2025-01-29 12:00:00 [info     ] Application starting           app_name=HomeFlix environment=development
2025-01-29 12:00:01 [info     ] User logged in                 user_id=123 action=login
2025-01-29 12:00:02 [warning  ] Rate limit approaching         current=95 limit=100
2025-01-29 12:00:03 [error    ] Database connection failed     error=Connection refused
```

### Production (JSON)

```json
{"timestamp": "2025-01-29T12:00:00.000000Z", "level": "info", "event": "Application starting", "app_name": "HomeFlix", "environment": "production"}
{"timestamp": "2025-01-29T12:00:01.000000Z", "level": "info", "event": "User logged in", "user_id": "123", "action": "login"}
{"timestamp": "2025-01-29T12:00:02.000000Z", "level": "warning", "event": "Rate limit approaching", "current": 95, "limit": 100}
{"timestamp": "2025-01-29T12:00:03.000000Z", "level": "error", "event": "Database connection failed", "error": "Connection refused"}
```

## Boas Práticas

### ✅ Use Structured Data

```python
# ✅ Bom - dados estruturados, fácil de filtrar
logger.info("Movie fetched", movie_id="mov_123", title="Inception", duration_ms=45)

# ❌ Ruim - dados no texto, difícil de parsear
logger.info(f"Fetched movie mov_123 (Inception) in 45ms")
```

### ✅ Log no Início e Fim de Operações

```python
async def scan_library(self, directory: str) -> ScanResult:
    logger.info("Library scan started", directory=directory)
    
    try:
        result = await self._do_scan(directory)
        logger.info(
            "Library scan completed",
            directory=directory,
            movies_found=result.movies_count,
            duration_ms=result.duration_ms,
        )
        return result
    except Exception as e:
        logger.error("Library scan failed", directory=directory, error=str(e))
        raise
```

### ✅ Use Níveis Apropriados

| Nível | Quando Usar |
|-------|-------------|
| `DEBUG` | Detalhes internos, útil para debugging |
| `INFO` | Eventos normais de negócio (login, scan, etc.) |
| `WARNING` | Algo inesperado mas não crítico (retry, fallback) |
| `ERROR` | Erro que afeta uma operação específica |
| `CRITICAL` | Sistema comprometido, precisa de atenção imediata |

### ✅ Inclua Contexto Relevante

```python
# ✅ Contexto suficiente para debugging
logger.error(
    "Failed to fetch movie metadata",
    movie_id="mov_123",
    tmdb_id="tt1234567",
    error=str(e),
    retry_count=3,
)

# ❌ Contexto insuficiente
logger.error("Failed to fetch metadata")
```

### ✅ Evite Logs Excessivos

```python
# ❌ Ruim - log dentro de loop
for movie in movies:
    logger.debug("Processing movie", movie_id=movie.id)
    process(movie)

# ✅ Bom - log resumido
logger.info("Processing movies", count=len(movies))
for movie in movies:
    process(movie)
logger.info("Movies processed", count=len(movies))
```

### ✅ Não Logue Dados Sensíveis

```python
# ❌ NUNCA faça isso
logger.info("User authenticated", password=password, api_key=api_key)

# ✅ Bom
logger.info("User authenticated", user_id=user_id)
```

## Logging em Testes

Em testes, o logging é desabilitado por padrão. Para debugar:

```python
import structlog

def test_something_with_logs(caplog):
    # Habilita logs no teste
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    )
    
    # Seu teste aqui
    ...
```

## Integração com Request ID

Para rastrear logs de uma request:

```python
# Middleware (futuro)
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    
    # Bind ao contexto global (disponível em toda a request)
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    # Limpa o contexto
    structlog.contextvars.unbind_contextvars("request_id")
    
    return response
```

## Referências

- [structlog Documentation](https://www.structlog.org/)
- [Twelve-Factor App - Logs](https://12factor.net/logs)
