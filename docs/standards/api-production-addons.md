# Complementos para Produção - API REST

Este documento complementa o **Padrão de API REST v3.0** com configurações e funcionalidades adicionais necessárias para ambientes de produção.

---

## 1. Headers de Segurança

### Headers Obrigatórios

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### Implementação FastAPI

```python
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app = FastAPI()

# Hosts permitidos (previne Host header injection)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com", "*.example.com"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    
    # HSTS apenas em produção
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response
```

---

## 2. CORS (Cross-Origin Resource Sharing)

### Configuração Básica

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Origens permitidas (NUNCA use "*" em produção com credentials)
ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://admin.example.com",
]

# Desenvolvimento local
if settings.ENVIRONMENT == "development":
    ALLOWED_ORIGINS.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-Idempotency-Key",
    ],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
        "ETag",
        "Server-Timing",
    ],
    max_age=600,  # Cache preflight por 10 minutos
)
```

### Headers CORS na Resposta

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID, X-RateLimit-Limit, ETag
```

---

## 3. Compressão

### Configuração

```python
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()

# Comprime respostas > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)
```

### Headers

```http
# Request
Accept-Encoding: gzip, br

# Response
Content-Encoding: gzip
Vary: Accept-Encoding
```

### Quando NÃO comprimir

- Respostas já pequenas (< 500 bytes)
- Streams e SSE
- Arquivos já comprimidos (imagens, PDFs)

---

## 4. Sorting e Filtering

### Padrão de Query Params

```
GET /v1/users?sort=created_at:desc,name:asc&filter[status]=active&filter[role]=admin
```

### Sintaxe

| Operação | Sintaxe | Exemplo |
|----------|---------|---------|
| Sort ASC | `sort=field` | `sort=name` |
| Sort DESC | `sort=field:desc` | `sort=created_at:desc` |
| Multi-sort | `sort=field1,field2:desc` | `sort=status,created_at:desc` |
| Filter igual | `filter[field]=value` | `filter[status]=active` |
| Filter IN | `filter[field]=a,b,c` | `filter[role]=admin,user` |
| Filter range | `filter[field][gte]=x` | `filter[age][gte]=18` |

### Operadores de Filtro

| Operador | Descrição | Exemplo |
|----------|-----------|---------|
| `eq` (default) | Igual | `filter[status]=active` |
| `neq` | Diferente | `filter[status][neq]=deleted` |
| `gt` | Maior que | `filter[age][gt]=18` |
| `gte` | Maior ou igual | `filter[age][gte]=18` |
| `lt` | Menor que | `filter[price][lt]=100` |
| `lte` | Menor ou igual | `filter[price][lte]=100` |
| `like` | Contém (texto) | `filter[name][like]=silva` |
| `in` | Lista de valores | `filter[status][in]=active,pending` |
| `null` | É nulo | `filter[deleted_at][null]=true` |

### Implementação

```python
from typing import Optional
from fastapi import Query
from pydantic import BaseModel


class SortParam(BaseModel):
    field: str
    direction: str = "asc"  # asc ou desc


def parse_sort(sort: Optional[str] = Query(None)) -> list[SortParam]:
    """Parse sort=field:desc,field2:asc"""
    if not sort:
        return []
    
    result = []
    for part in sort.split(","):
        if ":" in part:
            field, direction = part.split(":", 1)
        else:
            field, direction = part, "asc"
        
        if direction not in ("asc", "desc"):
            direction = "asc"
        
        result.append(SortParam(field=field, direction=direction))
    
    return result


def parse_filters(request) -> dict:
    """Parse filter[field]=value e filter[field][op]=value"""
    filters = {}
    
    for key, value in request.query_params.items():
        if not key.startswith("filter["):
            continue
        
        # filter[status] ou filter[age][gte]
        parts = key.replace("filter[", "").rstrip("]").split("][")
        
        if len(parts) == 1:
            filters[parts[0]] = {"op": "eq", "value": value}
        else:
            filters[parts[0]] = {"op": parts[1], "value": value}
    
    return filters


# Uso no endpoint
@app.get("/v1/users")
async def list_users(
    request: Request,
    sort: Optional[str] = Query(None, example="created_at:desc"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = None,
):
    sort_params = parse_sort(sort)
    filters = parse_filters(request)
    
    # Aplicar no query do banco...
```

