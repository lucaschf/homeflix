# ADR-005: Library como Entidade de Configuração

**Status:** Aceito
**Data:** 2026-02-03
**Deciders:** Lucas
**Technical Story:** Alinhar arquitetura do HomeFlix com padrões da indústria (Jellyfin, Plex)

---

## Contexto

Os requisitos iniciais (RF-001) mencionavam "diretórios configurados" para scan de mídia, mas não especificavam como essa configuração deveria ser modelada. A premissa implícita era uma configuração global simples com caminhos de mídia.

Entretanto, coleções de mídia reais têm características diversas:

1. **Múltiplas fontes**: Usuários têm mídia espalhada em vários HDs/diretórios
2. **Tipos diferentes de conteúdo**: Filmes, séries, anime, documentários precisam de tratamento distinto
3. **Necessidades de localização**: Filmes brasileiros precisam de metadados em português, anime em japonês
4. **Preferências de provedor**: Anime se beneficia do TVDb/AniDB, filmes do TMDB
5. **Agendamento de scan**: Algumas bibliotecas precisam de atualização frequente, outras são estáticas

Aplicações padrão da indústria (Jellyfin, Plex, Emby) resolvem isso tratando "Library" como uma entidade de configuração de primeira classe, não apenas uma lista de caminhos.

Além disso, arquivos de mídia modernos (especialmente containers MKV) contêm múltiplas faixas de áudio e legenda. Um filme dual-audio deve ser representado como uma única entidade com metadados de faixas, não como múltiplas entradas.

## Decisão

**Introduzimos `Library` como uma entidade de domínio que serve como container de configuração para fontes de mídia.**

Cada Library define:

- **Identidade e nome**: ID único e nome amigável
- **Tipo de conteúdo**: Que tipo de mídia contém (filmes, séries ou misto)
- **Caminhos fonte**: Um ou mais caminhos do filesystem para escanear
- **Localização**: Idioma preferido para busca de metadados
- **Provedores de metadados**: Lista ordenada de provedores com fallback
- **Comportamento de scan**: Agendamento e configurações para scan automático
- **Preferências de reprodução**: Seleção padrão de idioma de áudio/legenda

Entidades de mídia (`Movie`, `Series`, `Episode`) referenciarão sua Library pai.

Também modelamos `AudioTrack` e `SubtitleTrack` como value objects para representar arquivos de mídia multi-faixa, com preferências em nível de Library determinando a seleção padrão de faixas.

### Modelo de Domínio

```python
# domain/library/entities/library.py

class Library(DomainEntity):
    """Uma biblioteca de mídia configurada com settings de scan e reprodução.

    Representa uma coleção de mídia de um ou mais caminhos do filesystem,
    com provedores de metadados específicos e preferências do usuário.

    Attributes:
        id: External ID (formato lib_xxx).
        name: Nome amigável para exibição (ex: "Filmes BR", "Anime").
        library_type: Tipo de conteúdo (movies, series, mixed).
        paths: Caminhos do filesystem para escanear.
        language: Idioma preferido para metadados (ISO 639-1).
        metadata_providers: Lista ordenada de fontes de metadados.
        scan_schedule: Expressão cron para scan automático, ou None.
        settings: Configurações adicionais específicas da biblioteca.

    Example:
        >>> library = Library(
        ...     id=LibraryId.generate(),
        ...     name="Anime",
        ...     library_type=LibraryType.SERIES,
        ...     paths=[FilePath("/media/anime")],
        ...     language="ja",
        ...     metadata_providers=[
        ...         MetadataProviderConfig(provider=MetadataProvider.TVDB, priority=1),
        ...         MetadataProviderConfig(provider=MetadataProvider.TMDB, priority=2),
        ...     ],
        ...     scan_schedule=CronExpression("0 3 * * *"),
        ...     settings=LibrarySettings(),
        ... )
    """
    id: LibraryId | None = None
    name: LibraryName
    library_type: LibraryType
    paths: list[FilePath]
    language: LanguageCode
    metadata_providers: list[MetadataProviderConfig]
    scan_schedule: CronExpression | None = None
    settings: LibrarySettings
    created_at: datetime
    updated_at: datetime


class LibraryType(StrEnum):
    """Tipo de conteúdo que uma biblioteca contém."""
    MOVIES = "movies"
    SERIES = "series"
    MIXED = "mixed"


class MetadataProvider(StrEnum):
    """Provedores de metadados disponíveis."""
    TMDB = "tmdb"
    OMDB = "omdb"
    TVDB = "tvdb"


class MetadataProviderConfig(ValueObject):
    """Configuração de um provedor de metadados dentro de uma biblioteca.

    Attributes:
        provider: O provedor de metadados a usar.
        priority: Ordem na cadeia de fallback (1 = primeiro).
        enabled: Se este provedor está ativo.
    """
    provider: MetadataProvider
    priority: int
    enabled: bool = True


class SubtitleMode(StrEnum):
    """Quando exibir legendas por padrão."""
    ALWAYS = "always"              # Sempre mostrar legenda preferida
    FOREIGN_AUDIO_ONLY = "foreign" # Só quando áudio != idioma preferido
    FORCED_ONLY = "forced"         # Apenas legendas forçadas (placas, traduções)
    NONE = "none"                  # Desligado por padrão


class LibrarySettings(ValueObject):
    """Configurações adicionais para comportamento da biblioteca.

    Attributes:
        preferred_audio_language: Idioma padrão da faixa de áudio.
        preferred_subtitle_language: Idioma padrão de legenda, ou None.
        subtitle_mode: Quando habilitar legendas por padrão.
        generate_thumbnails: Se deve gerar thumbnails de vídeo.
        detect_intros: Se deve detectar timestamps de intro para skip.
        auto_refresh_metadata: Se deve atualizar metadados periodicamente.
    """
    preferred_audio_language: LanguageCode = LanguageCode("en")
    preferred_subtitle_language: LanguageCode | None = None
    subtitle_mode: SubtitleMode = SubtitleMode.FOREIGN_AUDIO_ONLY
    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False
```

