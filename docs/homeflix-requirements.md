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

### 3.1 Library Management (Gestão de Bibliotecas)

Responsável por gerenciar a configuração de bibliotecas de mídia.

**Entidades:**
- `Library` - Biblioteca configurada com caminhos e preferências

**Value Objects:**
- `LibraryId` - Identificador único de biblioteca (lib_xxx)
- `LibraryName` - Nome da biblioteca
- `LibraryType` - Tipo de conteúdo (movies, series, mixed)
- `MetadataProviderConfig` - Configuração de provedor de metadados
- `LibrarySettings` - Preferências de reprodução e scan
- `CronExpression` - Expressão de agendamento
- `LanguageCode` - Código de idioma ISO 639-1

**Agregados:**
- `LibraryAggregate` (root: Library)

**ADR:** [ADR-005](adr/ADR-005-library-as-configuration-entity.md)

### 3.2 Media Catalog (Catálogo de Mídia)

Responsável por gerenciar o catálogo de mídia.

**Entidades:**
- `Movie` - Filme individual (pertence a uma Library, contém múltiplos MediaFile)
- `Series` - Série com múltiplas temporadas
- `Season` - Temporada de uma série
- `Episode` - Episódio de uma temporada (contém múltiplos MediaFile)

**Value Objects:**
- `MediaId` - Identificador único de mídia
- `MediaFile` - Arquivo físico de vídeo (variante de resolução)
- `FilePath` - Caminho do arquivo validado
- `Duration` - Duração em segundos
- `Resolution` - Resolução do vídeo (720p, 1080p, 4K, etc.)
- `VideoCodec` - Codec de vídeo (H264, HEVC, AV1)
- `HdrFormat` - Formato HDR (HDR10, Dolby Vision, etc.)
- `AudioTrack` - Faixa de áudio com idioma, codec, canais
- `SubtitleTrack` - Faixa de legenda (embutida ou externa)
- `Genre` - Gênero do conteúdo
- `Year` - Ano de lançamento

**Agregados:**
- `MediaAggregate` (root: Movie ou Series)

**ADRs:** [ADR-005](adr/ADR-005-library-as-configuration-entity.md), [ADR-006](adr/ADR-006-media-file-variants.md)

### 3.3 Watch Progress (Progresso de Visualização)

Rastreia o progresso de visualização do usuário.

**Entidades:**
- `WatchProgress` - Progresso de um item específico
- `WatchHistory` - Histórico completo de visualização

**Value Objects:**
- `ProgressTimestamp` - Posição no vídeo
- `WatchStatus` - not_started | in_progress | completed
- `TrackPreference` - Preferência de áudio/legenda salva

### 3.4 Collections (Coleções)

Gerencia listas e organizações personalizadas.

**Entidades:**
- `Watchlist` - Lista "quero assistir"
- `CustomList` - Listas personalizadas pelo usuário
- `Favorites` - Itens favoritados

**Value Objects:**
- `ListId` - Identificador de lista
- `ListItem` - Item em uma lista (referência + ordem)

### 3.5 Library Scanner (Infraestrutura)

Escaneia o sistema de arquivos e detecta novas mídias.

**Serviços:**
- `FileScanner` - Varre diretórios em busca de mídia
- `MediaInfoExtractor` - Extrai informações de faixas de áudio/legenda (ffprobe)
- `MetadataResolver` - Busca metadados via APIs externas
- `ThumbnailGenerator` - Gera thumbnails dos vídeos

---

## 4. Requisitos Funcionais

### 4.1 Gestão de Bibliotecas

#### RF-001: Criar Biblioteca
**Descrição:** O usuário pode criar bibliotecas para organizar suas mídias.
**Critérios de Aceite:**
- Nome único e descritivo para a biblioteca
- Tipo de conteúdo: filmes, séries ou misto
- Um ou mais caminhos de diretório como fonte
- Idioma preferido para busca de metadados (ex: pt-BR, en, ja)
- Limite de 20 bibliotecas por instalação
**ADR:** [ADR-005](../adr/ADR-005-library-as-configuration-entity.md)

#### RF-002: Configurar Provedores de Metadados
**Descrição:** O usuário pode definir quais provedores de metadados usar por biblioteca.
**Critérios de Aceite:**
- Lista ordenada de provedores (TMDB, OMDb, TVDb)
- Ordem define prioridade de fallback
- Habilitar/desabilitar provedores individualmente
- Provedores default baseados no tipo de biblioteca (TMDB para filmes, TVDb para séries)

