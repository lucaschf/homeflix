# External API Integration Guide

Guia para integração com APIs externas no HomeFlix.

## Princípio Fundamental

> **Todo request para API externa deve ser auditado antes de processar a resposta.**

Isso garante rastreabilidade, debugging e compliance.

## O Que Auditar

### Campos Obrigatórios

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| `id` | ID único do audit | `api_abc123xyz789` |
| `provider` | Nome do provider | `"tmdb"`, `"omdb"` |
| `endpoint` | Endpoint chamado | `"/movie/550"` |
| `method` | Método HTTP | `"GET"` |
| `request_url` | URL completa | `"https://api.themoviedb.org/3/movie/550"` |
| `response_status` | Status HTTP | `200`, `404`, `500`, `null` |
| `response_body` | Resposta crua (JSON) | `{"id": 550, "title": "..."}` |
| `response_time_ms` | Latência | `234` |
| `success` | Se foi bem sucedido | `true`, `false` |
| `created_at` | Timestamp | `2025-01-29T12:00:00Z` |

### Campos de Contexto

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| `correlation_id` | Request ID da nossa API | `"req_xyz789"` |
| `domain_entity_type` | Tipo de entidade associada | `"Movie"`, `"Series"` |
| `domain_entity_id` | ID da entidade | `"mov_abc123"` |

### Campos de Erro

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| `error_type` | Tipo de erro | `"timeout"`, `"connection_error"` |
| `error_message` | Mensagem de erro | `"Connection refused"` |

## Status Codes - Salvar Todos

| Status | Salvar? | Por quê |
|--------|---------|---------|
| **2xx** | ✅ Sim | Resposta normal, dados para processar |
| **400** | ✅ Sim | Request inválido, bug no nosso código |
| **401/403** | ✅ Sim | Problema de autenticação |
| **404** | ✅ Sim | Recurso não existe, tentar outro provider |
| **429** | ✅ Sim | Rate limiting, ajustar frequência |
| **5xx** | ✅ Sim | Provider com problema, evidência |
| **Timeout** | ✅ Sim | Sem resposta, mas documenta falha |
| **Connection Error** | ✅ Sim | Provider fora do ar |

## Arquitetura

```
src/
├── domain/
│   └── audit/
│       ├── entities/
│       │   └── external_api_call.py
│       ├── value_objects/
│       │   └── ids.py                    # ApiCallId
│       └── repositories/
│           └── external_api_call_repository.py
│
├── infrastructure/
│   └── external/
│       ├── base_client.py                # Lógica de audit
│       ├── tmdb/
│       │   ├── tmdb_client.py
│       │   └── tmdb_mapper.py
│       └── omdb/
│           ├── omdb_client.py
│           └── omdb_mapper.py
```

## Implementação

### Entity de Audit

```python
# src/domain/audit/entities/external_api_call.py

@dataclass
class ExternalApiCall:
    """Record of an external API call."""
    
    id: ApiCallId
    provider: str
    endpoint: str
    method: str
    request_url: str
    response_time_ms: int
    success: bool
    created_at: datetime
    
    # Request details
    request_headers: dict[str, str] | None = None
    request_body: dict | None = None
    
    # Response details (null if no response)
    response_status: int | None = None
    response_headers: dict[str, str] | None = None
    response_body: dict | None = None
    
    # Error details (null if success)
    error_type: str | None = None
    error_message: str | None = None
    
    # Correlation
    correlation_id: str | None = None
    domain_entity_type: str | None = None
    domain_entity_id: str | None = None
```

### Base Client

