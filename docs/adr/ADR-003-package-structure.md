# ADR-003: Estrutura de Pacotes e Organização do Projeto

**Status:** Substituído por [ADR-008](ADR-008-screaming-architecture.md)
**Data:** 2025-01-28
**Deciders:** Lucas
**Technical Story:** Definir organização de pastas seguindo Clean Architecture

---

## Contexto

Ao iniciar o projeto HomeFlix, precisamos definir a estrutura de pacotes que:

1. Reflita claramente as camadas da Clean Architecture
2. Facilite a navegação e entendimento do código
3. Permita crescimento organizado
4. Siga convenções da comunidade Python

O projeto anterior usava `core/domain/` como legado, mas queremos seguir as boas práticas desde o início.

## Decisão

**Adotamos estrutura por camadas na raiz, com módulos de domínio aninhados.**

### Estrutura Adotada

```
homeflix/
├── src/
│   ├── domain/                     # 🟢 Camada de Domínio
│   │   ├── shared/                 # Kernel compartilhado
│   │   │   ├── models/             # DomainModel, ValueObject, Entity
│   │   │   ├── exceptions/         # DomainException hierarchy
│   │   │   └── events/             # Domain Events base
│   │   │
│   │   ├── media/                  # Bounded Context: Media Catalog
│   │   │   ├── entities/
│   │   │   ├── value_objects/
│   │   │   ├── repositories/       # Interfaces (ports)
│   │   │   ├── services/           # Domain services
│   │   │   └── events/
│   │   │
│   │   ├── progress/               # Bounded Context: Watch Progress
│   │   │   ├── entities/
│   │   │   ├── value_objects/
│   │   │   └── repositories/
│   │   │
│   │   └── collections/            # Bounded Context: Collections
│   │       ├── entities/
│   │       └── repositories/
│   │
│   ├── application/                # 🟡 Camada de Aplicação
│   │   ├── shared/
│   │   │   ├── exceptions/         # ApplicationException hierarchy
│   │   │   ├── interfaces/         # Gateways, ports
│   │   │   └── dtos/               # Shared DTOs
│   │   │
│   │   ├── media/
│   │   │   ├── use_cases/
│   │   │   │   ├── scan_library.py
│   │   │   │   ├── get_movie.py
│   │   │   │   └── search_media.py
│   │   │   └── dtos/
│   │   │
│   │   ├── progress/
│   │   │   ├── use_cases/
│   │   │   └── dtos/
│   │   │
│   │   └── collections/
│   │       ├── use_cases/
│   │       └── dtos/
│   │
│   ├── infrastructure/             # 🔴 Camada de Infraestrutura
│   │   ├── persistence/
│   │   │   ├── database.py         # Engine, session factory
│   │   │   ├── models/             # SQLAlchemy models
│   │   │   ├── repositories/       # Repository implementations
│   │   │   ├── unit_of_work.py
│   │   │   └── migrations/
│   │   │
│   │   ├── external/
│   │   │   ├── tmdb/               # TMDB API client
│   │   │   └── omdb/               # OMDb API client
│   │   │
│   │   ├── filesystem/
│   │   │   ├── scanner.py          # File scanner
│   │   │   └── thumbnail.py        # Thumbnail generator
│   │   │
│   │   └── exceptions/             # InfrastructureException hierarchy
│   │
│   ├── presentation/               # 🔵 Camada de Apresentação
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── routes/
│   │   │   │   │   ├── media.py
│   │   │   │   │   ├── progress.py
│   │   │   │   │   ├── collections.py
│   │   │   │   │   └── streaming.py
│   │   │   │   └── schemas/        # Pydantic schemas for API
│   │   │   │
│   │   │   ├── middleware/
│   │   │   ├── dependencies/       # FastAPI dependencies
│   │   │   └── exception_handlers/
│   │   │
│   │   └── exceptions/             # PresentationException hierarchy
│   │
│   ├── config/                     # ⚙️ Configuração
│   │   ├── settings.py             # Pydantic Settings
│   │   ├── logging.py
│   │   └── container.py            # DI container
│   │
│   ├── i18n/                       # 🌍 Internacionalização
│   │   ├── locales/
│   │   │   ├── en/
│   │   │   │   ├── errors.json
│   │   │   │   └── validation.json
│   │   │   └── pt-BR/
│   │   │       ├── errors.json
│   │   │       └── validation.json
│   │   └── translator.py
│   │
│   └── main.py                     # 🚀 Entry point
│
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── infrastructure/
│   ├── integration/
│   └── e2e/
│
├── docs/
├── pyproject.toml
├── Makefile
└── docker-compose.yml
```