#### RF-003: Configurar Preferências de Reprodução
**Descrição:** O usuário pode definir preferências de áudio e legenda por biblioteca.
**Critérios de Aceite:**
- Idioma de áudio preferido (ex: pt-BR)
- Idioma de legenda preferido (ex: pt-BR, ou desabilitado)
- Modo de legenda: sempre, apenas se áudio estrangeiro, apenas forçadas, desligado
- Configurações são aplicadas automaticamente ao iniciar reprodução

#### RF-004: Agendar Scan Automático
**Descrição:** O usuário pode configurar scan automático por biblioteca.
**Critérios de Aceite:**
- Agendamento via expressão cron ou presets (diário, semanal)
- Opção de scan apenas manual
- Cada biblioteca com seu próprio agendamento

#### RF-005: Editar e Excluir Biblioteca
**Descrição:** O usuário pode modificar ou remover bibliotecas existentes.
**Critérios de Aceite:**
- Editar nome, caminhos e configurações
- Excluir biblioteca (soft delete)
- Ao excluir, mídia associada é marcada como órfã (não deletada)
- Confirmação antes de excluir

### 4.2 Scan e Detecção de Mídia

#### RF-006: Escanear Biblioteca
**Descrição:** O sistema deve escanear os diretórios de uma biblioteca e detectar arquivos de vídeo.
**Critérios de Aceite:**
- Suporta formatos: MP4, MKV, AVI, MOV, WMV
- Detecta novos arquivos e remove entradas de arquivos deletados
- Identifica séries por padrão de nome (S01E01, 1x01)
- Cria registro no banco para cada mídia encontrada
- Associa mídia à biblioteca correta
- Extrai informações de faixas de áudio e legenda do arquivo (ffprobe)

#### RF-007: Detectar Faixas de Áudio e Legenda
**Descrição:** O sistema deve detectar e catalogar todas as faixas de áudio e legenda de cada arquivo.
**Critérios de Aceite:**
- Detecta faixas embutidas no container (MKV, MP4)
- Detecta legendas externas (.srt, .vtt, .ass) na mesma pasta
- Extrai metadados: idioma, codec, canais, título
- Identifica faixas marcadas como default ou forced
- Atualiza automaticamente se novas legendas forem adicionadas

#### RF-007.1: Detectar Variantes de Arquivo
**Descrição:** O sistema deve identificar múltiplas versões do mesmo conteúdo (diferentes resoluções).
**Critérios de Aceite:**
- Agrupa arquivos que representam o mesmo filme/episódio (ex: 720p, 1080p, 4K)
- Extrai informações de resolução, codec e HDR de cada variante
- Uma mídia = uma entidade com múltiplos arquivos
- Permite merge/separação manual de variantes incorretamente agrupadas
- Marca automaticamente a melhor qualidade como versão principal
**ADR:** [ADR-006](../adr/ADR-006-media-file-variants.md)

#### RF-008: Buscar Metadados Automaticamente
**Descrição:** O sistema deve buscar metadados usando os provedores configurados na biblioteca.
**Critérios de Aceite:**
- Usa provedores na ordem de prioridade da biblioteca
- Fallback automático se provedor primário falhar
- Usa idioma configurado na biblioteca para busca
- Permite correção manual de matches incorretos
- Cache de metadados para evitar requests repetidos

#### RF-009: Editar Metadados Manualmente
**Descrição:** O usuário pode editar/corrigir metadados de qualquer mídia.
**Critérios de Aceite:**
- Edição de título, sinopse, ano, gênero
- Upload de poster customizado
- Merge de entradas duplicadas
- Forçar re-match com provedor de metadados

#### RF-010: Listar Conteúdo da Biblioteca
**Descrição:** O sistema deve listar o conteúdo das bibliotecas com filtros.
**Critérios de Aceite:**
- Filtro por biblioteca
- Filtros: tipo (filme/série), gênero, ano, status de visualização
- Ordenação: título, data de adição, ano, duração
- Paginação cursor-based
- Busca por texto (título, sinopse)

### 4.3 Reprodução de Mídia