### Resposta com Metadata

```json
{
  "type": "list",
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "..."
  },
  "metadata": {
    "filters_applied": {
      "status": "active",
      "role": "admin"
    },
    "sort_applied": [
      {"field": "created_at", "direction": "desc"}
    ]
  }
}
```

---

## 5. Sparse Fieldsets (Campos Selecionáveis)

### Sintaxe

```
GET /v1/users?fields=id,name,email
GET /v1/users/123?fields=id,name,profile.avatar
```

### Implementação

```python
from typing import Optional


def filter_fields(data: dict, fields: Optional[str]) -> dict:
    """Filtra campos do response baseado no param fields."""
    if not fields:
        return data
    
    allowed = set(fields.split(","))
    
    def filter_dict(d: dict, prefix: str = "") -> dict:
        result = {}
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            # Campo direto
            if full_key in allowed or key in allowed:
                result[key] = value
            # Nested: se pediu profile.avatar, inclui profile
            elif any(f.startswith(f"{full_key}.") for f in allowed):
                if isinstance(value, dict):
                    result[key] = filter_dict(value, full_key)
        
        return result
    
    return filter_dict(data)


@app.get("/v1/users/{user_id}")
async def get_user(user_id: str, fields: Optional[str] = Query(None)):
    user = await find_user(user_id)
    
    filtered = filter_fields(user, fields)
    
    return {"type": "user", "data": filtered}
```

### Exemplo

```
GET /v1/users/123?fields=id,name,email
```

```json
{
  "type": "user",
  "data": {
    "id": "usr_123",
    "name": "João Silva",
    "email": "joao@example.com"
  }
}
```

Campos omitidos: `created_at`, `updated_at`, `role`, etc.

---

## 6. Batch Operations

### Endpoint

```
POST /v1/batch
```

### Request

```json
{
  "operations": [
    {
      "id": "op1",
      "method": "POST",
      "path": "/v1/users",
      "body": {
        "name": "João",
        "email": "joao@example.com"
      }
    },
    {
      "id": "op2",
      "method": "POST",
      "path": "/v1/users",
      "body": {
        "name": "Maria",
        "email": "maria@example.com"
      }
    },
    {
      "id": "op3",
      "method": "DELETE",
      "path": "/v1/users/usr_old123"
    }
  ]
}
```

### Response

```json
{
  "type": "batch_result",
  "data": {
    "total": 3,
    "succeeded": 2,
    "failed": 1,
    "results": [
      {
        "id": "op1",
        "status": 201,
        "body": {
          "type": "user",
          "data": {"id": "usr_new1", "name": "João", "email": "joao@example.com"}
        }
      },
      {
        "id": "op2",
        "status": 409,
        "body": {
          "type": "conflict_error",
          "message": "Email já cadastrado",
          "code": "EMAIL_EXISTS"
        }
      },
      {
        "id": "op3",
        "status": 204,
        "body": null
      }
    ]
  }
}
```

### Implementação

```python
from pydantic import BaseModel


class BatchOperation(BaseModel):
    id: str
    method: str  # GET, POST, PATCH, DELETE
    path: str
    body: Optional[dict] = None
    headers: Optional[dict] = None


class BatchRequest(BaseModel):
    operations: list[BatchOperation]


@app.post("/v1/batch")
async def batch_operations(batch: BatchRequest, request: Request):
    results = []
    succeeded = 0
    failed = 0
    
    for op in batch.operations:
        try:
            # Simula request interno
            result = await execute_internal_request(
                method=op.method,
                path=op.path,
                body=op.body,
                headers=op.headers,
                auth=request.headers.get("Authorization")
            )
            
            results.append({
                "id": op.id,
                "status": result.status_code,
                "body": result.body
            })
            
            if result.status_code < 400:
                succeeded += 1
            else:
                failed += 1
                
        except Exception as e:
            results.append({
                "id": op.id,
                "status": 500,
                "body": {
                    "type": "api_error",
                    "message": "Erro ao processar operação"
                }
            })
            failed += 1
    
    return {
        "type": "batch_result",
        "data": {
            "total": len(batch.operations),
            "succeeded": succeeded,
            "failed": failed,
            "results": results
        }
    }
```

