# Observabilidade e Práticas de Produção

Guia para padrões de observabilidade e práticas de produção no HomeFlix.

---

## Correlation ID

### O Que É

Um identificador único que acompanha uma requisição por todas as camadas da aplicação, facilitando debugging e rastreamento em logs.

```
Request → Middleware → Use Case → Repository → Response
   │          │            │           │           │
   └──────────┴────────────┴───────────┴───────────┘
                    correlation_id: "req_abc123"
```

### Implementação

#### Middleware

```python
# src/presentation/api/middleware/correlation_id.py
import uuid
from contextvars import ContextVar
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable para acesso global
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    return correlation_id_ctx.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that manages correlation ID for request tracing."""
    
    async def dispatch(self, request: Request, call_next):
        # Usa header se existir, senão gera novo
        correlation_id = request.headers.get(
            CORRELATION_ID_HEADER,
            f"req_{uuid.uuid4().hex[:12]}"
        )
        
        # Seta no contexto
        correlation_id_ctx.set(correlation_id)
        
        # Processa request
        response = await call_next(request)
        
        # Inclui no response
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        
        return response
```

#### Integração com Logging

```python
# src/config/logging.py (atualização)
from src.presentation.api.middleware.correlation_id import get_correlation_id

def add_correlation_id(logger, method_name, event_dict):
    """Processor que adiciona correlation_id em todo log."""
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict

# Adicionar ao pipeline de processors
structlog.configure(
    processors=[
        add_correlation_id,  # 👈 Adicionar antes do formatter
        structlog.processors.TimeStamper(fmt="iso"),
        # ... outros processors
    ],
)
```

#### Uso

```python
# Em qualquer lugar da aplicação
from src.config.logging import get_logger

logger = get_logger()
logger.info("Processing movie", movie_id="mov_abc123")
# Output: {"correlation_id": "req_xyz789", "event": "Processing movie", "movie_id": "mov_abc123"}
```

#### Propagação para APIs Externas

```python
# No BaseExternalClient
async def _make_request(self, method: str, endpoint: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["X-Correlation-ID"] = get_correlation_id()
    
    # ... resto da implementação
```

### Formato do Correlation ID

```
req_{12 caracteres hex}
Exemplo: req_a1b2c3d4e5f6
```

---

## Health Checks

### O Que É

Endpoints que indicam se a aplicação está funcionando corretamente. Útil para:
- Load balancers
- Container orchestration (Kubernetes)
- Monitoramento

### Tipos

| Tipo | Propósito | O Que Verifica |
|------|-----------|----------------|
| **Liveness** | "A aplicação está rodando?" | Processo está vivo |
| **Readiness** | "A aplicação pode receber tráfego?" | Dependências OK (DB, etc.) |

### Implementação

```python
# src/presentation/api/v1/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.config.container import get_container

router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness():
    """Liveness probe - aplicação está rodando?
    
    Sempre retorna 200 se o processo está vivo.
    Usado por: Kubernetes livenessProbe
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(
    session: AsyncSession = Depends(get_container().db_session)
):
    """Readiness probe - aplicação pode receber tráfego?
    
    Verifica se dependências críticas estão OK.
    Usado por: Kubernetes readinessProbe, Load Balancers
    """
    checks = {
        "database": await _check_database(session),
    }
    
    all_healthy = all(check["healthy"] for check in checks.values())
    
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
    }


async def _check_database(session: AsyncSession) -> dict:
    """Verifica conexão com o banco."""
    try:
        await session.execute(text("SELECT 1"))
        return {"healthy": True}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


@router.get("/health")
async def health_summary(
    session: AsyncSession = Depends(get_container().db_session)
):
    """Health check completo com detalhes.
    
    Usado por: Monitoramento, dashboards
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    db_check = await _check_database(session)
    
    return {
        "status": "healthy" if db_check["healthy"] else "unhealthy",
        "version": settings.app_version,
        "environment": settings.app_env,
        "checks": {
            "database": db_check,
        },
    }
```

### Registro das Rotas

```python
# src/presentation/api/v1/__init__.py
from src.presentation.api.v1.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
```

### Respostas

#### Liveness (sempre 200 se processo vivo)
```json
{
  "status": "alive"
}
```

