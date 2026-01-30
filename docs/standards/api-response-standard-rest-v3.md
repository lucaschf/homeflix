# Padrão de Resposta de API REST v3.0

## Changelog v3.0

- **Removido** `processing_time_ms` do corpo → movido para header `Server-Timing`
- **Removido** `cache_hit` do corpo → movido para header `X-Cache`
- **Removido** `deprecation_warning` do corpo → movido para header `Deprecation`
- **Simplificado** estrutura de erro: removido aninhamento redundante
- **Simplificado** `metadata`: agora contém apenas `filters_applied`

## Changelog v2.0

- Removido `id` de requisição do corpo (movido para header `X-Request-ID`)
- Corrigido paginação: `total` agora é opcional, cursor-based é recomendado
- Corrigido versionamento: apenas URI (`/v1/`)
- Documentado DELETE 204 como exceção explícita

---

## Visão Geral

Padrão de design para APIs RESTful otimizado para **cache HTTP**, **performance em escala** e **Developer Experience (DX)**.

### Princípios do Design

1. **Cacheabilidade**: Corpo contém apenas dados estáveis do recurso
2. **Separação**: Metadados voláteis vão em headers, não no payload
3. **Simplicidade**: Estruturas sem aninhamento desnecessário
4. **Performance**: Evitar operações custosas por padrão

---

## Estrutura de Respostas de Sucesso

### Recurso Único

```json
{
  "type": "user",
  "data": {
    "id": "usr_123",
    "name": "João Silva",
    "email": "joao@example.com",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

### Coleção de Recursos

```json
{
  "type": "list",
  "data": [
    {
      "id": "usr_123",
      "name": "João Silva"
    },
    {
      "id": "usr_456",
      "name": "Maria Santos"
    }
  ],
  "pagination": {
    "has_more": true,
    "next_cursor": "cur_abc123"
  }
}
```

### Coleção com Filtros Aplicados

```json
{
  "type": "list",
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "cur_abc123"
  },
  "metadata": {
    "filters_applied": {
      "status": "active",
      "role": "admin"
    }
  }
}
```

### Campos da Resposta

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `type` | string | Sim | Tipo do recurso ou `list` para coleções |
| `data` | object/array | Sim | Dados do recurso |
| `pagination` | object | Condicional | Apenas em listagens |
| `metadata` | object | Não | Apenas `filters_applied` (dados estáveis) |

### Sobre o campo `type`

O `type` na raiz é mantido por:
- Facilitar type guards em TypeScript/SDKs
- Permitir evolução para respostas polimórficas sem breaking changes
- Overhead negligível (~15 bytes) comparado a benefícios de extensibilidade

---

## Estrutura de Erros

### Formato (Simplificado na v3.0)

```json
{
  "type": "not_found_error",
  "message": "Usuário com ID 'usr_123' não encontrado.",
  "code": "USER_NOT_FOUND",
  "param": "user_id",
  "details": {
    "resource_type": "user",
    "resource_id": "usr_123"
  }
}
```

**Mudança v3.0:** Removido wrapper `{ "type": "error", "error": {...} }`. Erro agora é flat.

### Campos do Erro

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `type` | string | Sim | Categoria do erro |
| `message` | string | Sim | Mensagem legível para humanos |
| `code` | string | Recomendado | Código específico para programação |
| `param` | string | Não | Parâmetro que causou o erro |
| `details` | object | Não | Informações adicionais para debug |

### Diferenciando Sucesso de Erro

```typescript
// TypeScript - Type Guard
function isError(response: ApiResponse): response is ErrorResponse {
  return response.type.endsWith('_error');
}

