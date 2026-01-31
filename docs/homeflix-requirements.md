# HomeFlix - Plataforma de Streaming Pessoal

## Documento de Requisitos v1.0

---

## 1. Visão Geral

### 1.1 Objetivo do Projeto

**HomeFlix** é uma plataforma de streaming pessoal que gerencia e reproduz filmes e séries armazenados em um HD local. O projeto tem duplo propósito:

1. **Aprendizado**: Servir como laboratório para práticas de arquitetura de software (Clean Architecture, DDD, padrões de API)
2. **Utilidade**: Criar uma ferramenta funcional para organizar e assistir conteúdo de mídia pessoal

### 1.2 Escopo

**Incluído:**
- Gestão de biblioteca de mídia (filmes, séries, episódios)
- Player de vídeo integrado com controles avançados
- Sistema de progresso e "Continue Watching"
- Listas personalizadas e favoritos
- Busca e filtros avançados
- Metadados automáticos (via APIs externas como TMDB)

**Excluído:**
- Notificações push
- Funcionalidades sociais (compartilhamento, comentários)
- Streaming remoto (apenas rede local)
- Sistema de múltiplos usuários/perfis (v1.0)

### 1.3 Stack Técnica

| Camada | Tecnologia |
|--------|------------|
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| **Frontend** | React 18+, TypeScript, TanStack Query, Tailwind CSS |
| **Banco de Dados** | SQLite (dev), PostgreSQL (opcional) |
| **Player** | Video.js ou HLS.js |
| **Metadados** | TMDB API, OMDb API |

---

## 2. Objetivos de Aprendizado (Arquitetura)

### 2.1 Padrões Arquiteturais

| Padrão | Aplicação no Projeto | ADR |
|--------|---------------------|-----|
| **Clean Architecture** | Separação em Domain, Application, Infrastructure, Presentation | - |
| **Domain-Driven Design** | Entidades ricas, Value Objects, Agregados por Bounded Context | - |
| **Repository Pattern** | Abstração de persistência com interfaces no Domain | - |
| **Use Case Pattern** | Cada operação como um use case isolado com Input/Output DTOs | - |
| **Ports & Adapters** | Interfaces na Application, implementações na Infrastructure | ADR-006 |
| **CQRS (simplificado)** | Query Services separados de Commands | - |

### 2.2 Padrões de API e Comunicação

| Padrão | Aplicação no Projeto | Documento |
|--------|---------------------|-----------|
| **API REST v3.0** | Formato padronizado de resposta (data, error, meta, pagination) | api-response-standard-rest-v3.md |
| **Exception Hierarchy** | Hierarquia por camada (Domain, Application, Infrastructure) | exception-hierarchy-clean-architecture.md |
| **i18n** | Mensagens traduzidas pt-BR/en com error_code como chave | api-i18n-guide.md |
| **Prefixed External IDs** | IDs públicos com prefixo por entidade (mov_xxx, ser_xxx) | ADR-002 |

### 2.3 Padrões de Resiliência (APIs Externas)

| Padrão | Aplicação no Projeto | ADR |
|--------|---------------------|-----|
| **External API Auditing** | Toda chamada externa é salva para debugging e compliance | ADR-005 |
| **Retry + Exponential Backoff** | Tenacity para falhas transientes (max 3 tentativas) | ADR-006 |
| **Circuit Breaker** | pybreaker para evitar cascata de falhas (abre após 5 falhas) | ADR-006 |
| **Fallback Strategy** | Provider secundário (OMDb) quando primário (TMDB) falha | ADR-006 |
| **Rate Limit Handling** | Propaga exceção com retry_after, não faz sleep prolongado | ADR-006 |

### 2.4 Padrões de Observabilidade

| Padrão | Aplicação no Projeto | Documento |
|--------|---------------------|-----------|
| **Correlation ID** | ID único por request propagado em logs e APIs externas | observability-production-guide.md |
| **Health Checks** | `/health/live` e `/health/ready` para monitoramento | observability-production-guide.md |
| **Structured Logging** | structlog com JSON em produção, pretty em dev | logging-guide.md |

### 2.5 Padrões de Dados