### Limites

| Limite | Valor | Descrição |
|--------|-------|-----------|
| Max operações | 100 | Por request |
| Timeout total | 30s | Para todo o batch |
| Max body size | 1MB | Por operação |

---

## 7. Idempotência

### Conceito

Requisições com a mesma `X-Idempotency-Key` retornam o mesmo resultado, mesmo se executadas múltiplas vezes.

### Fluxo

```
┌─────────────────────────────────────────────────────────────┐
│ Cliente envia POST com X-Idempotency-Key: abc123            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Servidor verifica se abc123 já existe no cache              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│ Não existe:             │     │ Existe:                     │
│ - Processa request      │     │ - Retorna resposta cacheada │
│ - Salva resposta        │     │ - Header: X-Idempotent: true│
│ - Retorna resultado     │     │                             │
└─────────────────────────┘     └─────────────────────────────┘
```

### Implementação com Redis

```python
import redis
import json
import hashlib
from fastapi import Request, Response
from functools import wraps

redis_client = redis.Redis(host='localhost', port=6379, db=0)

IDEMPOTENCY_TTL = 86400  # 24 horas


def idempotent(func):
    """Decorator para endpoints idempotentes."""
    
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        idempotency_key = request.headers.get("X-Idempotency-Key")
        
        if not idempotency_key:
            # Sem chave, executa normalmente
            return await func(request, *args, **kwargs)
        
        # Cria chave única: método + path + idempotency_key + user
        user_id = request.state.user_id or "anonymous"
        cache_key = f"idempotency:{user_id}:{request.method}:{request.url.path}:{idempotency_key}"
        
        # Verifica cache
        cached = redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            response = JSONResponse(
                content=data["body"],
                status_code=data["status_code"],
                headers={"X-Idempotent-Replayed": "true"}
            )
            return response
        
        # Lock para evitar race condition
        lock_key = f"{cache_key}:lock"
        lock = redis_client.set(lock_key, "1", nx=True, ex=30)
        
        if not lock:
            # Outra request está processando
            return JSONResponse(
                status_code=409,
                content={
                    "type": "conflict_error",
                    "message": "Requisição em processamento",
                    "code": "IDEMPOTENCY_CONFLICT"
                }
            )
        
        try:
            # Executa request
            result = await func(request, *args, **kwargs)
            
            # Serializa resposta
            if isinstance(result, Response):
                body = result.body.decode()
                status_code = result.status_code
            else:
                body = json.dumps(result)
                status_code = 200
            
            # Salva no cache
            cache_data = json.dumps({
                "body": json.loads(body) if body else None,
                "status_code": status_code
            })
            redis_client.setex(cache_key, IDEMPOTENCY_TTL, cache_data)
            
            return result
            
        finally:
            # Remove lock
            redis_client.delete(lock_key)
    
    return wrapper


# Uso
@app.post("/v1/payments")
@idempotent
async def create_payment(request: Request, body: PaymentRequest):
    # Mesmo request com mesma idempotency key retorna mesmo resultado
    payment = await process_payment(body)
    return {"type": "payment", "data": payment}
```

### Headers

```http
# Request
X-Idempotency-Key: pay_abc123_retry1

# Response (primeira vez)
HTTP/1.1 201 Created

# Response (replay)
HTTP/1.1 201 Created
X-Idempotent-Replayed: true
```

### Regras

1. Chave deve ser única por operação lógica (ex: UUID do pedido)
2. TTL de 24h é suficiente para maioria dos casos
3. Apenas métodos não-idempotentes por natureza (POST) precisam
4. GET, PUT, DELETE já são idempotentes por definição HTTP