// Ou pelo status code HTTP (recomendado)
if (response.status >= 400) {
  // É erro
}
```

---

## Mapeamento de Status Codes HTTP

| HTTP Status | Error Type | Descrição | Retry? |
|-------------|------------|-----------|--------|
| **200** | - | Sucesso | - |
| **201** | - | Recurso criado | - |
| **202** | - | Aceito (async) | - |
| **204** | - | Sucesso sem conteúdo | - |
| **400** | `invalid_request_error` | Requisição malformada | Não |
| **401** | `authentication_error` | Não autenticado | Não |
| **403** | `permission_error` | Sem permissão | Não |
| **404** | `not_found_error` | Recurso não existe | Não |
| **409** | `conflict_error` | Conflito de estado | Condicional |
| **413** | `request_too_large_error` | Payload muito grande | Não |
| **422** | `validation_error` | Dados inválidos | Não |
| **429** | `rate_limit_error` | Rate limit excedido | Sim |
| **500** | `api_error` | Erro interno | Sim |
| **502** | `bad_gateway_error` | Erro de gateway | Sim |
| **503** | `service_unavailable_error` | Serviço indisponível | Sim |
| **529** | `overloaded_error` | Sistema sobrecarregado | Sim |

---

## Detalhamento dos Erros

### 400 - Invalid Request Error

```json
{
  "type": "invalid_request_error",
  "message": "O campo 'email' deve ser uma string.",
  "code": "INVALID_TYPE",
  "param": "email",
  "details": {
    "expected": "string",
    "received": "number"
  }
}
```

### 401 - Authentication Error

```json
{
  "type": "authentication_error",
  "message": "Token de acesso inválido ou expirado.",
  "code": "INVALID_TOKEN"
}
```

### 403 - Permission Error

```json
{
  "type": "permission_error",
  "message": "Você não tem permissão para acessar este recurso.",
  "code": "FORBIDDEN",
  "details": {
    "required_role": "admin",
    "current_role": "user"
  }
}
```

### 404 - Not Found Error

```json
{
  "type": "not_found_error",
  "message": "Pedido não encontrado.",
  "code": "ORDER_NOT_FOUND",
  "param": "order_id"
}
```

### 409 - Conflict Error

```json
{
  "type": "conflict_error",
  "message": "Este email já está cadastrado.",
  "code": "EMAIL_ALREADY_EXISTS",
  "param": "email"
}
```

### 422 - Validation Error

```json
{
  "type": "validation_error",
  "message": "Erros de validação encontrados.",
  "code": "VALIDATION_FAILED",
  "details": {
    "errors": [
      {
        "field": "birth_date",
        "message": "Data não pode ser no futuro",
        "code": "DATE_IN_FUTURE"
      },
      {
        "field": "quantity",
        "message": "Deve ser maior que zero",
        "code": "MIN_VALUE"
      }
    ]
  }
}
```

### 429 - Rate Limit Error

```json
{
  "type": "rate_limit_error",
  "message": "Limite de requisições excedido. Tente novamente em 45 segundos.",
  "code": "RATE_LIMIT_EXCEEDED",
  "details": {
    "limit": 100,
    "window": "1m",
    "retry_after_seconds": 45
  }
}
```

### 500 - API Error

```json
{
  "type": "api_error",
  "message": "Ocorreu um erro interno. Nossa equipe foi notificada.",
  "code": "INTERNAL_ERROR",
  "details": {
    "incident_id": "inc_2025011500123"
  }
}
```

### 503 - Service Unavailable Error

```json
{
  "type": "service_unavailable_error",
  "message": "Sistema em manutenção programada.",
  "code": "MAINTENANCE"
}
```

---

## Headers Padrão

### Requisição

| Header | Obrigatório | Descrição |
|--------|-------------|-----------|
| `Authorization` | Sim | `Bearer {token}` |
| `Content-Type` | Sim | `application/json` |
| `X-Request-ID` | Não | ID de correlação (cliente) |
| `X-Idempotency-Key` | Não | Para requisições idempotentes |

### Resposta - Sempre Presentes

| Header | Descrição |
|--------|-----------|
| `X-Request-ID` | ID único para tracing |
| `X-RateLimit-Limit` | Limite total no período |
| `X-RateLimit-Remaining` | Requisições restantes |
| `X-RateLimit-Reset` | Timestamp Unix do reset |

### Resposta - Condicionais

| Header | Quando Usar | Descrição |
|--------|-------------|-----------|
| `Server-Timing` | Sempre (debug) | Tempo de processamento |
| `ETag` | GET de recursos | Hash do conteúdo para cache |
| `Cache-Control` | GET de recursos | Diretivas de cache |
| `X-Cache` | Se usar cache | `HIT` ou `MISS` |
| `Retry-After` | Erros 429/503 | Segundos para retry |
| `Deprecation` | APIs depreciadas | Data de descontinuação |
| `Link` | APIs depreciadas | URL da documentação de migração |

### Exemplo de Headers de Performance

```http
HTTP/1.1 200 OK
X-Request-ID: req_01HQ9XYZ
Server-Timing: db;dur=12, render;dur=3, total;dur=45
ETag: "a1b2c3d4"
Cache-Control: private, max-age=60
X-Cache: MISS
```

### Exemplo de Headers de Depreciação

```http
HTTP/1.1 200 OK
Deprecation: Sun, 01 Jun 2025 00:00:00 GMT
Link: <https://docs.api.com/migrations/v2>; rel="deprecation"
Sunset: Sun, 01 Sep 2025 00:00:00 GMT
```

---

## Versionamento

Use **URI Versioning** exclusivamente:

```
/v1/users
/v2/users
```

**Razões:**
- Fácil de testar (browser, curl)
- Fácil de rotear (nginx, load balancers)
- Cacheável por CDNs
- Sem ambiguidade

---

## Paginação

### Cursor-based (Recomendado)

```json
{
  "type": "list",
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "prev_cursor": "eyJpZCI6ODF9"
  }
}
```

**Request:** `GET /v1/users?cursor=eyJpZCI6MTAwfQ==&limit=20`

### Offset-based (Datasets Pequenos)

```json
{
  "type": "list",
  "data": [...],
  "pagination": {
    "page": 2,
    "per_page": 20,
    "has_more": true
  }
}
```

### Campo `total` (Opt-in)

**⚠️ Não inclua por padrão.** `COUNT(*)` é custoso.

```
GET /v1/users?include_total=true
```

---

## Exceções ao Envelope

### DELETE retorna 204 (sem corpo)

```http
DELETE /v1/users/usr_123 HTTP/1.1