### Princípios da Estrutura

#### 1. Camadas na Raiz

```
src/
├── domain/          # Regras de negócio puras
├── application/     # Orquestração e use cases
├── infrastructure/  # Implementações concretas
└── presentation/    # API e interface externa
```

**Por quê:** Deixa explícita a arquitetura. Qualquer dev sabe onde cada coisa vai.

#### 2. Bounded Contexts Dentro de Cada Camada

```
domain/
├── media/           # Catálogo de mídia
├── progress/        # Progresso de visualização
└── collections/     # Listas e favoritos
```

**Por quê:** Mantém coesão por domínio, evita `god modules`.

#### 3. Shared Kernel Explícito

```
domain/shared/       # Compartilhado entre bounded contexts
application/shared/
```

**Por quê:** Evita duplicação, mas é explícito sobre o que é compartilhado.

#### 4. Exceptions por Camada

```
domain/shared/exceptions/          # DomainException
application/shared/exceptions/     # ApplicationException
infrastructure/exceptions/         # InfrastructureException
presentation/exceptions/           # PresentationException
```

**Por quê:** Cada camada tem suas próprias exceções, seguindo a hierarquia definida.

## Consequências

### Positivas

1. **Clareza arquitetural** - Estrutura reflete Clean Architecture
2. **Navegação fácil** - Dev sabe onde encontrar cada coisa
3. **Isolamento de mudanças** - Alterações em infra não afetam domain
4. **Testabilidade** - Fácil mockar camadas externas
5. **Onboarding** - Novos devs entendem rapidamente

### Negativas

1. **Mais diretórios** - Estrutura mais profunda que flat
2. **Imports mais longos** - `from domain.media.entities import Movie`
3. **Decisões de localização** - Às vezes não é óbvio onde algo deve ficar

### Mitigações

| Problema | Solução |
|----------|---------|
| Imports longos | `__init__.py` com re-exports públicos |
| Dúvida onde colocar | Este ADR como referência |
| Muitos arquivos pequenos | OK - prefira arquivos focados |

## Alternativas Consideradas

### 1. Estrutura por Feature (Vertical Slices)

```
src/
├── media/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── api/
├── progress/
│   ├── domain/
│   └── ...
```

**Considerado, mas rejeitado:**
- Mais difícil garantir isolamento de camadas
- Shared code fica confuso
- Menos comum em Python/FastAPI

### 2. Flat Structure

```
src/
├── models/
├── services/
├── repositories/
├── routes/
```

**Rejeitado:**
- Não reflete Clean Architecture
- Mistura camadas
- Escala mal

### 3. core/ como Prefixo (Legado)

```
src/
├── core/
│   ├── domain/
│   └── ...
```

**Rejeitado:**
- `core/` adiciona nível desnecessário
- Era convenção do projeto legado
- Não agrega valor semântico

## Referências

- [Clean Architecture - Uncle Bob](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Cosmic Python](https://www.cosmicpython.com/)
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)

---

## Notas de Implementação

### Import Público via `__init__.py`

```python
# domain/media/__init__.py
from domain.media.entities.movie import Movie
from domain.media.entities.series import Series
from domain.media.value_objects import Duration, Year, FilePath

__all__ = ["Movie", "Series", "Duration", "Year", "FilePath"]
```

```python
# Uso simplificado
from domain.media import Movie, Duration
```

### Evitar Imports Circulares

- Domain não importa de Application/Infrastructure
- Application não importa de Infrastructure (usa interfaces)
- Shared pode ser importado por todos

### Checklist para Novos Arquivos

| Pergunta | Localização |
|----------|-------------|
| É regra de negócio pura? | `domain/` |
| Orquestra use case? | `application/` |
| Acessa recurso externo? | `infrastructure/` |
| Expõe para o mundo? | `presentation/` |
| Usado em vários contextos? | `*/shared/` |