```python
# src/infrastructure/external/base_client.py

class BaseExternalClient(ABC):
    """Base class for external API clients with auditing."""
    
    PROVIDER_NAME: ClassVar[str]  # Override in subclasses
    
    def __init__(
        self,
        audit_repository: ExternalApiCallRepository,
        base_url: str,
        timeout: float = 30.0,
    ):
        self._audit_repository = audit_repository
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=timeout)
        self._logger = get_logger().bind(provider=self.PROVIDER_NAME)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        correlation_id: str | None = None,
        domain_entity_type: str | None = None,
        domain_entity_id: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        """Make an audited HTTP request."""
        
        url = f"{self._base_url}{endpoint}"
        start_time = time.perf_counter()
        
        # Prepare audit record
        audit = ExternalApiCall(
            id=ApiCallId.generate(),
            provider=self.PROVIDER_NAME,
            endpoint=endpoint,
            method=method,
            request_url=url,
            request_headers=self._sanitize_headers(kwargs.get("headers", {})),
            request_body=kwargs.get("json"),
            correlation_id=correlation_id,
            domain_entity_type=domain_entity_type,
            domain_entity_id=domain_entity_id,
            response_time_ms=0,
            success=False,
            created_at=datetime.now(UTC),
        )
        
        try:
            response = await self._client.request(method, url, **kwargs)
            
            # Record response
            audit.response_status = response.status_code
            audit.response_headers = dict(response.headers)
            audit.response_body = self._safe_json(response)
            audit.success = 200 <= response.status_code < 300
            
            self._logger.info(
                "API call completed",
                endpoint=endpoint,
                status=response.status_code,
                success=audit.success,
            )
            
            return response
            
        except httpx.TimeoutException as e:
            audit.error_type = "timeout"
            audit.error_message = str(e)
            self._logger.warning("API call timeout", endpoint=endpoint)
            raise ExternalApiTimeoutException(self.PROVIDER_NAME, endpoint) from e
            
        except httpx.ConnectError as e:
            audit.error_type = "connection_error"
            audit.error_message = str(e)
            self._logger.error("API connection error", endpoint=endpoint, error=str(e))
            raise ExternalApiConnectionException(self.PROVIDER_NAME, endpoint) from e
            
        finally:
            # Calculate response time
            audit.response_time_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Save audit (non-blocking)
            asyncio.create_task(self._save_audit(audit))
    
    async def _save_audit(self, audit: ExternalApiCall) -> None:
        """Save audit record. Failures are logged but don't break the flow."""
        try:
            await self._audit_repository.save(audit)
        except Exception as e:
            self._logger.error(
                "Failed to save API audit",
                audit_id=str(audit.id),
                error=str(e),
            )
    
    def _sanitize_headers(self, headers: dict) -> dict:
        """Remove sensitive data from headers."""
        sensitive = {"authorization", "x-api-key", "api-key", "api_key"}
        return {
            k: "***REDACTED***" if k.lower() in sensitive else v
            for k, v in headers.items()
        }
    
    def _safe_json(self, response: httpx.Response) -> dict | None:
        """Safely parse JSON response."""
        if not response.content:
            return None
        try:
            body = response.json()
            # Truncate large responses
            if len(str(body)) > 1_000_000:  # 1MB
                return {"_truncated": True, "_size": len(str(body))}
            return body
        except Exception:
            return {"_raw": response.text[:1000]}  # First 1000 chars
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
```

### Client Específico (TMDB)

```python
# src/infrastructure/external/tmdb/tmdb_client.py

class TMDBClient(BaseExternalClient):
    """TMDB API client."""
    
    PROVIDER_NAME = "tmdb"
    
    def __init__(
        self,
        audit_repository: ExternalApiCallRepository,
        api_key: str,
        base_url: str = "https://api.themoviedb.org/3",
    ):
        super().__init__(audit_repository, base_url)
        self._api_key = api_key
    
    async def get_movie(
        self,
        tmdb_id: int,
        *,
        correlation_id: str | None = None,
        domain_entity_id: str | None = None,
    ) -> TMDBMovieResponse:
        """Fetch movie details from TMDB."""
        
        response = await self._request(
            "GET",
            f"/movie/{tmdb_id}",
            params={"api_key": self._api_key, "language": "pt-BR"},
            correlation_id=correlation_id,
            domain_entity_type="Movie",
            domain_entity_id=domain_entity_id,
        )
        
        if response.status_code == 404:
            raise MovieNotFoundInProviderException("tmdb", str(tmdb_id))
        
        response.raise_for_status()
        return TMDBMovieResponse(**response.json())
    
    async def search_movie(
        self,
        query: str,
        year: int | None = None,
        *,
        correlation_id: str | None = None,
    ) -> list[TMDBSearchResult]:
        """Search for movies in TMDB."""
        
        params = {"api_key": self._api_key, "query": query}
        if year:
            params["year"] = year
        
        response = await self._request(
            "GET",
            "/search/movie",
            params=params,
            correlation_id=correlation_id,
        )
        
        response.raise_for_status()
        data = response.json()
        return [TMDBSearchResult(**item) for item in data.get("results", [])]
```