HTTP/1.1 204 No Content
X-Request-ID: req_abc123
```

**Tratamento:**

```python
def handle_response(response):
    if response.status_code == 204:
        return None
    return response.json()
```

---

## Exemplos CRUD Completos

### CREATE - POST /v1/users

**Request:**
```http
POST /v1/users HTTP/1.1
Content-Type: application/json
Authorization: Bearer token_xyz
X-Idempotency-Key: idem_abc123

{
  "name": "João Silva",
  "email": "joao@example.com"
}
```

**Response 201:**
```http
HTTP/1.1 201 Created
X-Request-ID: req_01HQ9XYZ
Location: /v1/users/usr_789xyz
Server-Timing: total;dur=23

{
  "type": "user",
  "data": {
    "id": "usr_789xyz",
    "name": "João Silva",
    "email": "joao@example.com",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response 409:**
```json
{
  "type": "conflict_error",
  "message": "Email já cadastrado.",
  "code": "EMAIL_EXISTS",
  "param": "email"
}
```

---

### READ - GET /v1/users/:id

**Request:**
```http
GET /v1/users/usr_789xyz HTTP/1.1
Authorization: Bearer token_xyz
```

**Response 200:**
```http
HTTP/1.1 200 OK
X-Request-ID: req_01HQ9ABC
Server-Timing: db;dur=5, total;dur=12
ETag: "a1b2c3d4"
Cache-Control: private, max-age=60

{
  "type": "user",
  "data": {
    "id": "usr_789xyz",
    "name": "João Silva",
    "email": "joao@example.com",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response 304 (Cache Hit):**
```http
HTTP/1.1 304 Not Modified
X-Request-ID: req_01HQ9DEF
ETag: "a1b2c3d4"
```

---

### UPDATE - PATCH /v1/users/:id

**Request:**
```http
PATCH /v1/users/usr_789xyz HTTP/1.1
Content-Type: application/json
Authorization: Bearer token_xyz

{
  "name": "João Santos Silva"
}
```

**Response 200:**
```http
HTTP/1.1 200 OK
X-Request-ID: req_01HQ9GHI
Server-Timing: total;dur=18

{
  "type": "user",
  "data": {
    "id": "usr_789xyz",
    "name": "João Santos Silva",
    "email": "joao@example.com",
    "updated_at": "2025-01-15T11:45:00Z"
  }
}
```

---

### DELETE - DELETE /v1/users/:id

**Request:**
```http
DELETE /v1/users/usr_789xyz HTTP/1.1
Authorization: Bearer token_xyz
```

**Response 204:**
```http
HTTP/1.1 204 No Content
X-Request-ID: req_01HQ9JKL
Server-Timing: total;dur=8
```

---

### LIST - GET /v1/users

**Request:**
```http
GET /v1/users?limit=20&status=active HTTP/1.1
Authorization: Bearer token_xyz
```

**Response 200:**
```http
HTTP/1.1 200 OK
X-Request-ID: req_01HQ9MNO
Server-Timing: db;dur=15, total;dur=22

{
  "type": "list",
  "data": [
    {
      "id": "usr_001",
      "name": "Admin Master",
      "email": "admin@example.com"
    },
    {
      "id": "usr_002",
      "name": "Admin Junior",
      "email": "junior@example.com"
    }
  ],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6InVzcl8wMDIifQ=="
  },
  "metadata": {
    "filters_applied": {
      "status": "active"
    }
  }
}
```

---

## Implementação

### Python + Pydantic

```python
from typing import Literal, Optional, Any, Generic, TypeVar
from pydantic import BaseModel
from enum import Enum

T = TypeVar('T')


class ErrorType(str, Enum):
    INVALID_REQUEST = "invalid_request_error"
    AUTHENTICATION = "authentication_error"
    PERMISSION = "permission_error"
    NOT_FOUND = "not_found_error"
    CONFLICT = "conflict_error"
    REQUEST_TOO_LARGE = "request_too_large_error"
    VALIDATION = "validation_error"
    RATE_LIMIT = "rate_limit_error"
    API_ERROR = "api_error"
    BAD_GATEWAY = "bad_gateway_error"
    SERVICE_UNAVAILABLE = "service_unavailable_error"
    OVERLOADED = "overloaded_error"


# Erro simplificado (v3.0 - sem wrapper)
class ErrorResponse(BaseModel):
    type: ErrorType
    message: str
    code: Optional[str] = None
    param: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class CursorPagination(BaseModel):
    has_more: bool = False
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    total: Optional[int] = None


class ResponseMetadata(BaseModel):
    filters_applied: Optional[dict[str, Any]] = None


class SingleResponse(BaseModel, Generic[T]):
    type: str
    data: T


class ListResponse(BaseModel, Generic[T]):
    type: Literal["list"] = "list"
    data: list[T]
    pagination: Optional[CursorPagination] = None
    metadata: Optional[ResponseMetadata] = None
```

### Helpers de Resposta

```python
def success(data: Any, resource_type: str) -> dict:
    """Resposta de sucesso para recurso único."""
    return {"type": resource_type, "data": data}


def success_list(
    data: list,
    has_more: bool = False,
    next_cursor: str = None,
    filters: dict = None
) -> dict:
    """Resposta de sucesso para lista."""
    response = {
        "type": "list",
        "data": data,
        "pagination": {"has_more": has_more}
    }
    
    if next_cursor:
        response["pagination"]["next_cursor"] = next_cursor
    
    if filters:
        response["metadata"] = {"filters_applied": filters}
    
    return response


def error(
    error_type: ErrorType,
    message: str,
    code: str = None,
    param: str = None,
    details: dict = None
) -> dict:
    """Resposta de erro (v3.0 - flat, sem wrapper)."""
    err = {"type": error_type.value, "message": message}
    if code:
        err["code"] = code
    if param:
        err["param"] = param
    if details:
        err["details"] = details
    return err


# Erros específicos
def bad_request(message: str, code: str = None, param: str = None):
    return error(ErrorType.INVALID_REQUEST, message, code, param), 400

def unauthorized(message: str = "Não autenticado"):
    return error(ErrorType.AUTHENTICATION, message, "UNAUTHORIZED"), 401

def forbidden(message: str = "Sem permissão"):
    return error(ErrorType.PERMISSION, message, "FORBIDDEN"), 403

def not_found(resource: str):
    return error(ErrorType.NOT_FOUND, f"{resource} não encontrado", f"{resource.upper()}_NOT_FOUND"), 404

def conflict(message: str, code: str = None):
    return error(ErrorType.CONFLICT, message, code), 409

def validation_error(errors: list[dict]):
    return error(ErrorType.VALIDATION, "Erros de validação", "VALIDATION_FAILED", details={"errors": errors}), 422

def rate_limited(retry_after: int):
    return error(ErrorType.RATE_LIMIT, f"Tente em {retry_after}s", "RATE_LIMIT_EXCEEDED", details={"retry_after_seconds": retry_after}), 429

def internal_error(incident_id: str = None):
    details = {"incident_id": incident_id} if incident_id else None
    return error(ErrorType.API_ERROR, "Erro interno", "INTERNAL_ERROR", details=details), 500
```

### FastAPI - Completo

```python
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uuid
import time

app = FastAPI()

ERROR_TYPE_MAP = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    409: "conflict_error",
    422: "validation_error",
    429: "rate_limit_error",
    500: "api_error",
    503: "service_unavailable_error",
}