---

## 8. Internacionalização (i18n)

### Header

```http
Accept-Language: pt-BR, pt;q=0.9, en;q=0.8
```

### Implementação

```python
from fastapi import Request
from babel import Locale, negotiate_locale

SUPPORTED_LOCALES = ["pt-BR", "pt", "en", "es"]
DEFAULT_LOCALE = "en"

# Mensagens de erro
ERROR_MESSAGES = {
    "USER_NOT_FOUND": {
        "en": "User not found",
        "pt": "Usuário não encontrado",
        "pt-BR": "Usuário não encontrado",
        "es": "Usuario no encontrado"
    },
    "EMAIL_EXISTS": {
        "en": "Email already registered",
        "pt": "Email já cadastrado",
        "pt-BR": "Email já cadastrado",
        "es": "Correo electrónico ya registrado"
    },
    "VALIDATION_FAILED": {
        "en": "Validation errors found",
        "pt": "Erros de validação encontrados",
        "pt-BR": "Erros de validação encontrados",
        "es": "Errores de validación encontrados"
    },
    # ...
}


def get_locale(request: Request) -> str:
    """Extrai locale do header Accept-Language."""
    accept = request.headers.get("Accept-Language", DEFAULT_LOCALE)
    
    # Parse Accept-Language
    locales = []
    for part in accept.split(","):
        part = part.strip()
        if ";q=" in part:
            locale, q = part.split(";q=")
            locales.append((locale.strip(), float(q)))
        else:
            locales.append((part, 1.0))
    
    # Ordena por qualidade
    locales.sort(key=lambda x: x[1], reverse=True)
    
    # Encontra primeiro suportado
    for locale, _ in locales:
        if locale in SUPPORTED_LOCALES:
            return locale
        # Tenta sem região (pt-BR -> pt)
        base = locale.split("-")[0]
        if base in SUPPORTED_LOCALES:
            return base
    
    return DEFAULT_LOCALE


def get_error_message(code: str, locale: str) -> str:
    """Retorna mensagem de erro traduzida."""
    messages = ERROR_MESSAGES.get(code, {})
    return messages.get(locale) or messages.get("en") or code


@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    request.state.locale = get_locale(request)
    response = await call_next(request)
    response.headers["Content-Language"] = request.state.locale
    return response


# Helper para criar erro traduzido
def localized_error(request: Request, error_type: str, code: str, **kwargs):
    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    message = get_error_message(code, locale)
    
    return {
        "type": error_type,
        "message": message,
        "code": code,
        **kwargs
    }


# Uso
@app.get("/v1/users/{user_id}")
async def get_user(user_id: str, request: Request):
    user = await find_user(user_id)
    if not user:
        raise HTTPException(
            404,
            localized_error(request, "not_found_error", "USER_NOT_FOUND")
        )
    return {"type": "user", "data": user}
```

### Response

```http
# Request
Accept-Language: pt-BR

# Response
Content-Language: pt-BR

{
  "type": "not_found_error",
  "message": "Usuário não encontrado",
  "code": "USER_NOT_FOUND"
}
```

---

## 9. Health Check

### Endpoints

| Endpoint | Propósito | Quem usa |
|----------|-----------|----------|
| `GET /health` | Aplicação está viva | Load balancer |
| `GET /ready` | Pronta para receber tráfego | Kubernetes |
| `GET /health/detailed` | Status de dependências | Monitoramento |

### Implementação