## Boas Práticas

### ✅ Sempre passar correlation_id

```python
# No Use Case
class EnrichMovieUseCase:
    async def execute(self, input: EnrichMovieInput) -> Movie:
        # Propagar correlation_id para rastreabilidade
        tmdb_data = await self._tmdb_client.get_movie(
            input.tmdb_id,
            correlation_id=input.correlation_id,
            domain_entity_id=str(input.movie_id),
        )
        ...
```

### ✅ Associar ao domain entity quando possível

```python
# Permite queries como: "todas as chamadas para o filme mov_abc123"
await self._tmdb_client.get_movie(
    tmdb_id=550,
    domain_entity_type="Movie",
    domain_entity_id="mov_abc123",
)
```

### ✅ Tratar erros específicos

```python
try:
    movie_data = await tmdb_client.get_movie(tmdb_id)
except MovieNotFoundInProviderException:
    # Tentar outro provider
    movie_data = await omdb_client.get_movie(imdb_id)
except ExternalApiTimeoutException:
    # Usar cache ou falhar gracefully
    movie_data = await cache.get(f"movie:{tmdb_id}")
```

### ❌ Nunca logar API keys

```python
# ❌ ERRADO
logger.info("Calling TMDB", api_key=self._api_key)

# ✅ CERTO - sanitizado automaticamente no audit
# Headers com api_key são substituídos por ***REDACTED***
```

### ❌ Não salvar responses gigantes

```python
# O _safe_json já trunca responses > 1MB
# Mas se precisar mais controle:
if len(response.content) > 500_000:
    audit.response_body = {"_truncated": True}
```

## Queries Úteis

### Requests que falharam nas últimas 24h

```sql
SELECT * FROM external_api_calls
WHERE success = false
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

### Taxa de erro por provider

```sql
SELECT 
    provider,
    COUNT(*) as total,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM external_api_calls
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY provider;
```

### Tempo médio de resposta por endpoint

```sql
SELECT 
    provider,
    endpoint,
    AVG(response_time_ms) as avg_time,
    MAX(response_time_ms) as max_time,
    COUNT(*) as call_count
FROM external_api_calls
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY provider, endpoint
ORDER BY avg_time DESC;
```

### Todas as chamadas para um filme específico

```sql
SELECT * FROM external_api_calls
WHERE domain_entity_id = 'mov_abc123'
ORDER BY created_at DESC;
```

## Retenção de Dados

Recomendação de política de retenção:

| Tipo | Retenção | Motivo |
|------|----------|--------|
| Erros (success=false) | 180 dias | Debugging histórico |
| Sucesso com response | 90 dias | Cache e auditoria |
| Sucesso sem response | 30 dias | Só métricas |

```sql
-- Job de limpeza (rodar diariamente)
DELETE FROM external_api_calls
WHERE (success = false AND created_at < NOW() - INTERVAL '180 days')
   OR (success = true AND response_body IS NOT NULL AND created_at < NOW() - INTERVAL '90 days')
   OR (success = true AND response_body IS NULL AND created_at < NOW() - INTERVAL '30 days');
```

## Checklist de Implementação

- [ ] Criar entity `ExternalApiCall` em `domain/audit/`
- [ ] Criar `ApiCallId` value object
- [ ] Criar repository interface
- [ ] Implementar `BaseExternalClient` com audit
- [ ] Implementar `TMDBClient` extends base
- [ ] Implementar `OMDBClient` extends base
- [ ] Criar migration para tabela `external_api_calls`
- [ ] Configurar job de retenção/limpeza

---

## Retry e Circuit Breaker

Ver [ADR-006](../adr/ADR-006-retry-circuit-breaker.md) para decisões detalhadas.

### Retry com Tenacity

```python
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

class BaseExternalClient:
    RETRY_MAX_ATTEMPTS = 3
    RETRY_MIN_WAIT = 1   # segundos
    RETRY_MAX_WAIT = 10  # segundos
    
    async def _request_with_retry(self, method: str, endpoint: str, **kwargs):
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential_jitter(
                initial=self.RETRY_MIN_WAIT,
                max=self.RETRY_MAX_WAIT,
            ),
            retry=retry_if_exception_type((
                httpx.TimeoutException,
                httpx.ConnectError,
                RetryableStatusException,
            )),
            reraise=True,
        ):
            with attempt:
                response = await self._make_request(method, endpoint, **kwargs)
                
                if self._is_retryable_status(response.status_code):
                    raise RetryableStatusException(response.status_code)
                
                return response