| Padrão | Aplicação no Projeto | Documento |
|--------|---------------------|-----------|
| **Soft Delete** | `deleted_at` em entidades, nunca DELETE físico | observability-production-guide.md |
| **Cursor Pagination** | Paginação eficiente sem OFFSET | api-response-standard-rest-v3.md |
| **Prefixed External IDs** | IDs públicos com prefixo por entidade (mov_xxx) | ADR-002 |

### 2.6 Padrões de Código

| Padrão | Aplicação no Projeto | Documento |
|--------|---------------------|-----------|
| **Pydantic Domain Models** | Validação declarativa encapsulada em classes base | ADR-001 |
| **Dependency Injection** | dependency-injector com wiring em routes | ADR-004 |
| **AAA Testing** | Arrange-Act-Assert sem comentários, fixtures com factories | testing-guide.md |

### 2.7 Padrões de Infraestrutura

| Padrão | Aplicação no Projeto | Documento |
|--------|---------------------|-----------|
| **CORS** | Configuração para frontend React | observability-production-guide.md |
| **Graceful Shutdown** | Finaliza requests em andamento antes de encerrar | observability-production-guide.md |
| **Database Migrations** | Alembic com rollback | - |

### 2.8 Princípios SOLID Aplicados

```
S - Single Responsibility: Cada Use Case faz uma coisa
O - Open/Closed: Extensão via interfaces (Ports)
L - Liskov Substitution: Implementações de Repository/Provider intercambiáveis
I - Interface Segregation: Interfaces pequenas e focadas (MetadataProvider vs MovieRepository)
D - Dependency Inversion: Domain não conhece Infrastructure, Use Case depende de interfaces
```

### 2.9 Decisões Pragmáticas (Clean Architecture)

| Tópico | Decisão | Documento |
|--------|---------|-----------|
| **Logger** | Acesso direto via `get_logger()`, não injetado | clean-architecture-decisions.md |
| **Settings** | Acesso direto via `get_settings()`, não injetado | clean-architecture-decisions.md |
| **DateTime** | Direto para audit, injetado para regras de negócio | clean-architecture-decisions.md |
| **UUID/IDs** | Geração direta, exceto quando precisar determinismo em testes | clean-architecture-decisions.md |
| **Validação** | Presentation valida formato, Domain valida regras de negócio | clean-architecture-decisions.md |

### 2.10 Métricas de Qualidade

| Métrica | Meta |
|---------|------|
| **Cobertura de testes** | ≥ 80% no Domain e Application |
| **Complexidade ciclomática** | ≤ 10 por função |
| **Dependency Rule** | Nenhuma violação (Domain não importa Infrastructure) |
| **Type hints** | 100% coverage com mypy strict |

### 2.11 Documentação

| Tipo | Localização |
|------|-------------|
| **ADRs** | `docs/adr/ADR-XXX-*.md` - Decisões arquiteturais |
| **Standards** | `docs/standards/*.md` - Guias e padrões |
| **API Docs** | OpenAPI auto-gerado pelo FastAPI |
| **CLAUDE.md** | Contexto para AI assistants |

---

## 3. Bounded Contexts (Domínios)

### 3.1 Media Catalog (Contexto Principal)

Responsável por gerenciar o catálogo de mídia.

**Entidades:**
- `Movie` - Filme individual
- `Series` - Série com múltiplas temporadas
- `Season` - Temporada de uma série
- `Episode` - Episódio de uma temporada

**Value Objects:**
- `MediaId` - Identificador único de mídia
- `FilePath` - Caminho do arquivo validado
- `Duration` - Duração em segundos
- `Resolution` - Resolução do vídeo (1080p, 4K, etc.)
- `Genre` - Gênero do conteúdo
- `Year` - Ano de lançamento

**Agregados:**
- `MediaAggregate` (root: Movie ou Series)

### 3.2 Watch Progress (Progresso de Visualização)

Rastreia o progresso de visualização do usuário.

**Entidades:**
- `WatchProgress` - Progresso de um item específico
- `WatchHistory` - Histórico completo de visualização

**Value Objects:**
- `ProgressTimestamp` - Posição no vídeo
- `WatchStatus` - not_started | in_progress | completed