#### Readiness (200 se pronto, 503 se não)
```json
{
  "status": "ready",
  "checks": {
    "database": {"healthy": true}
  }
}
```

#### Health Completo
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "database": {"healthy": true}
  }
}
```

---

## Soft Delete

### O Que É

Em vez de deletar registros fisicamente (`DELETE FROM`), marcar com timestamp de exclusão:

```sql
-- Hard Delete (tradicional)
DELETE FROM movies WHERE id = 'mov_abc123';

-- Soft Delete
UPDATE movies SET deleted_at = NOW() WHERE id = 'mov_abc123';
```

### Por Quê Usar

| Benefício | Exemplo |
|-----------|---------|
| **Recuperação** | Usuário deletou sem querer, pode restaurar |
| **Auditoria** | Histórico de quando foi deletado |
| **Integridade** | Foreign keys não quebram |
| **Debug** | Ver dados que existiam antes |

### Implementação no Domain

```python
# src/domain/shared/models/entity.py
from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import Field

from src.domain.shared.models.domain_model import DomainModel

IdType = TypeVar("IdType")


class DomainEntity(DomainModel, Generic[IdType]):
    """Base class for all domain entities with soft delete support."""
    
    id: IdType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = Field(default=None)
    
    def mark_as_deleted(self) -> None:
        """Soft delete this entity."""
        self.deleted_at = datetime.now(UTC)
    
    def restore(self) -> None:
        """Restore a soft-deleted entity."""
        self.deleted_at = None
    
    @property
    def is_deleted(self) -> bool:
        """Check if entity is soft-deleted."""
        return self.deleted_at is not None
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC)
```

### Implementação no Repository

```python
# src/infrastructure/persistence/repositories/movie_repository.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository
from src.infrastructure.persistence.models import MovieModel


class SQLAlchemyMovieRepository(MovieRepository):
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def find_all(
        self,
        include_deleted: bool = False,
    ) -> list[Movie]:
        """Find all movies, excluding soft-deleted by default."""
        query = select(MovieModel)
        
        if not include_deleted:
            query = query.where(MovieModel.deleted_at.is_(None))
        
        result = await self._session.execute(query)
        return [row.to_entity() for row in result.scalars()]
    
    async def find_by_id(
        self,
        movie_id: MovieId,
        include_deleted: bool = False,
    ) -> Movie | None:
        """Find movie by ID, excluding soft-deleted by default."""
        query = select(MovieModel).where(MovieModel.id == movie_id.value)
        
        if not include_deleted:
            query = query.where(MovieModel.deleted_at.is_(None))
        
        result = await self._session.execute(query)
        row = result.scalar_one_or_none()
        return row.to_entity() if row else None
    
    async def delete(self, movie: Movie) -> None:
        """Soft delete a movie."""
        movie.mark_as_deleted()
        model = await self._session.get(MovieModel, movie.id.value)
        if model:
            model.deleted_at = movie.deleted_at
            await self._session.commit()
    
    async def hard_delete(self, movie: Movie) -> None:
        """Permanently delete a movie. Use with caution!"""
        model = await self._session.get(MovieModel, movie.id.value)
        if model:
            await self._session.delete(model)
            await self._session.commit()
    
    async def restore(self, movie_id: MovieId) -> Movie | None:
        """Restore a soft-deleted movie."""
        movie = await self.find_by_id(movie_id, include_deleted=True)
        if movie and movie.is_deleted:
            movie.restore()
            model = await self._session.get(MovieModel, movie_id.value)
            if model:
                model.deleted_at = None
                await self._session.commit()
            return movie
        return None
```

### Interface do Repository

```python
# src/domain/media/repositories/movie_repository.py
from abc import ABC, abstractmethod

from src.domain.media.entities import Movie
from src.domain.media.value_objects import MovieId


class MovieRepository(ABC):
    @abstractmethod
    async def find_all(self, include_deleted: bool = False) -> list[Movie]:
        """Find all movies."""
        ...
    
    @abstractmethod
    async def find_by_id(
        self,
        movie_id: MovieId,
        include_deleted: bool = False,
    ) -> Movie | None:
        """Find movie by ID."""
        ...
    
    @abstractmethod
    async def save(self, movie: Movie) -> None:
        """Save a movie (insert or update)."""
        ...
    
    @abstractmethod
    async def delete(self, movie: Movie) -> None:
        """Soft delete a movie."""
        ...
    
    @abstractmethod
    async def restore(self, movie_id: MovieId) -> Movie | None:
        """Restore a soft-deleted movie."""
        ...