```

### O Que Fazer Retry

| Status/Erro | Retry? | Motivo |
|-------------|--------|--------|
| **Timeout** | ✅ Sim | Falha transiente |
| **Connection Error** | ✅ Sim | Falha transiente |
| **503 Service Unavailable** | ✅ Sim | Servidor sobrecarregado |
| **502 Bad Gateway** | ✅ Sim | Problema de proxy |
| **500 Internal Error** | ⚠️ 1x | Pode ser transiente |
| **429 Rate Limit** | ✅ Sim | Com backoff maior |
| **404 Not Found** | ❌ Não | Recurso não existe |
| **401/403** | ❌ Não | Problema de auth |
| **400 Bad Request** | ❌ Não | Bug nosso |

### Tratando 429 Rate Limit

**Não fazer `sleep` prolongado.** A exceção deve propagar para cima:

```python
async def _handle_response(self, response: httpx.Response) -> httpx.Response:
    if response.status_code == 429:
        retry_after = self._parse_retry_after(response)
        
        # Retry automático apenas para delays curtos (≤ 5s)
        if retry_after and retry_after <= 5:
            raise RetryableStatusException(429)  # Tenacity fará retry
        
        # Delays longos: propagar para o caller decidir
        raise GatewayRateLimitException(
            message="Rate limit exceeded",
            gateway_name=self.PROVIDER_NAME,
            retry_after_seconds=retry_after or 60,
        )
    
    return response

def _parse_retry_after(self, response: httpx.Response) -> int | None:
    """Parse Retry-After header."""
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return int(retry_after)
    except ValueError:
        return None  # Pode ser HTTP date, usar default