### 3.3 Collections (Coleções)

Gerencia listas e organizações personalizadas.

**Entidades:**
- `Watchlist` - Lista "quero assistir"
- `CustomList` - Listas personalizadas pelo usuário
- `Favorites` - Itens favoritados

**Value Objects:**
- `ListId` - Identificador de lista
- `ListItem` - Item em uma lista (referência + ordem)

### 3.4 Library Scanner (Infraestrutura)

Escaneia o sistema de arquivos e detecta novas mídias.

**Serviços:**
- `FileScanner` - Varre diretórios em busca de mídia
- `MetadataResolver` - Busca metadados via APIs externas
- `ThumbnailGenerator` - Gera thumbnails dos vídeos

---

## 4. Requisitos Funcionais

### 4.1 Gestão de Biblioteca

#### RF-001: Escanear Diretório de Mídia
**Descrição:** O sistema deve escanear diretórios configurados e detectar arquivos de vídeo.
**Critérios de Aceite:**
- Suporta formatos: MP4, MKV, AVI, MOV, WMV
- Detecta novos arquivos automaticamente (manual ou agendado)
- Identifica séries por padrão de nome (S01E01, 1x01)
- Cria registro no banco para cada mídia encontrada

#### RF-002: Buscar Metadados Automaticamente
**Descrição:** O sistema deve buscar metadados (título, sinopse, poster, gênero) em APIs externas.
**Critérios de Aceite:**
- Integração com TMDB API
- Fallback para OMDb API
- Permite correção manual de matches incorretos
- Cache de metadados para evitar requests repetidos

#### RF-003: Editar Metadados Manualmente
**Descrição:** O usuário pode editar/corrigir metadados de qualquer mídia.
**Critérios de Aceite:**
- Edição de título, sinopse, ano, gênero
- Upload de poster customizado
- Merge de entradas duplicadas

#### RF-004: Listar Biblioteca
**Descrição:** O sistema deve listar todo o conteúdo da biblioteca com filtros.
**Critérios de Aceite:**
- Filtros: tipo (filme/série), gênero, ano, status de visualização
- Ordenação: título, data de adição, ano, duração
- Paginação cursor-based
- Busca por texto (título, sinopse)

### 4.2 Reprodução de Mídia

#### RF-005: Reproduzir Vídeo
**Descrição:** O sistema deve reproduzir vídeos diretamente no browser.
**Critérios de Aceite:**
- Streaming via HTTP Range Requests
- Suporte a legendas externas (SRT, VTT)
- Múltiplas faixas de áudio (quando disponível)
- Controles: play, pause, seek, volume, fullscreen

#### RF-006: Controles Avançados de Player
**Descrição:** O player deve ter controles avançados de reprodução.
**Critérios de Aceite:**
- Skip intro (pular para timestamp configurado)
- Skip outro/créditos
- Velocidade de reprodução (0.5x a 2x)
- Atalhos de teclado (espaço, setas, etc.)
- Picture-in-Picture

#### RF-007: Selecionar Legenda
**Descrição:** O usuário pode selecionar legendas disponíveis.
**Critérios de Aceite:**
- Detecta arquivos .srt/.vtt na mesma pasta
- Permite upload de legenda externa
- Ajuste de tamanho e posição da legenda
- Sincronização de legenda (+/- segundos)

### 4.3 Progresso e Histórico

#### RF-008: Salvar Progresso Automaticamente
**Descrição:** O sistema deve salvar o progresso de visualização automaticamente.
**Critérios de Aceite:**
- Salva a cada 10 segundos de reprodução
- Salva ao pausar ou fechar o player
- Marca como "completo" quando ≥ 90% assistido
- Próximo episódio auto-detectado

#### RF-009: Exibir "Continue Watching"
**Descrição:** O sistema deve mostrar itens em progresso para continuar assistindo.
**Critérios de Aceite:**
- Lista ordenada por último acesso
- Mostra thumbnail no ponto onde parou
- Barra de progresso visual
- Botão "Continuar" vai direto para o timestamp