#### RF-011: Reproduzir Vídeo
**Descrição:** O sistema deve reproduzir vídeos diretamente no browser.
**Critérios de Aceite:**
- Streaming via HTTP Range Requests
- Seleção automática de variante baseada nas preferências (resolução, HDR)
- Seleção automática de faixa de áudio baseada nas preferências da biblioteca
- Seleção automática de legenda baseada no modo configurado
- Controles: play, pause, seek, volume, fullscreen

#### RF-011.1: Selecionar Variante de Arquivo
**Descrição:** O usuário pode escolher qual versão do arquivo reproduzir.
**Critérios de Aceite:**
- Lista todas as variantes disponíveis com resolução, codec e tamanho
- Indica se variante tem HDR (e qual formato)
- Auto-seleção baseada em preferências da biblioteca
- Opção de sempre perguntar ou usar automático
- Lembra escolha do usuário para a mídia específica

#### RF-012: Selecionar Faixa de Áudio
**Descrição:** O usuário pode trocar a faixa de áudio durante a reprodução.
**Critérios de Aceite:**
- Lista todas as faixas de áudio disponíveis com idioma e formato
- Troca de faixa em tempo real sem reiniciar o vídeo
- Exibe informações: idioma, codec, canais (5.1, 7.1, etc.)
- Lembra preferência do usuário para a mídia específica

#### RF-013: Selecionar Legenda
**Descrição:** O usuário pode selecionar legendas disponíveis.
**Critérios de Aceite:**
- Lista legendas embutidas e externas
- Permite upload de legenda externa em tempo real
- Ajuste de tamanho e posição da legenda
- Sincronização de legenda (+/- segundos)
- Opção de desativar legenda

#### RF-014: Controles Avançados de Player
**Descrição:** O player deve ter controles avançados de reprodução.
**Critérios de Aceite:**
- Skip intro (pular para timestamp configurado)
- Skip outro/créditos
- Velocidade de reprodução (0.5x a 2x)
- Atalhos de teclado (espaço, setas, etc.)
- Picture-in-Picture

### 4.4 Progresso e Histórico

#### RF-015: Salvar Progresso Automaticamente
**Descrição:** O sistema deve salvar o progresso de visualização automaticamente.
**Critérios de Aceite:**
- Salva a cada 10 segundos de reprodução
- Salva ao pausar ou fechar o player
- Salva faixa de áudio e legenda selecionadas
- Marca como "completo" quando ≥ 90% assistido
- Próximo episódio auto-detectado

#### RF-016: Exibir "Continue Watching"
**Descrição:** O sistema deve mostrar itens em progresso para continuar assistindo.
**Critérios de Aceite:**
- Lista ordenada por último acesso
- Mostra thumbnail no ponto onde parou
- Barra de progresso visual
- Botão "Continuar" vai direto para o timestamp
- Restaura faixa de áudio e legenda da última sessão

#### RF-017: Histórico de Visualização
**Descrição:** O sistema deve manter histórico completo de visualização.
**Critérios de Aceite:**
- Lista todos os itens assistidos com data/hora
- Filtro por período e por biblioteca
- Opção de limpar histórico (individual ou total)

### 4.5 Listas e Favoritos

#### RF-018: Adicionar à Watchlist
**Descrição:** O usuário pode adicionar itens à lista "quero assistir".
**Critérios de Aceite:**
- Adicionar/remover de qualquer tela
- Ordenação manual (drag & drop)
- Contador de itens na watchlist

#### RF-019: Favoritar Item
**Descrição:** O usuário pode marcar itens como favoritos.
**Critérios de Aceite:**
- Toggle de favorito rápido
- Seção dedicada de favoritos
- Exportar lista de favoritos

#### RF-020: Criar Listas Personalizadas
**Descrição:** O usuário pode criar listas temáticas customizadas.
**Critérios de Aceite:**
- Criar lista com nome e descrição
- Adicionar/remover itens
- Reordenar itens
- Limite de 10 listas, 100 itens por lista
- Renomear e excluir listas

### 4.6 Busca e Navegação

#### RF-021: Busca Global
**Descrição:** O sistema deve permitir busca em toda a biblioteca.
**Critérios de Aceite:**
- Busca por título (fuzzy matching)
- Busca em sinopse
- Filtro por biblioteca específica ou todas
- Resultados categorizados (filmes, séries, episódios)
- Sugestões enquanto digita (debounce 300ms)