```python
import asyncio
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


async def check_database() -> tuple[HealthStatus, dict]:
    """Verifica conexão com banco."""
    try:
        start = datetime.now()
        await db.execute("SELECT 1")
        latency = (datetime.now() - start).total_seconds() * 1000
        
        status = HealthStatus.HEALTHY if latency < 100 else HealthStatus.DEGRADED
        return status, {"latency_ms": round(latency, 2)}
    except Exception as e:
        return HealthStatus.UNHEALTHY, {"error": str(e)}


async def check_redis() -> tuple[HealthStatus, dict]:
    """Verifica conexão com Redis."""
    try:
        start = datetime.now()
        await redis_client.ping()
        latency = (datetime.now() - start).total_seconds() * 1000
        
        status = HealthStatus.HEALTHY if latency < 50 else HealthStatus.DEGRADED
        return status, {"latency_ms": round(latency, 2)}
    except Exception as e:
        return HealthStatus.UNHEALTHY, {"error": str(e)}


async def check_external_api() -> tuple[HealthStatus, dict]:
    """Verifica API externa (ex: payment gateway)."""
    try:
        start = datetime.now()
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.payment.com/health", timeout=5)
        latency = (datetime.now() - start).total_seconds() * 1000
        
        if resp.status_code == 200:
            return HealthStatus.HEALTHY, {"latency_ms": round(latency, 2)}
        return HealthStatus.DEGRADED, {"status_code": resp.status_code}
    except Exception as e:
        return HealthStatus.UNHEALTHY, {"error": str(e)}


# Liveness: aplicação está rodando?
@app.get("/health")
async def health():
    return {"status": "healthy"}


# Readiness: pronta para tráfego?
@app.get("/ready")
async def ready():
    db_status, _ = await check_database()
    
    if db_status == HealthStatus.UNHEALTHY:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": "database unavailable"}
        )
    
    return {"status": "healthy"}


# Detailed: status de todas as dependências
@app.get("/health/detailed")
async def health_detailed():
    checks = await asyncio.gather(
        check_database(),
        check_redis(),
        check_external_api(),
        return_exceptions=True
    )
    
    dependencies = {
        "database": {"status": checks[0][0], "details": checks[0][1]},
        "redis": {"status": checks[1][0], "details": checks[1][1]},
        "payment_api": {"status": checks[2][0], "details": checks[2][1]},
    }
    
    # Status geral
    statuses = [d["status"] for d in dependencies.values()]
    if HealthStatus.UNHEALTHY in statuses:
        overall = HealthStatus.UNHEALTHY
        http_status = 503
    elif HealthStatus.DEGRADED in statuses:
        overall = HealthStatus.DEGRADED
        http_status = 200
    else:
        overall = HealthStatus.HEALTHY
        http_status = 200
    
    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.2.3",
            "dependencies": dependencies
        }
    )
```

### Responses

**GET /health**
```json
{"status": "healthy"}
```