#### RF-010: Histórico de Visualização
**Descrição:** O sistema deve manter histórico completo de visualização.
**Critérios de Aceite:**
- Lista todos os itens assistidos com data/hora
- Filtro por período
- Opção de limpar histórico (individual ou total)

### 4.4 Listas e Favoritos

#### RF-011: Adicionar à Watchlist
**Descrição:** O usuário pode adicionar itens à lista "quero assistir".
**Critérios de Aceite:**
- Adicionar/remover de qualquer tela
- Ordenação manual (drag & drop)
- Contador de itens na watchlist

#### RF-012: Favoritar Item
**Descrição:** O usuário pode marcar itens como favoritos.
**Critérios de Aceite:**
- Toggle de favorito rápido
- Seção dedicada de favoritos
- Exportar lista de favoritos

#### RF-013: Criar Listas Personalizadas
**Descrição:** O usuário pode criar listas temáticas customizadas.
**Critérios de Aceite:**
- Criar lista com nome e descrição
- Adicionar/remover itens
- Reordenar itens
- Limite de 10 listas, 100 itens por lista
- Renomear e excluir listas

### 4.5 Busca e Navegação

#### RF-014: Busca Global
**Descrição:** O sistema deve permitir busca em toda a biblioteca.
**Critérios de Aceite:**
- Busca por título (fuzzy matching)
- Busca em sinopse
- Resultados categorizados (filmes, séries, episódios)
- Sugestões enquanto digita (debounce 300ms)

#### RF-015: Navegação por Gênero
**Descrição:** O sistema deve permitir navegar por gêneros.
**Critérios de Aceite:**
- Lista de gêneros com contagem
- Filtragem combinada de múltiplos gêneros
- "Descobrir" gêneros relacionados

#### RF-016: Página de Detalhes
**Descrição:** Cada mídia deve ter página de detalhes completa.
**Critérios de Aceite:**
- Poster, título, ano, duração, gêneros
- Sinopse completa
- Para séries: lista de temporadas e episódios
- Informações técnicas (resolução, codec, tamanho)
- Ações: Play, Watchlist, Favorito, Editar

---

## 5. Requisitos Não-Funcionais

### 5.1 Performance

| Métrica | Target |
|---------|--------|
| Tempo de resposta API (p95) | < 200ms |
| Tempo de carregamento inicial | < 2s |
| Início de reprodução de vídeo | < 3s |
| Scan de biblioteca (1000 arquivos) | < 60s |

### 5.2 Usabilidade

- Interface responsiva (desktop e tablet)
- Tema escuro (padrão para streaming)
- Navegação por teclado no player
- Acessibilidade básica (ARIA labels)

### 5.3 Confiabilidade

- Graceful degradation se APIs externas falharem
- Retry automático para metadados com backoff
- Transações ACID para operações críticas

### 5.4 Segurança

- CORS configurado apenas para localhost
- Rate limiting básico
- Validação de paths (prevenir directory traversal)
- Headers de segurança padrão

### 5.5 Observabilidade

- Logs estruturados (JSON)
- Request ID em todas as requisições
- Health check endpoint
- Métricas básicas (requests/s, latência, erros)

---

## 6. Modelo de Dados (Entidades Principais)

### 6.1 Movie

```python
@dataclass
class Movie:
    id: MediaId
    title: str
    original_title: str | None
    year: Year
    duration: Duration
    synopsis: str | None
    poster_path: FilePath | None
    backdrop_path: FilePath | None
    genres: list[Genre]
    file_path: FilePath
    file_size: int  # bytes
    resolution: Resolution
    tmdb_id: str | None
    imdb_id: str | None
    added_at: datetime
    updated_at: datetime
```

### 6.2 Series

```python
@dataclass
class Series:
    id: MediaId
    title: str
    original_title: str | None
    start_year: Year
    end_year: Year | None
    synopsis: str | None
    poster_path: FilePath | None
    backdrop_path: FilePath | None
    genres: list[Genre]
    seasons: list[Season]
    tmdb_id: str | None
    imdb_id: str | None
    added_at: datetime
    updated_at: datetime
    
    @property
    def total_episodes(self) -> int: ...
    
    @property
    def total_duration(self) -> Duration: ...
```

### 6.3 Episode