#### RF-022: Navegação por Gênero
**Descrição:** O sistema deve permitir navegar por gêneros.
**Critérios de Aceite:**
- Lista de gêneros com contagem
- Filtragem combinada de múltiplos gêneros
- "Descobrir" gêneros relacionados

#### RF-023: Página de Detalhes
**Descrição:** Cada mídia deve ter página de detalhes completa.
**Critérios de Aceite:**
- Poster, título, ano, duração, gêneros
- Sinopse completa
- Para séries: lista de temporadas e episódios
- Informações técnicas (resolução, codec, tamanho)
- Lista de faixas de áudio disponíveis (idiomas, formatos)
- Lista de legendas disponíveis (embutidas e externas)
- Biblioteca à qual pertence
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
│   ├── Library/
│   │   ├── CreateLibraryUseCase
│   │   ├── UpdateLibraryUseCase
│   │   ├── DeleteLibraryUseCase
│   │   ├── GetLibraryByIdUseCase
│   │   ├── ListLibrariesUseCase
│   │   ├── ScanLibraryUseCase
│   │   └── GetScanStatusUseCase
│   │
│   ├── Media/
│   │   ├── GetMovieByIdUseCase
│   │   ├── ListMoviesUseCase
│   │   ├── SearchMediaUseCase
│   │   ├── UpdateMediaMetadataUseCase
│   │   ├── RefreshMetadataUseCase
│   │   ├── MergeMediaVariantsUseCase
│   │   ├── SplitMediaVariantsUseCase
│   │   └── SelectMediaFileUseCase
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
│       ├── GetAvailableFilesUseCase
│       ├── GetAudioTracksUseCase
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

### 8.1 Libraries

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/libraries` | Lista todas as bibliotecas |
| POST | `/v1/libraries` | Cria nova biblioteca |
| GET | `/v1/libraries/{id}` | Detalhes da biblioteca |
| PATCH | `/v1/libraries/{id}` | Atualiza biblioteca |
| DELETE | `/v1/libraries/{id}` | Remove biblioteca (soft delete) |
| POST | `/v1/libraries/{id}/scan` | Inicia scan da biblioteca |
| GET | `/v1/libraries/{id}/scan/status` | Status do scan |

### 8.2 Media

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/movies` | Lista filmes (filtro por library_id) |
| GET | `/v1/movies/{id}` | Detalhes do filme (inclui variantes) |
| GET | `/v1/movies/{id}/files` | Lista arquivos/variantes do filme |
| GET | `/v1/series` | Lista séries (filtro por library_id) |
| GET | `/v1/series/{id}` | Detalhes da série |
| GET | `/v1/series/{id}/seasons/{season}` | Episódios da temporada |
| PATCH | `/v1/media/{id}/metadata` | Atualiza metadados |
| POST | `/v1/media/{id}/merge` | Merge variantes incorretamente separadas |
| POST | `/v1/media/{id}/split` | Separa variantes incorretamente agrupadas |

### 8.3 Progress

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/progress/continue-watching` | Lista "continuar assistindo" |
| GET | `/v1/progress/{media_id}` | Progresso de uma mídia |
| POST | `/v1/progress` | Salva progresso (inclui track preferences) |
| DELETE | `/v1/progress/{media_id}` | Limpa progresso |
| GET | `/v1/history` | Histórico de visualização |

### 8.4 Collections

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

### 8.5 Streaming

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/stream/{media_id}` | Stream do vídeo (auto-seleciona variante) |
| GET | `/v1/stream/{media_id}?file_index={n}` | Stream de variante específica |
| GET | `/v1/stream/{media_id}/files` | Lista variantes disponíveis para stream |
| GET | `/v1/stream/{media_id}/audio-tracks` | Lista faixas de áudio da variante |
| GET | `/v1/stream/{media_id}/subtitles` | Lista legendas da variante |
| GET | `/v1/stream/{media_id}/subtitles/{index}` | Legenda específica |
| GET | `/v1/thumbnails/{media_id}` | Thumbnail/poster |

### 8.6 Search

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/v1/search?q={query}` | Busca global |
| GET | `/v1/search?q={query}&library_id={id}` | Busca em biblioteca específica |
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