### Modelo de Faixas de Áudio e Legenda

```python
# domain/media/value_objects/tracks.py

class AudioTrack(ValueObject):
    """Uma faixa de áudio dentro de um arquivo de mídia.

    Attributes:
        index: Índice da faixa no container (base 0).
        language: Código de idioma ISO 639-1.
        codec: Codec de áudio (aac, ac3, dts, etc.).
        channels: Número de canais de áudio (2=stereo, 6=5.1, 8=7.1).
        title: Título descritivo opcional dos metadados do arquivo.
        is_default: Se está marcado como default no container.
        bitrate: Bitrate em kbps, se disponível.

    Example:
        >>> track = AudioTrack(
        ...     index=0,
        ...     language="en",
        ...     codec="dts-hd",
        ...     channels=8,
        ...     title="English DTS-HD MA 7.1",
        ...     is_default=True,
        ... )
    """
    index: int
    language: LanguageCode
    codec: str
    channels: int
    title: str | None = None
    is_default: bool = False
    bitrate: int | None = None


class SubtitleTrack(ValueObject):
    """Uma faixa de legenda para um arquivo de mídia.

    Pode estar embutida no container ou ser um arquivo externo.

    Attributes:
        index: Índice da faixa (base 0, único entre embutidas+externas).
        language: Código de idioma ISO 639-1.
        format: Formato da legenda (srt, ass, vtt, pgs).
        title: Título descritivo opcional.
        is_default: Se está marcada como default.
        is_forced: Se é uma faixa de legenda forçada (apenas sinais).
        is_external: True se de arquivo separado, False se embutida.
        file_path: Caminho para arquivo de legenda externo, se aplicável.

    Example:
        >>> embedded = SubtitleTrack(
        ...     index=0,
        ...     language="en",
        ...     format="pgs",
        ...     is_default=True,
        ...     is_external=False,
        ... )
        >>> external = SubtitleTrack(
        ...     index=2,
        ...     language="pt-BR",
        ...     format="srt",
        ...     is_external=True,
        ...     file_path=FilePath("/movies/Movie.pt-BR.srt"),
        ... )
    """
    index: int
    language: LanguageCode
    format: str
    title: str | None = None
    is_default: bool = False
    is_forced: bool = False
    is_external: bool = False
    file_path: FilePath | None = None
```

### Entidades de Mídia Atualizadas

**Nota:** A partir do ADR-006, `AudioTrack` e `SubtitleTrack` ficam dentro de `MediaFile`,
não diretamente na entidade. Uma mídia pode ter múltiplos arquivos (variantes de resolução).

```python
# domain/media/entities/movie.py (atualizado)
# Ver ADR-006 para detalhes sobre MediaFile e variantes

class Movie(DomainEntity):
    id: MovieId | None = None
    library_id: LibraryId          # Referência à biblioteca pai
    title: Title
    original_title: Title | None
    year: Year
    synopsis: Synopsis | None
    poster_path: FilePath | None
    backdrop_path: FilePath | None
    genres: list[Genre]
    files: list[MediaFile]         # Múltiplos arquivos (720p, 1080p, 4K)
    tmdb_id: str | None
    imdb_id: str | None
    added_at: datetime
    updated_at: datetime

# Cada MediaFile contém:
# - file_path, file_size, resolution, video_codec, hdr_format
# - audio_tracks: list[AudioTrack]
# - subtitle_tracks: list[SubtitleTrack]
```

### Lógica de Seleção de Faixas

