# ADR-002: Prefixed External IDs para Recursos da API

**Status:** Aceito  
**Data:** 2025-01-28  
**Deciders:** Lucas  
**Technical Story:** Definir estratégia de identificadores para recursos expostos via API

---

## Contexto

Ao projetar APIs REST, precisamos decidir como identificar recursos. As opções comuns são:

1. **Auto-increment IDs** (`/movies/1`, `/movies/2`)
2. **Database IDs** (`/movies/507f1f77bcf86cd799439011` para MongoDB)
3. **UUIDs** (`/movies/550e8400-e29b-41d4-a716-446655440000`)
4. **Prefixed IDs** (`/movies/mov_2xK9mPqR7nL4`)

Cada abordagem tem trade-offs de segurança, usabilidade e flexibilidade.

## Decisão

**Adotamos Prefixed External IDs no formato `{prefix}_{random}`.**

### Formato

```
{tipo}_{base62_random_12chars}

Exemplos:
- mov_2xK9mPqR7nL4  (Movie)
- ser_8jH3kLm9pQ2w  (Series)
- epi_4nM7rT2xK9pL  (Episode)
- ssn_7mK2pQ9nL4xR  (Season)
- prg_9qW2nL4mK7rT  (WatchProgress)
- wls_3kM9pQ7nL2xR  (Watchlist item)
- fav_6nL4mK9pQ2wR  (Favorite)
- lst_1pQ7nL2xR9mK  (CustomList)
```

### Estrutura do ID

| Componente | Tamanho | Descrição |
|------------|---------|-----------|
| Prefix | 3 chars | Tipo do recurso (lowercase) |
| Separator | 1 char | Underscore `_` |
| Random | 12 chars | Base62 (a-z, A-Z, 0-9) |
| **Total** | **16 chars** | Fixo e previsível |

### Mapeamento de Prefixos

```python
PREFIX_MAP = {
    "mov": "Movie",
    "ser": "Series", 
    "ssn": "Season",
    "epi": "Episode",
    "prg": "WatchProgress",
    "wls": "WatchlistItem",
    "fav": "Favorite",
    "lst": "CustomList",
    "gnr": "Genre",
    "scn": "LibraryScan",
}
```

## Consequências

### Positivas

1. **Segurança**
   - Não enumerável (atacante não pode iterar `/movies/1`, `/movies/2`)
   - Não revela tecnologia do banco
   - Entropia suficiente (62^12 ≈ 3.2 × 10^21 combinações)

2. **Developer Experience**
   - Debugging fácil: "mov_xxx é um filme, prg_xxx é progresso"
   - Logs mais legíveis
   - Erros mais claros: "Invalid movie ID" vs "Invalid ID"

3. **Flexibilidade**
   - ID gerado no domínio, antes de persistir
   - Pode migrar de banco sem quebrar APIs
   - Facilita merge de dados de diferentes fontes

4. **Consistência**
   - Tamanho fixo (16 chars) - bom para UI
   - Sempre lowercase + underscore - fácil de copiar/colar

### Negativas

1. **Storage adicional**
   - Precisa armazenar `external_id` além do `internal_id`
   - +16 bytes por registro (negligível)

2. **Lookup extra**
   - Query precisa buscar por `external_id`
   - Mitigado com índice único

3. **Complexidade inicial**
   - Mais código que usar ID do banco diretamente

## Implementação

### Value Object