```python
@dataclass
class Episode:
    id: MediaId
    series_id: MediaId
    season_number: int
    episode_number: int
    title: str
    synopsis: str | None
    duration: Duration
    file_path: FilePath
    file_size: int
    resolution: Resolution
    thumbnail_path: FilePath | None
    air_date: date | None
```

### 6.4 WatchProgress

```python
@dataclass
class WatchProgress:
    id: str
    media_id: MediaId
    media_type: Literal["movie", "episode"]
    position: ProgressTimestamp  # segundos
    duration: Duration
    status: WatchStatus
    last_watched_at: datetime
    started_at: datetime
    completed_at: datetime | None
    
    @property
    def percentage(self) -> float:
        return (self.position / self.duration) * 100
```

---

## 7. Casos de Uso Principais

### 7.1 Camada de Aplicação

```
Application/
├── UseCases/
│   ├── Media/
│   │   ├── ScanLibraryUseCase
│   │   ├── GetMovieByIdUseCase
│   │   ├── ListMoviesUseCase
│   │   ├── SearchMediaUseCase
│   │   ├── UpdateMediaMetadataUseCase
│   │   └── RefreshMetadataUseCase
│   │
│   ├── Series/
│   │   ├── GetSeriesByIdUseCase
│   │   ├── ListSeriesUseCase
│   │   ├── GetSeasonEpisodesUseCase
│   │   └── GetNextEpisodeUseCase
│   │
│   ├── Progress/
│   │   ├── SaveProgressUseCase
│   │   ├── GetProgressUseCase
│   │   ├── GetContinueWatchingUseCase
│   │   ├── MarkAsCompletedUseCase
│   │   └── ClearProgressUseCase
│   │
│   ├── Collections/
│   │   ├── AddToWatchlistUseCase
│   │   ├── RemoveFromWatchlistUseCase
│   │   ├── GetWatchlistUseCase
│   │   ├── ToggleFavoriteUseCase
│   │   ├── CreateCustomListUseCase
│   │   └── AddToCustomListUseCase
│   │
│   └── Streaming/
│       ├── GetStreamUrlUseCase
│       ├── GetSubtitlesUseCase
│       └── GetThumbnailUseCase
```

### 7.2 Exemplo de Use Case

```python
# application/use_cases/progress/save_progress_use_case.py

@dataclass
class SaveProgressInput:
    media_id: str
    media_type: Literal["movie", "episode"]
    position_seconds: int
    duration_seconds: int

@dataclass
class SaveProgressOutput:
    progress_id: str
    status: WatchStatus
    percentage: float

class SaveProgressUseCase:
    def __init__(
        self,
        progress_repository: WatchProgressRepository,
        media_repository: MediaRepository,
    ):
        self._progress_repo = progress_repository
        self._media_repo = media_repository
    
    async def execute(self, input: SaveProgressInput) -> SaveProgressOutput:
        # 1. Validar que mídia existe
        media = await self._media_repo.find_by_id(MediaId(input.media_id))
        if not media:
            raise ResourceNotFoundException(
                message="Media not found",
                resource_type="media",
                resource_id=input.media_id,
            )
        
        # 2. Calcular status
        percentage = (input.position_seconds / input.duration_seconds) * 100
        status = self._calculate_status(percentage)
        
        # 3. Criar ou atualizar progresso
        progress = WatchProgress(
            id=generate_id(),
            media_id=MediaId(input.media_id),
            media_type=input.media_type,
            position=ProgressTimestamp(input.position_seconds),
            duration=Duration(input.duration_seconds),
            status=status,
            last_watched_at=datetime.now(UTC),
            # ...
        )
        
        await self._progress_repo.save(progress)
        
        return SaveProgressOutput(
            progress_id=progress.id,
            status=status,
            percentage=percentage,
        )
    
    def _calculate_status(self, percentage: float) -> WatchStatus:
        if percentage >= 90:
            return WatchStatus.COMPLETED
        elif percentage > 0:
            return WatchStatus.IN_PROGRESS
        return WatchStatus.NOT_STARTED
```

---

## 8. API Endpoints (v1)