**GET /health/detailed**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "1.2.3",
  "dependencies": {
    "database": {
      "status": "healthy",
      "details": {"latency_ms": 5.2}
    },
    "redis": {
      "status": "healthy",
      "details": {"latency_ms": 1.1}
    },
    "payment_api": {
      "status": "degraded",
      "details": {"latency_ms": 850.5}
    }
  }
}
```

---

## 10. OpenAPI/Swagger

### Configuração FastAPI

```python
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Minha API",
    version="1.0.0",
    description="API de exemplo seguindo padrão REST v3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Adiciona schemas de erro padrão
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "required": ["type", "message"],
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "invalid_request_error",
                    "authentication_error",
                    "permission_error",
                    "not_found_error",
                    "conflict_error",
                    "validation_error",
                    "rate_limit_error",
                    "api_error"
                ]
            },
            "message": {"type": "string"},
            "code": {"type": "string"},
            "param": {"type": "string"},
            "details": {"type": "object"}
        }
    }
    
    # Adiciona respostas comuns
    openapi_schema["components"]["responses"] = {
        "NotFound": {
            "description": "Recurso não encontrado",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            }
        },
        "Unauthorized": {
            "description": "Não autenticado",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            }
        },
        "RateLimited": {
            "description": "Rate limit excedido",
            "headers": {
                "Retry-After": {
                    "schema": {"type": "integer"},
                    "description": "Segundos para retry"
                }
            },
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
```

### Documentando Endpoints

```python
from fastapi import Path, Query
from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """Resposta de usuário."""
    type: str = Field(example="user")
    data: dict = Field(example={
        "id": "usr_123",
        "name": "João Silva",
        "email": "joao@example.com"
    })


@app.get(
    "/v1/users/{user_id}",
    response_model=UserResponse,
    responses={
        404: {"description": "Usuário não encontrado"},
        401: {"description": "Não autenticado"}
    },
    tags=["Users"],
    summary="Buscar usuário por ID",
    description="Retorna os dados de um usuário específico."
)
async def get_user(
    user_id: str = Path(..., description="ID único do usuário", example="usr_123"),
    fields: str = Query(None, description="Campos a retornar", example="id,name,email")
):
    """
    Busca um usuário pelo ID.
    
    - **user_id**: ID único do usuário (formato: usr_xxx)
    - **fields**: Lista de campos separados por vírgula (opcional)
    """
    pass
```

---

## 11. Rate Limiting Detalhado

### Estratégias

| Estratégia | Uso | Exemplo |
|------------|-----|---------|
| Fixed Window | Simples | 100 req/minuto |
| Sliding Window | Mais justo | 100 req nos últimos 60s |
| Token Bucket | Bursts | 100 tokens, refill 10/s |

### Implementação com Redis (Sliding Window)

```python
import time
import redis

redis_client = redis.Redis()


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int
) -> tuple[bool, dict]:
    """
    Sliding window rate limiter.
    Retorna (allowed, info).
    """
    now = time.time()
    window_start = now - window_seconds
    
    pipe = redis_client.pipeline()
    
    # Remove requests antigos
    pipe.zremrangebyscore(key, 0, window_start)
    
    # Conta requests na janela
    pipe.zcard(key)
    
    # Adiciona request atual
    pipe.zadd(key, {str(now): now})
    
    # Define TTL
    pipe.expire(key, window_seconds)
    
    results = pipe.execute()
    request_count = results[1]
    
    remaining = max(0, limit - request_count - 1)
    reset_at = int(now + window_seconds)
    
    info = {
        "limit": limit,
        "remaining": remaining,
        "reset": reset_at
    }
    
    if request_count >= limit:
        info["retry_after"] = window_seconds
        return False, info
    
    return True, info


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Identifica cliente (user_id ou IP)
    user_id = getattr(request.state, "user_id", None)
    client_key = user_id or request.client.host
    
    # Diferentes limites por tier
    if user_id:
        limit, window = 1000, 60  # Autenticado: 1000/min
    else:
        limit, window = 100, 60   # Anônimo: 100/min
    
    rate_key = f"ratelimit:{client_key}:{request.url.path}"
    
    allowed, info = await check_rate_limit(rate_key, limit, window)
    
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["retry_after"])
            },
            content={
                "type": "rate_limit_error",
                "message": f"Limite excedido. Tente em {info['retry_after']}s.",
                "code": "RATE_LIMIT_EXCEEDED",
                "details": info
            }
        )
    
    response = await call_next(request)
    
    # Adiciona headers de rate limit
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset"])
    
    return response
```

---

## Checklist de Produção

### ✅ Segurança

- [ ] Headers de segurança configurados
- [ ] CORS restrito a origens conhecidas
- [ ] Rate limiting implementado
- [ ] Validação de input em todos endpoints
- [ ] Logs sem dados sensíveis

### ✅ Performance

- [ ] Compressão habilitada
- [ ] Cache com ETags
- [ ] Paginação cursor-based
- [ ] Connection pooling no banco
- [ ] Timeouts configurados

### ✅ Operação

- [ ] Health checks funcionando
- [ ] Logs estruturados (JSON)
- [ ] Métricas expostas (Prometheus)
- [ ] Tracing distribuído (X-Request-ID)
- [ ] Alertas configurados

### ✅ Developer Experience

- [ ] OpenAPI/Swagger atualizado
- [ ] Erros traduzidos (i18n)
- [ ] Idempotência em POST/PATCH
- [ ] Documentação de códigos de erro
- [ ] SDK ou exemplos de uso

---

*Complementos para Produção - API REST v1.0*