@app.middleware("http")
async def add_headers(request: Request, call_next):
    start = time.perf_counter()
    
    # Request ID
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = request_id
    
    response: Response = await call_next(request)
    
    # Headers padrão
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"total;dur={duration_ms:.0f}"
    
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(x) for x in err["loc"][1:]),
            "message": err["msg"],
            "code": err["type"]
        }
        for err in exc.errors()
    ]
    
    return JSONResponse(
        status_code=422,
        content={
            "type": "validation_error",
            "message": "Erros de validação encontrados",
            "code": "VALIDATION_FAILED",
            "details": {"errors": errors}
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_type = ERROR_TYPE_MAP.get(exc.status_code, "api_error")
    
    # Suporta detail como string ou dict
    if isinstance(exc.detail, dict):
        content = {"type": error_type, **exc.detail}
    else:
        content = {"type": error_type, "message": exc.detail}
    
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    import logging
    logging.exception("Erro não tratado")
    
    return JSONResponse(
        status_code=500,
        content={
            "type": "api_error",
            "message": "Erro interno",
            "code": "INTERNAL_ERROR"
        }
    )


# === Endpoints ===

@app.get("/v1/users/{user_id}")
async def get_user(user_id: str, response: Response):
    user = await find_user(user_id)
    if not user:
        raise HTTPException(404, {"message": "Usuário não encontrado", "code": "USER_NOT_FOUND"})
    
    # ETag para cache
    import hashlib
    etag = hashlib.md5(str(user).encode()).hexdigest()[:8]
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "private, max-age=60"
    
    return {"type": "user", "data": user}


@app.get("/v1/users")
async def list_users(
    cursor: str = None,
    limit: int = 20,
    status: str = None,
    include_total: bool = False
):
    filters = {}
    if status:
        filters["status"] = status
    
    users, next_cursor, total = await find_users(cursor, limit, status, include_total)
    
    response = {
        "type": "list",
        "data": users,
        "pagination": {"has_more": next_cursor is not None}
    }
    
    if next_cursor:
        response["pagination"]["next_cursor"] = next_cursor
    
    if include_total and total is not None:
        response["pagination"]["total"] = total
    
    if filters:
        response["metadata"] = {"filters_applied": filters}
    
    return response


@app.post("/v1/users", status_code=201)
async def create_user(body: dict, response: Response):
    user = await insert_user(body)
    response.headers["Location"] = f"/v1/users/{user['id']}"
    return {"type": "user", "data": user}


@app.patch("/v1/users/{user_id}")
async def update_user(user_id: str, body: dict):
    user = await modify_user(user_id, body)
    if not user:
        raise HTTPException(404, {"message": "Usuário não encontrado", "code": "USER_NOT_FOUND"})
    return {"type": "user", "data": user}


@app.delete("/v1/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    deleted = await remove_user(user_id)
    if not deleted:
        raise HTTPException(404, {"message": "Usuário não encontrado", "code": "USER_NOT_FOUND"})
    return None
```

### TypeScript - Tipos

```typescript
// === Tipos de Erro ===

type ErrorType =
  | 'invalid_request_error'
  | 'authentication_error'
  | 'permission_error'
  | 'not_found_error'
  | 'conflict_error'
  | 'request_too_large_error'
  | 'validation_error'
  | 'rate_limit_error'
  | 'api_error'
  | 'bad_gateway_error'
  | 'service_unavailable_error'
  | 'overloaded_error';

// v3.0: Erro flat, sem wrapper
interface ErrorResponse {
  type: ErrorType;
  message: string;
  code?: string;
  param?: string;
  details?: Record<string, unknown>;
}

// === Tipos de Sucesso ===

interface CursorPagination {
  has_more: boolean;
  next_cursor?: string;
  prev_cursor?: string;
  total?: number;
}

interface ResponseMetadata {
  filters_applied?: Record<string, unknown>;
}

interface SingleResponse<T> {
  type: string;
  data: T;
}

interface ListResponse<T> {
  type: 'list';
  data: T[];
  pagination?: CursorPagination;
  metadata?: ResponseMetadata;
}

// === União e Type Guards ===

type ApiResponse<T> = SingleResponse<T> | ListResponse<T> | ErrorResponse;

function isError(response: ApiResponse<unknown>): response is ErrorResponse {
  return (response.type as string).endsWith('_error');
}

function isList<T>(response: ApiResponse<T>): response is ListResponse<T> {
  return response.type === 'list';
}

// === Cliente HTTP ===

async function apiRequest<T>(
  url: string,
  options?: RequestInit
): Promise<SingleResponse<T> | ListResponse<T>> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  // DELETE 204: sem corpo
  if (response.status === 204) {
    return null as any;
  }

  const data = await response.json();

  if (!response.ok || isError(data)) {
    throw new ApiError(data as ErrorResponse, response.status);
  }

  return data;
}

class ApiError extends Error {
  constructor(
    public readonly error: ErrorResponse,
    public readonly status: number
  ) {
    super(error.message);
    this.name = 'ApiError';
  }

  get isRetryable(): boolean {
    return ['rate_limit_error', 'api_error', 'service_unavailable_error', 'overloaded_error']
      .includes(this.error.type);
  }
}
```

---

## Estratégia de Retry

| Error Type | Retry | Estratégia |
|------------|-------|------------|
| `rate_limit_error` | ✅ | Respeitar `Retry-After` |
| `api_error` | ✅ | Backoff exponencial, max 3x |
| `bad_gateway_error` | ✅ | Backoff exponencial, max 3x |
| `service_unavailable_error` | ✅ | Respeitar `Retry-After` |
| `overloaded_error` | ✅ | Respeitar `Retry-After` |
| Outros | ❌ | Não fazer retry |

```python
import time
import random

RETRYABLE = {
    "rate_limit_error", 
    "api_error", 
    "bad_gateway_error", 
    "service_unavailable_error", 
    "overloaded_error"
}

def with_retry(fn, max_attempts=3, base_delay=1.0):
    for attempt in range(max_attempts):
        try:
            return fn()
        except ApiException as e:
            if e.error_type not in RETRYABLE or attempt == max_attempts - 1:
                raise
            
            delay = e.retry_after or base_delay * (2 ** attempt) * (0.5 + random.random())
            time.sleep(delay)
```

---

## Checklist de Implementação

### ✅ Obrigatório

- [ ] Respostas de sucesso: `{type, data}`
- [ ] Erros flat: `{type, message, code}`
- [ ] Header `X-Request-ID` em todas as respostas
- [ ] Header `Server-Timing` (não no corpo)
- [ ] Status codes HTTP corretos
- [ ] Paginação com `has_more`

### ✅ Recomendado

- [ ] ETags para cache
- [ ] Headers de rate limit
- [ ] `Retry-After` em erros 429/503
- [ ] Cursor-based como padrão
- [ ] `Deprecation` header (não no corpo)

### ✅ Boas Práticas

- [ ] `code` específico em todos os erros
- [ ] Logs com X-Request-ID
- [ ] Nunca expor stack traces
- [ ] Documentar códigos de erro

---

## Comparativo de Versões

| Aspecto | v1.0 | v2.0 | v3.0 |
|---------|------|------|------|
| Request ID | No corpo ❌ | No header ✅ | No header ✅ |
| Tempo de processamento | N/A | No corpo ❌ | `Server-Timing` ✅ |
| Deprecation | N/A | No corpo ❌ | Header ✅ |
| Estrutura de erro | Wrapper duplo | Wrapper duplo | Flat ✅ |
| Cache HTTP | Quebrado | Quebrado | Funcional ✅ |
| `total` na paginação | Obrigatório ❌ | Opcional ✅ | Opcional ✅ |

---

*Padrão de API REST v3.0 - Cache funcional, erros simples, headers corretos*