```

### Model de Persistência

```python
# src/infrastructure/persistence/models/movie.py
from datetime import datetime

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class MovieModel(Base):
    __tablename__ = "movies"
    
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    year: Mapped[int]
    # ... outros campos
    
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

### Migration

```python
# alembic/versions/xxx_add_soft_delete.py
def upgrade():
    op.add_column('movies', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('series', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    # ... outras tabelas

def downgrade():
    op.drop_column('movies', 'deleted_at')
    op.drop_column('series', 'deleted_at')
```

---

## CORS (Cross-Origin Resource Sharing)

### O Que É

Mecanismo de segurança que controla quais origens (domínios) podem acessar a API.

Necessário porque o frontend React roda em porta diferente do backend.

### Implementação

```python
# src/presentation/api/middleware/cors.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware."""
    settings = get_settings()
    
    # Em desenvolvimento, permitir localhost
    # Em produção, restringir às origens conhecidas
    if settings.app_env == "development":
        origins = [
            "http://localhost:3000",      # React dev server
            "http://localhost:5173",      # Vite dev server
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    else:
        origins = settings.cors_origins  # Lista configurável
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
```

### Settings

```python
# src/config/settings.py (adicionar)
class Settings(BaseSettings):
    # ... campos existentes
    
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )
```

### Uso no main.py

```python
# src/main.py
from src.presentation.api.middleware.cors import setup_cors
from src.presentation.api.middleware.correlation_id import CorrelationIdMiddleware

app = FastAPI(...)

# Ordem importa! CORS deve vir primeiro
setup_cors(app)
app.add_middleware(CorrelationIdMiddleware)
```

---

## Graceful Shutdown

### O Que É

Finalizar a aplicação de forma limpa, completando requests em andamento antes de encerrar.

### Implementação

O FastAPI lifespan já suporta isso:

```python
# src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.config.logging import get_logger, setup_logging
from src.config.container import get_container

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with graceful shutdown."""
    # === Startup ===
    setup_logging()
    logger.info("Application starting up")
    
    container = get_container()
    await container.init_resources()
    
    logger.info("Application ready to receive requests")
    
    yield  # Aplicação rodando
    
    # === Shutdown ===
    logger.info("Application shutting down")
    
    # Fechar conexões de banco
    await container.shutdown_resources()
    
    # Fechar clients HTTP
    # await tmdb_client.close()
    # await omdb_client.close()
    
    logger.info("Application shutdown complete")


app = FastAPI(
    title="HomeFlix API",
    lifespan=lifespan,
)
```

### Signal Handling

Para Docker/Kubernetes, o FastAPI já trata SIGTERM corretamente. Para desenvolvimento:

```python
# Se precisar de controle adicional
import signal
import asyncio

def handle_shutdown(signum, frame):
    logger.info("Received shutdown signal", signal=signum)
    # O FastAPI vai tratar o resto via lifespan

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```

---

## Checklist de Produção

### Observabilidade
- [ ] Correlation ID em todas as requisições
- [ ] Correlation ID propagado para logs
- [ ] Correlation ID propagado para APIs externas
- [ ] Health check `/health/live`
- [ ] Health check `/health/ready`

### Dados
- [ ] Soft delete em todas as entidades principais
- [ ] `include_deleted` flag nos repositories
- [ ] Migration para `deleted_at`

### Segurança
- [ ] CORS configurado
- [ ] Origens restritas em produção

### Resiliência
- [ ] Graceful shutdown configurado
- [ ] Conexões fechadas no shutdown
- [ ] Timeout em todas as requisições HTTP

---

## Resumo

| Padrão | Complexidade | Linhas de Código | Benefício |
|--------|--------------|------------------|-----------|
| Correlation ID | Baixa | ~50 | Debugging |
| Health Checks | Baixa | ~40 | Monitoramento |
| Soft Delete | Baixa | ~30 | Recuperação de dados |
| CORS | Baixa | ~20 | Frontend funciona |
| Graceful Shutdown | Baixa | ~20 | Estabilidade |

**Total: ~160 linhas de código** para práticas de produção.