```python
# domain/media/services/track_selector.py

class TrackSelector:
    """Seleciona faixas apropriadas de áudio e legenda baseado em preferências."""

    def select_audio(
        self,
        tracks: list[AudioTrack],
        preferred_language: LanguageCode,
    ) -> AudioTrack | None:
        """Seleciona a melhor faixa de áudio baseado em preferências.

        Prioridade:
        1. Idioma preferido com maior número de canais
        2. Faixa default do arquivo
        3. Primeira faixa disponível
        """
        ...

    def select_subtitle(
        self,
        subtitle_tracks: list[SubtitleTrack],
        audio_language: LanguageCode,
        preferred_language: LanguageCode,
        mode: SubtitleMode,
    ) -> SubtitleTrack | None:
        """Seleciona faixa de legenda baseado no modo e preferências.

        Comportamento por modo:
        - ALWAYS: Retorna legenda do idioma preferido
        - FOREIGN_AUDIO_ONLY: Retorna legenda só se áudio != preferido
        - FORCED_ONLY: Retorna legenda forçada se disponível
        - NONE: Retorna None
        """
        ...
```

## Consequências

### Positivas

1. **Flexibilidade**: Usuários podem organizar mídia por idioma, tipo ou qualquer critério
2. **Melhores metadados**: Cada biblioteca usa provedores apropriados (TVDB para anime)
3. **Scan seletivo**: Escanear apenas bibliotecas específicas em vez de tudo
4. **Alinhamento com indústria**: UX familiar para usuários de Jellyfin/Plex
5. **Suporte multi-faixa**: Tratamento adequado de arquivos dual/tri-audio
6. **Defaults inteligentes**: Seleção automática de faixa baseada em preferências
7. **Escalabilidade**: Fácil adicionar novos tipos de biblioteca ou provedores

### Negativas

1. **Complexidade aumentada**: Mais uma entidade para gerenciar e persistir
2. **Setup necessário**: Usuários devem criar pelo menos uma biblioteca antes de adicionar mídia
3. **Caminho de migração**: Setups simples existentes precisam conversão para modelo de biblioteca

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Excesso de configuração | Média | Baixo | Fornecer defaults sensatos, "Setup Rápido" simples |
| Falhas na detecção de faixas | Média | Médio | Fallback para primeira faixa, permitir override manual |
| Complexidade na validação de caminhos | Baixa | Médio | Validar caminhos na criação da biblioteca, avisar no scan |

## Alternativas Consideradas

### 1. Configuração Global com Múltiplos Caminhos

Lista simples de caminhos nas configurações da aplicação, toda mídia em um pool.

**Rejeitado porque:**
- Sem forma de definir idiomas de metadados diferentes por diretório
- Sem preferência de provedor por tipo de conteúdo
- Organização pobre para coleções grandes

### 2. Tags/Labels em vez de Bibliotecas

Taguear mídia com categorias, filtrar por tags.

**Rejeitado porque:**
- Não resolve o problema do provedor de metadados
- Não ajuda com organização de scan
- Menos intuitivo que conceito de biblioteca

### 3. Arquivos Separados para Cada Faixa de Áudio

Criar múltiplas entradas Movie para cada versão de áudio.

**Rejeitado porque:**
- Um arquivo físico = uma entidade lógica
- Duplicaria metadados e complicaria o gerenciamento
- Não é como as ferramentas da indústria funcionam

## Referências

- [Jellyfin Library Management](https://jellyfin.org/docs/general/server/libraries/)
- [Plex Media Server Libraries](https://support.plex.tv/articles/200264746-quick-start-step-by-step-guides/)
- [MKV Container Specification](https://www.matroska.org/technical/elements.html)
- [ISO 639-1 Language Codes](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes)
- [ADR-006: Variantes de Arquivo de Mídia](ADR-006-media-file-variants.md) - Complementa este ADR com suporte a múltiplas resoluções

---

## Notas de Implementação

### Prefixo de External ID

Seguindo ADR-002, entidades Library usam o prefixo `lib_`:

```python
class LibraryId(PrefixedId):
    prefix = "lib"

# Exemplo: lib_2xK9mPqR7nL4
```

### Posicionamento no Bounded Context

A entidade `Library` pertence a um novo bounded context **Library Management**, que será referenciado pelo Media Catalog. Isso mantém preocupações de configuração separadas de metadados de mídia.

```
domain/
├── library/           # NOVO: Contexto Library Management
│   ├── entities/
│   │   └── library.py
│   ├── value_objects/
│   │   ├── library_settings.py
│   │   └── metadata_provider_config.py
│   └── repositories/
│       └── library_repository.py
├── media/             # Media Catalog (existente)
│   ├── entities/
│   │   ├── movie.py   # Agora tem library_id e files: list[MediaFile]
│   │   └── ...
│   └── value_objects/
│       ├── media_file.py  # NOVO: MediaFile, Resolution, VideoCodec
│       └── tracks.py      # NOVO: AudioTrack, SubtitleTrack
└── ...
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-02-03 | Lucas | Criação inicial |