```python
# core/domain/shared/value_objects/external_id.py

import secrets
import string
from typing import ClassVar
from pydantic import model_validator

from core.domain.shared.models import StringValueObject

# Alphabet for Base62 encoding
BASE62_ALPHABET = string.ascii_letters + string.digits  # a-zA-Z0-9


class ExternalId(StringValueObject):
    """
    External ID for API exposure.
    
    Format: {prefix}_{base62_random_12chars}
    Example: mov_2xK9mPqR7nL4
    """
    
    VALID_PREFIXES: ClassVar[set[str]] = {
        "mov", "ser", "ssn", "epi", "prg", 
        "wls", "fav", "lst", "gnr", "scn",
    }
    
    @model_validator(mode="before")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("External ID must be a string")
        
        value = value.strip().lower()
        
        if "_" not in value:
            raise ValueError("External ID must contain underscore separator")
        
        prefix, random_part = value.split("_", 1)
        
        if prefix not in cls.VALID_PREFIXES:
            raise ValueError(f"Invalid prefix: {prefix}")
        
        if len(random_part) != 12:
            raise ValueError("Random part must be 12 characters")
        
        if not all(c in BASE62_ALPHABET for c in random_part):
            raise ValueError("Random part must be Base62")
        
        return value
    
    @classmethod
    def generate(cls, prefix: str) -> "ExternalId":
        """Generate a new external ID with given prefix."""
        if prefix not in cls.VALID_PREFIXES:
            raise ValueError(f"Invalid prefix: {prefix}")
        
        random_part = ''.join(
            secrets.choice(BASE62_ALPHABET) for _ in range(12)
        )
        return cls(f"{prefix}_{random_part}")
    
    @property
    def prefix(self) -> str:
        """Extract prefix from ID."""
        return self.value.split("_")[0]
    
    @property
    def random_part(self) -> str:
        """Extract random part from ID."""
        return self.value.split("_")[1]


# Typed aliases for specific resources
class MovieId(ExternalId):
    """External ID for Movies."""
    
    @model_validator(mode="after")
    def validate_movie_prefix(self) -> "MovieId":
        if self.prefix != "mov":
            raise ValueError("MovieId must have 'mov' prefix")
        return self
    
    @classmethod
    def generate(cls) -> "MovieId":
        return cls(ExternalId.generate("mov").value)


class SeriesId(ExternalId):
    """External ID for Series."""
    
    @model_validator(mode="after")
    def validate_series_prefix(self) -> "SeriesId":
        if self.prefix != "ser":
            raise ValueError("SeriesId must have 'ser' prefix")
        return self
    
    @classmethod
    def generate(cls) -> "SeriesId":
        return cls(ExternalId.generate("ser").value)


# ... similar for EpisodeId, SeasonId, etc.
```

### Uso na Entity

```python
class Movie(DomainEntity):
    """Movie entity with external ID."""
    
    id: MovieId  # External ID (mov_xxx)
    title: str
    year: int
    
    # internal_id é gerenciado pela camada de infraestrutura
```

### Persistência (Infrastructure)

```python
# infrastructure/persistence/models.py

class MovieModel(Base):
    """SQLAlchemy model for Movie."""
    
    __tablename__ = "movies"
    
    # Internal ID (database)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # External ID (API)
    external_id: Mapped[str] = mapped_column(
        String(16), 
        unique=True, 
        index=True,
        nullable=False
    )
    
    title: Mapped[str]
    year: Mapped[int]
```

### Repository

```python
class MovieRepository:
    async def find_by_id(self, movie_id: MovieId) -> Movie | None:
        """Find movie by external ID."""
        model = await self.session.execute(
            select(MovieModel).where(
                MovieModel.external_id == movie_id.value
            )
        )
        return self._to_domain(model.scalar_one_or_none())
```

## Alternativas Consideradas

### 1. Auto-increment IDs

```
GET /movies/1
GET /movies/2
```

**Rejeitado:**
- Enumerável (ataque de scraping)
- Revela quantidade de registros
- Conflitos em merge de dados

### 2. UUIDs Puros

```
GET /movies/550e8400-e29b-41d4-a716-446655440000
```

**Rejeitado:**
- Muito longo (36 chars)
- Não indica tipo do recurso
- Difícil de copiar/comunicar verbalmente

### 3. UUID v7 (Time-ordered)

```
GET /movies/018e4a5c-1b2d-7000-8000-000000000001
```

**Considerado, mas rejeitado:**
- Ainda longo
- Não indica tipo
- Time-ordering não é necessário para nosso caso

### 4. ULID

```
GET /movies/01ARZ3NDEKTSV4RRFFQ69G5FAV
```

**Considerado, mas rejeitado:**
- Não indica tipo do recurso
- Case-sensitive pode causar confusão

### 5. Hashids

```
GET /movies/jR (encode de integer)
```

**Rejeitado:**
- Reversível (segurança por obscuridade)
- Tamanho variável
- Não indica tipo

## Referências

- [Stripe API Design](https://stripe.com/docs/api) - Usa `cus_`, `sub_`, `pi_`
- [Anthropic API](https://docs.anthropic.com/en/api/) - Usa `msg_`, `cpl_`
- [Linear API](https://developers.linear.app/) - Usa prefixed IDs
- [Segment's KSUID](https://github.com/segmentio/ksuid)

---

## Checklist de Implementação

- [ ] Criar `ExternalId` value object base
- [ ] Criar typed IDs: `MovieId`, `SeriesId`, `EpisodeId`, etc.
- [ ] Adicionar `external_id` column nos models SQLAlchemy
- [ ] Criar índice único em `external_id`
- [ ] Atualizar repositories para buscar por external ID
- [ ] Validar prefixo nos endpoints (mov_xxx só em /movies)
- [ ] Documentar formato no OpenAPI