```

### Quem Decide o Que Fazer com Rate Limit

| Camada | Responsabilidade |
|--------|------------------|
| **Client** | Detecta 429, retry se ≤5s, senão lança exceção |
| **Use Case** | Decide: fallback? cache? propagar erro? |
| **Presentation** | Retorna 429/503 com header `Retry-After` |

### Circuit Breaker

Evita cascata de falhas quando o provider está fora:

```python
class CircuitBreaker:
    """Simple circuit breaker implementation."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        name: str = "default",
    ):
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._timeout = timeout
        self._name = name
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._logger = get_logger().bind(circuit=name)
    
    @property
    def is_open(self) -> bool:
        if self._state == CircuitState.OPEN:
            # Check if timeout passed → move to half-open
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._logger.info("Circuit half-open, testing...")
                return False
            return True
        return False
    
    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return False
        return time.time() - self._last_failure_time >= self._timeout
    
    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._logger.info("Circuit closed, service recovered")
        else:
            self._failure_count = 0
    
    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._logger.warning("Circuit reopened after half-open failure")
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._logger.warning(
                "Circuit opened",
                failures=self._failure_count,
                threshold=self._failure_threshold,
            )


class CircuitState(Enum):
    CLOSED = "closed"      # Normal, requests passam
    OPEN = "open"          # Falha rápida, requests bloqueados
    HALF_OPEN = "half_open"  # Testando recuperação
```

### Fluxo Completo

```
Request
   │
   ▼
┌──────────────────┐
│ Circuit Breaker  │──── OPEN ────► CircuitOpenException (fast fail)
└──────────────────┘
   │ CLOSED/HALF_OPEN
   ▼
┌──────────────────┐
│  Retry Policy    │
│  (até 3 tentativas)
└──────────────────┘
   │
   ├── Sucesso ──► record_success() ──► Return response
   │
   └── Falha após retries ──► record_failure() ──► Raise exception
                                    │
                                    ▼
                            Se failures >= 5
                                    │
                                    ▼
                            Circuit abre
```

### Configuração por Provider

```python
class TMDBClient(BaseExternalClient):
    PROVIDER_NAME = "tmdb"
    
    # Override se necessário
    RETRY_MAX_ATTEMPTS = 3
    CIRCUIT_FAILURE_THRESHOLD = 5
    CIRCUIT_TIMEOUT = 30


class OMDBClient(BaseExternalClient):
    PROVIDER_NAME = "omdb"
    
    # OMDb é mais instável, ser mais conservador
    RETRY_MAX_ATTEMPTS = 2
    CIRCUIT_FAILURE_THRESHOLD = 3
    CIRCUIT_TIMEOUT = 60
```

### Fallback quando Circuit Aberto ou Rate Limited

**NÃO** coloque lógica de fallback no Use Case. Use o padrão **Ports & Adapters**:

```
Application                          Infrastructure
     │                                     │
     │  MetadataProvider (interface)       │
     │◄────────────────────────────────────┤
     │                                     │
                                    MetadataProviderWithFallback
                                           │
                                    ┌──────┴──────┐
                                    │             │
                                TMDBClient   OMDBClient
```

#### Port (Interface na Application)

```python
# src/application/media/ports/metadata_provider.py
class MetadataProvider(ABC):
    """Port for fetching media metadata from external sources."""
    
    @abstractmethod
    async def get_movie_by_id(
        self,
        *,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
    ) -> MovieMetadata | None:
        ...
```

#### Adapter (Implementação na Infrastructure)

```python
# src/infrastructure/external/metadata_provider.py
class MetadataProviderWithFallback(MetadataProvider):
    """Metadata provider with automatic fallback between sources."""
    
    def __init__(
        self,
        primary: TMDBClient,
        fallback: OMDBClient | None = None,
    ):
        self._primary = primary
        self._fallback = fallback
        self._logger = get_logger().bind(service="MetadataProvider")
    
    async def get_movie_by_id(self, ...) -> MovieMetadata | None:
        try:
            return await self._primary.get_movie(tmdb_id=tmdb_id)
            
        except (GatewayRateLimitException, CircuitOpenException, GatewayTimeoutException) as e:
            if not self._fallback:
                raise
            
            self._logger.warning(
                "Primary provider failed, trying fallback",
                primary="tmdb",
                fallback="omdb",
                error=type(e).__name__,
            )
            return await self._fallback.get_movie(imdb_id=imdb_id)
```

#### Use Case Limpo

```python
# src/application/media/use_cases/enrich_movie.py
class EnrichMovieUseCase:
    def __init__(self, metadata_provider: MetadataProvider):  # ✅ Interface
        self._metadata_provider = metadata_provider
    
    async def execute(self, input: EnrichMovieInput) -> Movie:
        metadata = await self._metadata_provider.get_movie_by_id(
            tmdb_id=input.tmdb_id,
            imdb_id=input.imdb_id,
        )
        
        if metadata:
            movie = self._apply_metadata(movie, metadata)
        
        return movie
```

#### Wiring no Container

```python
# src/config/containers/infrastructure.py
class InfrastructureContainer(containers.DeclarativeContainer):
    tmdb_client = providers.Singleton(TMDBClient, ...)
    omdb_client = providers.Singleton(OMDBClient, ...)
    
    metadata_provider = providers.Singleton(
        MetadataProviderWithFallback,
        primary=tmdb_client,
        fallback=omdb_client,
    )
```

### Por Que Essa Arquitetura?

| Abordagem | Onde fica fallback | Use Case conhece |
|-----------|-------------------|------------------|
| ❌ Errada | Use Case | TMDBClient, OMDBClient |
| ✅ Correta | Infrastructure | MetadataProvider (interface) |

Benefícios:
- **Testabilidade**: Mock apenas `MetadataProvider` no Use Case
- **Flexibilidade**: Trocar providers sem mudar Application
- **Single Responsibility**: Use Case não conhece detalhes de resiliência
- **Open/Closed**: Adicionar providers sem modificar Use Cases

### Métricas Importantes

```python
# Log quando circuit muda de estado
logger.warning("Circuit opened", provider="tmdb", failures=5)
logger.info("Circuit half-open", provider="tmdb")
logger.info("Circuit closed", provider="tmdb", recovery_time_s=45)

# Métricas para monitoramento
- circuit_state{provider="tmdb"} = 0/1/2 (closed/open/half_open)
- retry_attempts_total{provider="tmdb", attempt="1/2/3"}
- circuit_trips_total{provider="tmdb"}
```

### Dependências

```bash
poetry add tenacity
```

O circuit breaker pode ser implementado manualmente (como acima) ou usar `pybreaker`:

```bash
poetry add pybreaker  # opcional
```
