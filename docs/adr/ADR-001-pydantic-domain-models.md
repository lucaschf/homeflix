# ADR-001: Uso de Pydantic para Modelos de Domínio

**Status:** Aceito  
**Data:** 2025-01-28  
**Deciders:** Lucas  
**Technical Story:** Definir abordagem de validação para domain models

---

## Contexto

No desenvolvimento do HomeFlix seguindo Clean Architecture, precisamos definir como implementar validação e estrutura dos modelos de domínio (Entities, Value Objects, Aggregates).

Existem duas abordagens principais na comunidade:

### Abordagem Purista
- Domain models como dataclasses puras ou POPOs
- Validação em serviços/factories separados
- Argumento: "O domínio não deve depender de frameworks"

### Abordagem Pragmática
- Domain models usando Pydantic encapsulado
- Validação declarativa nos próprios models
- Argumento: "Pydantic é ferramenta de validação, não infraestrutura"

## Decisão

**Adotamos a abordagem pragmática com Pydantic encapsulado.**

Implementamos uma hierarquia de classes base que:

1. **Encapsula Pydantic** - O domínio não expõe `pydantic.ValidationError` diretamente
2. **Abstrai erros** - Usa `DomainValidationError` customizado
3. **Força invariantes** - Configurações como `frozen=True`, `extra='forbid'`
4. **Permite substituição futura** - Se necessário trocar Pydantic, apenas as classes base mudam

### Hierarquia de Classes

```
DomainModel (BaseModel encapsulado)
├── ValueObject (frozen=True) - base abstrata, não instanciar diretamente
│   ├── CompoundValueObject (múltiplos campos, with_updates)
│   ├── StringValueObject (RootModel[str])
│   ├── IntValueObject (RootModel[int])
│   └── ... outros tipos primitivos
├── DomainEntity (com id, created_at, updated_at, with_updates)
└── AggregateRoot (DomainEntity + domain events)

SupportsUpdates (Protocol) - type checking para objetos com with_updates()
```

**Notas sobre a hierarquia:**

- **ValueObject**: Classe base abstrata para todos os Value Objects. Não deve ser instanciada diretamente.
- **CompoundValueObject**: Para VOs com múltiplos campos (ex: Address, DateRange). Possui `with_updates()`.
- **StringValueObject, IntValueObject, etc.**: Para VOs que encapsulam um único valor primitivo. Sem `with_updates()` - crie uma nova instância.
- **SupportsUpdates**: Protocol que documenta a interface `with_updates()`, implementada por `CompoundValueObject` e `DomainEntity`.

### Configuração Padrão

```python
model_config = ConfigDict(
    validate_assignment=True,  # Valida em atribuição
    extra='forbid',            # Não aceita campos extras
    frozen=True,               # Imutável (para Value Objects)
)
```

## Consequências

### Positivas

- **Validação declarativa**: Regras claras nos próprios models
- **Type safety**: Integração nativa com type hints
- **Produtividade**: Menos boilerplate de validação
- **Serialização**: `model_dump()` e `model_validate()` prontos
- **Ecossistema**: FastAPI, SQLModel, etc. integram naturalmente

### Negativas

- **Dependência externa**: Pydantic vira dependência do domínio
- **Curva de aprendizado**: Precisa conhecer Pydantic v2
- **Overhead**: Validação tem custo (negligível para nosso caso)

### Riscos Mitigados

| Risco | Mitigação |
|-------|-----------|
| Acoplamento forte ao Pydantic | Classes base encapsulam; troca afeta só `core/domain/shared/models/` |
| Exposição de erros internos | `DomainValidationError` abstrai `pydantic.ValidationError` |
| Configuração inconsistente | Metaclass impede alteração de `model_config` |

## Alternativas Consideradas

### 1. Dataclasses Puras + Validação Externa

```python
@dataclass
class Movie:
    title: str
    year: int

class MovieFactory:
    def create(self, data: dict) -> Movie:
        # validação manual
        ...
```

**Rejeitado:** Muito boilerplate, validação espalhada, sem type coercion.

### 2. attrs + cattrs

```python
@attrs.define
class Movie:
    title: str = attrs.field(validator=attrs.validators.instance_of(str))
```

**Rejeitado:** Menos popular, ecossistema menor, sintaxe mais verbosa.

### 3. Pydantic Direto (sem encapsulamento)

```python
class Movie(BaseModel):
    title: str
```

**Rejeitado:** Expõe `ValidationError` do Pydantic, sem garantias de configuração.

## Referências

- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [Cosmic Python - Domain Modeling](https://www.cosmicpython.com/)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

## Notas de Implementação

### Criando um Value Object

```python
from core.domain.shared.models import StringValueObject
from pydantic import model_validator

class MovieTitle(StringValueObject):
    """Título de filme com validação."""
    
    @model_validator(mode="before")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Title cannot be empty")
        if len(value) > 500:
            raise ValueError("Title too long")
        return value.strip()
```

### Criando uma Entity

```python
from core.domain.shared.models import DomainEntity
from core.domain.media.value_objects import MovieTitle, MediaId

class Movie(DomainEntity):
    """Entidade de Filme."""
    
    id: MediaId
    title: MovieTitle
    year: int
    duration_seconds: int
```

### Criando um Aggregate

```python
from core.domain.shared.models import AggregateRoot

class Series(AggregateRoot):
    """Agregado de Série com temporadas."""

    id: MediaId
    title: str
    seasons: list[Season]

    def add_season(self, season: Season) -> None:
        self.seasons.append(season)
        self.add_event(SeasonAddedEvent(series_id=self.id, season=season))
```

### Criando um Compound Value Object

```python
from src.domain.shared.models import CompoundValueObject

class Address(CompoundValueObject):
    """Endereço como Value Object composto."""

    street: str
    city: str
    zip_code: str
    country: str = "BR"

# Uso do with_updates() para criar cópia modificada
addr = Address(street="Rua A", city="São Paulo", zip_code="01234-567")
new_addr = addr.with_updates(city="Rio de Janeiro", zip_code="20000-000")
```

### Usando o Protocol SupportsUpdates

```python
from src.domain.shared.models import SupportsUpdates

def apply_discount(obj: SupportsUpdates, field: str, factor: float) -> SupportsUpdates:
    """Aplica desconto a qualquer objeto que suporte updates."""
    current_value = getattr(obj, field)
    return obj.with_updates(**{field: current_value * factor})
```

---

## Histórico

| Data | Mudança |
|------|---------|
| 2025-01-28 | Decisão inicial: Pydantic encapsulado para domain models |
| 2025-02-04 | Refinamento: Adicionado `CompoundValueObject` e `SupportsUpdates` Protocol. `ValueObject` agora é base abstrata. `with_updates()` movido para classes específicas. |
