# ADR-008: Screaming Architecture with Modules

**Status:** Aceito
**Data:** 2026-04-02
**Deciders:** Lucas
**Technical Story:** Reorganizar projeto para Screaming Architecture com módulos
**Substitui:** ADR-003

---

## Contexto

A estrutura anterior (ADR-003) organizava o código por **camadas técnicas** na raiz (`domain/`, `application/`, `infrastructure/`, `presentation/`), com bounded contexts aninhados dentro de cada camada. Isso significava:

1. Para entender a feature "Media", era necessário navegar 4 diretórios top-level
2. A pasta `src/` "gritava" arquitetura técnica, não domínio de negócio
3. À medida que novos contextos fossem adicionados, a fragmentação aumentaria
4. Shared code misturava base classes técnicas com value objects de negócio

## Decisão

**Adotamos Screaming Architecture: módulos de negócio como eixo primário, com camadas técnicas internas a cada módulo.**

Olhando `src/modules/`, o desenvolvedor entende imediatamente que o sistema gerencia **media** e **libraries**.

### Estrutura Adotada

```
src/
├── building_blocks/              # Base técnica domain-agnostic
│   ├── domain/
│   │   ├── models.py             # DomainModel, SupportsUpdates
│   │   ├── value_objects.py      # ValueObject, StringVO, IntVO, etc.
│   │   ├── entity.py             # DomainEntity, AggregateRoot
│   │   ├── external_id.py        # ExternalId (prefixed IDs)
│   │   └── errors.py             # CoreException, DomainException hierarchy
│   ├── application/
│   │   └── errors.py             # ApplicationException hierarchy
│   └── infrastructure/
│       └── errors.py             # InfrastructureException hierarchy
│
├── shared_kernel/                # Conceitos de negócio cross-module
│   └── value_objects/
│       ├── file_path.py          # FilePath
│       ├── language_code.py      # LanguageCode
│       └── tracks.py             # AudioTrack, SubtitleTrack
│
├── modules/
│   ├── media/                    # Bounded Context: Media Catalog
│   │   ├── domain/
│   │   │   ├── entities/         # Movie, Series, Season, Episode
│   │   │   ├── value_objects/    # MovieId, Title, Year, Duration, etc.
│   │   │   ├── repositories/     # MovieRepository, SeriesRepository (ABCs)
│   │   │   ├── services/         # FileSelector
│   │   │   └── rule_codes.py
│   │   ├── application/
│   │   │   ├── use_cases/        # GetMovieById, ListMovies, etc.
│   │   │   └── dtos/             # MovieOutput, SeriesOutput, etc.
│   │   ├── infrastructure/
│   │   │   └── persistence/
│   │   │       ├── models/       # SQLAlchemy ORM models
│   │   │       ├── repositories/ # SQLAlchemy implementations
│   │   │       └── mappers/      # Entity <-> ORM mappers
│   │   └── presentation/
│   │       └── routes/
│   │
│   └── library/                  # Bounded Context: Library Management
│       ├── domain/
│       │   ├── entities/         # Library
│       │   ├── value_objects/    # LibraryId, LibraryName, etc.
│       │   ├── repositories/     # LibraryRepository (ABC)
│       │   ├── services/         # TrackSelector
│       │   └── rule_codes.py
│       ├── application/
│       ├── infrastructure/
│       └── presentation/
│
├── infrastructure/               # Infra compartilhada cross-module
│   └── persistence/
│       ├── database.py
│       └── models/
│           └── base.py           # SQLAlchemy Base
│
├── config/
│   ├── settings.py
│   ├── logging.py
│   └── containers/
│       ├── main.py               # ApplicationContainer
│       ├── infrastructure.py     # InfrastructureContainer
│       ├── media.py              # MediaContainer
│       └── library.py            # LibraryContainer
│
└── main.py
```

### Princípios

1. **Módulos não importam entre si** — comunicação futura via integration events no shared_kernel
2. **building_blocks é domain-agnostic** — apenas base classes e patterns técnicos
3. **shared_kernel é mínimo** — apenas VOs genuinamente usados por múltiplos módulos
4. **Cada módulo tem as 4 camadas** — domain, application, infrastructure, presentation
5. **Regra de dependência** — `modules → shared_kernel → building_blocks`

## Consequências

### Positivas

1. **O código "grita" domínio** — `src/modules/media/` diz mais que `src/domain/media/`
2. **Feature completa em um lugar** — tudo sobre Media está sob `modules/media/`
3. **Melhor isolamento** — módulos são independentes, facilitam extração futura
4. **DI containers por módulo** — MediaContainer, LibraryContainer com suas dependências

### Negativas

1. **Paths mais profundos** — `src.modules.media.domain.value_objects.resolution`
2. **Mais boilerplate em `__init__.py`** — cada módulo tem ~10 init files
3. **shared_kernel requer disciplina** — fácil abusar jogando coisas que são de um módulo só

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| shared_kernel crescer demais | Média | Médio | Code review + regra: só entra se 2+ módulos usam |
| Imports circulares entre módulos | Baixa | Alto | Módulos não importam entre si; usar integration events |

## Alternativas Consideradas

### 1. Manter ADR-003 (Camadas na Raiz)

Estrutura anterior com `src/domain/`, `src/application/`, etc.

**Rejeitado porque:** Feature espalhada em 4 diretórios. À medida que o projeto cresce, fica cada vez mais difícil raciocinar sobre um bounded context completo.

### 2. Vertical Slices sem building_blocks

Módulos diretos sem base classes compartilhadas.

**Rejeitado porque:** Duplicação de base classes (Entity, ValueObject, exception hierarchy) em cada módulo.

## Referências

- [Screaming Architecture - Uncle Bob](https://blog.cleancoder.com/uncle-bob/2011/09/30/Screaming-Architecture.html)
- [Clean Architecture - Uncle Bob](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- ADR-003 (substituído por este ADR)

---

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-04-02 | Lucas | Criação inicial |