### 8.1 Media

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/movies` | Lista filmes |
| GET | `/v1/movies/{id}` | Detalhes do filme |
| GET | `/v1/series` | Lista séries |
| GET | `/v1/series/{id}` | Detalhes da série |
| GET | `/v1/series/{id}/seasons/{season}` | Episódios da temporada |
| POST | `/v1/library/scan` | Inicia scan da biblioteca |
| GET | `/v1/library/scan/status` | Status do scan |
| PATCH | `/v1/media/{id}/metadata` | Atualiza metadados |

### 8.2 Progress

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/progress/continue-watching` | Lista "continuar assistindo" |
| GET | `/v1/progress/{media_id}` | Progresso de uma mídia |
| POST | `/v1/progress` | Salva progresso |
| DELETE | `/v1/progress/{media_id}` | Limpa progresso |
| GET | `/v1/history` | Histórico de visualização |

### 8.3 Collections

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/watchlist` | Lista watchlist |
| POST | `/v1/watchlist/{media_id}` | Adiciona à watchlist |
| DELETE | `/v1/watchlist/{media_id}` | Remove da watchlist |
| GET | `/v1/favorites` | Lista favoritos |
| POST | `/v1/favorites/{media_id}` | Favorita |
| DELETE | `/v1/favorites/{media_id}` | Desfavorita |
| GET | `/v1/lists` | Lista custom lists |
| POST | `/v1/lists` | Cria lista |
| GET | `/v1/lists/{id}` | Detalhes da lista |
| POST | `/v1/lists/{id}/items` | Adiciona item |
| DELETE | `/v1/lists/{id}/items/{media_id}` | Remove item |

### 8.4 Streaming

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/stream/{media_id}` | Stream do vídeo (HTTP Range) |
| GET | `/v1/stream/{media_id}/subtitles` | Lista legendas |
| GET | `/v1/stream/{media_id}/subtitles/{lang}` | Legenda específica |
| GET | `/v1/thumbnails/{media_id}` | Thumbnail/poster |

### 8.5 Search

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/search?q={query}` | Busca global |
| GET | `/v1/genres` | Lista gêneros |
| GET | `/v1/genres/{slug}` | Mídia por gênero |

---

## 9. Estrutura de Pastas

```
homeflix/
├── backend/
│   ├── src/
│   │   ├── domain/                    # Camada de Domínio
│   │   │   ├── entities/
│   │   │   │   ├── movie.py
│   │   │   │   ├── series.py
│   │   │   │   ├── episode.py
│   │   │   │   └── watch_progress.py
│   │   │   ├── value_objects/
│   │   │   │   ├── media_id.py
│   │   │   │   ├── file_path.py
│   │   │   │   ├── duration.py
│   │   │   │   └── resolution.py
│   │   │   ├── repositories/          # Interfaces (ports)
│   │   │   │   ├── media_repository.py
│   │   │   │   └── progress_repository.py
│   │   │   ├── services/              # Domain services
│   │   │   │   └── progress_calculator.py
│   │   │   └── exceptions/
│   │   │       └── domain_exceptions.py
│   │   │
│   │   ├── application/               # Camada de Aplicação
│   │   │   ├── use_cases/
│   │   │   │   ├── media/
│   │   │   │   ├── progress/
│   │   │   │   ├── collections/
│   │   │   │   └── streaming/
│   │   │   ├── services/              # Application services
│   │   │   │   └── metadata_service.py
│   │   │   ├── dtos/
│   │   │   │   ├── inputs.py
│   │   │   │   └── outputs.py
│   │   │   └── exceptions/
│   │   │       └── application_exceptions.py
│   │   │
│   │   ├── infrastructure/            # Camada de Infraestrutura
│   │   │   ├── persistence/
│   │   │   │   ├── sqlalchemy/
│   │   │   │   │   ├── models.py
│   │   │   │   │   ├── repositories/
│   │   │   │   │   └── unit_of_work.py
│   │   │   │   └── migrations/
│   │   │   ├── external/
│   │   │   │   ├── tmdb_gateway.py
│   │   │   │   └── omdb_gateway.py
│   │   │   ├── file_system/
│   │   │   │   ├── scanner.py
│   │   │   │   └── thumbnail_generator.py
│   │   │   └── exceptions/
│   │   │       └── infrastructure_exceptions.py
│   │   │
│   │   ├── presentation/              # Camada de Apresentação
│   │   │   ├── api/
│   │   │   │   ├── v1/
│   │   │   │   │   ├── routes/
│   │   │   │   │   │   ├── media_routes.py
│   │   │   │   │   │   ├── progress_routes.py
│   │   │   │   │   │   ├── collections_routes.py
│   │   │   │   │   │   └── streaming_routes.py
│   │   │   │   │   └── schemas/
│   │   │   │   ├── middleware/
│   │   │   │   │   ├── cors.py
│   │   │   │   │   ├── request_id.py
│   │   │   │   │   └── error_handler.py
│   │   │   │   └── dependencies.py
│   │   │   └── exceptions/
│   │   │       └── presentation_exceptions.py
│   │   │
│   │   ├── core/                      # Shared kernel
│   │   │   ├── config.py
│   │   │   ├── exceptions/
│   │   │   │   └── base.py            # CoreException
│   │   │   └── i18n/
│   │   │       ├── locales/
│   │   │       │   ├── en/
│   │   │       │   └── pt-BR/
│   │   │       └── translator.py
│   │   │
│   │   └── main.py                    # Entry point
│   │
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   └── infrastructure/
│   │   ├── integration/
│   │   └── e2e/
│   │
│   ├── pyproject.toml
│   └── Makefile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── api-response-standard-rest-v3.md
│   ├── exception-hierarchy.md
│   ├── api-i18n-guide.md
│   └── api-production-addons.md
│
├── docker-compose.yml
└── README.md
```

---

## 10. Roadmap de Desenvolvimento

### Fase 1: Foundation (2-3 semanas)
- [ ] Setup do projeto (monorepo, CI/CD básico)
- [ ] Estrutura de pastas Clean Architecture
- [ ] Exception hierarchy completa
- [ ] Padrão de resposta REST v3.0
- [ ] Testes unitários do Domain

### Fase 2: Core Domain (2-3 semanas)
- [ ] Entidades: Movie, Series, Episode
- [ ] Value Objects: MediaId, FilePath, Duration
- [ ] Repositories interfaces
- [ ] Use Cases: CRUD básico de mídia
- [ ] Persistência SQLite

### Fase 3: Library Scanner (1-2 semanas)
- [ ] File Scanner service
- [ ] Detecção de padrões de nome
- [ ] Integração TMDB para metadados
- [ ] Thumbnail generation

### Fase 4: Streaming & Player (2 semanas)
- [ ] HTTP Range Requests
- [ ] Endpoint de stream
- [ ] Detecção de legendas
- [ ] Frontend: Player básico

### Fase 5: Progress System (1-2 semanas)
- [ ] WatchProgress entity
- [ ] Save/Load progress
- [ ] Continue Watching
- [ ] Histórico

### Fase 6: Collections (1 semana)
- [ ] Watchlist
- [ ] Favorites
- [ ] Custom Lists

### Fase 7: Polish & UI (2 semanas)
- [ ] Design system
- [ ] Páginas completas
- [ ] Busca e filtros
- [ ] Responsividade

### Fase 8: Production Ready (1 semana)
- [ ] Health checks
- [ ] Logging estruturado
- [ ] Documentação OpenAPI
- [ ] Docker compose

---

## 11. Padrões de Referência (Anexos)

Os seguintes documentos definem padrões a serem seguidos:

1. **api-response-standard-rest-v3.md** - Formato de respostas de API
2. **exception-hierarchy-clean-architecture.md** - Hierarquia de exceções
3. **api-i18n-guide.md** - Internacionalização
4. **api-production-addons.md** - Configurações de produção

---

## 12. Próximos Passos

1. **Validar requisitos** - Revisar com stakeholder (você mesmo 😄)
2. **Definir MVP** - Quais features são essenciais para v1.0?
3. **Setup inicial** - Criar estrutura de pastas e dependências
4. **Primeiro Use Case** - Implementar `ScanLibraryUseCase` como prova de conceito

---

*HomeFlix - Documento de Requisitos v1.0*
*Gerado em: 2025-01-28*
