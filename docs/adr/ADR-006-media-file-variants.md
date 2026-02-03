# ADR-006: Variantes de Arquivo de Mídia (Múltiplas Resoluções)

**Status:** Aceito
**Data:** 2026-02-03
**Deciders:** Lucas
**Technical Story:** Suportar múltiplas versões de um mesmo filme/episódio (720p, 1080p, 4K)

---

## Contexto

Coleções de mídia reais frequentemente contêm múltiplas versões do mesmo conteúdo em diferentes resoluções ou formatos:

```
/filmes/
  Inception.2010.720p.BluRay.mkv
  Inception.2010.1080p.BluRay.mkv
  Inception.2010.2160p.UHD.HDR.mkv
```

Isso ocorre por diversos motivos:

1. **Compatibilidade**: Nem todos os dispositivos suportam 4K ou HDR
2. **Bandwidth**: Streaming em rede local pode ter limitações
3. **Armazenamento**: Versões menores como backup quando espaço é limitado
4. **Migração gradual**: Usuário atualizando coleção para melhor qualidade

O sistema precisa:
- Reconhecer que são o mesmo filme, não duplicatas
- Compartilhar metadados entre versões
- Permitir ao usuário escolher qual versão reproduzir
- Auto-selecionar a melhor versão baseado em preferências

## Decisão

**Introduzimos `MediaFile` como Value Object para representar cada arquivo físico, e entidades de mídia (`Movie`, `Episode`) contêm uma lista de `MediaFile`.**

Uma mídia = uma entidade com múltiplos arquivos (variantes).

### Modelo de Domínio

```python
# domain/media/value_objects/media_file.py

class VideoCodec(StrEnum):
    """Codecs de vídeo suportados."""
    H264 = "h264"
    H265 = "h265"      # HEVC
    AV1 = "av1"
    VP9 = "vp9"
    MPEG4 = "mpeg4"


class HdrFormat(StrEnum):
    """Formatos HDR suportados."""
    HDR10 = "hdr10"
    HDR10_PLUS = "hdr10+"
    DOLBY_VISION = "dolby_vision"
    HLG = "hlg"


class MediaFile(ValueObject):
    """Um arquivo físico de vídeo representando uma variante de mídia.

    Cada MediaFile é uma versão específica (resolução, codec, HDR) de um
    filme ou episódio. Uma mídia pode ter múltiplos MediaFiles.

    Attributes:
        file_path: Caminho absoluto para o arquivo de vídeo.
        file_size: Tamanho do arquivo em bytes.
        resolution: Resolução do vídeo (720p, 1080p, 4K).
        video_codec: Codec de vídeo utilizado.
        video_bitrate: Bitrate do vídeo em kbps, se disponível.
        hdr_format: Formato HDR, ou None se SDR.
        audio_tracks: Faixas de áudio disponíveis neste arquivo.
        subtitle_tracks: Faixas de legenda disponíveis neste arquivo.
        is_primary: Se esta é a versão principal para exibição de metadados.
        added_at: Quando este arquivo foi detectado.

    Example:
        >>> file_4k = MediaFile(
        ...     file_path=FilePath("/movies/Inception.2160p.mkv"),
        ...     file_size=48_000_000_000,  # ~45GB
        ...     resolution=Resolution.UHD_4K,
        ...     video_codec=VideoCodec.H265,
        ...     hdr_format=HdrFormat.DOLBY_VISION,
        ...     audio_tracks=[...],
        ...     subtitle_tracks=[...],
        ...     is_primary=True,
        ... )
    """
    file_path: FilePath
    file_size: int
    resolution: Resolution
    video_codec: VideoCodec
    video_bitrate: int | None = None
    hdr_format: HdrFormat | None = None
    audio_tracks: list[AudioTrack]
    subtitle_tracks: list[SubtitleTrack]
    is_primary: bool = False
    added_at: datetime


class Resolution(ValueObject):
    """Resolução de vídeo com comparação e ordenação.

    Attributes:
        width: Largura em pixels.
        height: Altura em pixels.
        name: Nome comum (720p, 1080p, 4K).

    Example:
        >>> r1 = Resolution(1920, 1080, "1080p")
        >>> r2 = Resolution(3840, 2160, "4K")
        >>> r2 > r1
        True
    """
    width: int
    height: int
    name: str

    # Constantes comuns
    SD_480P = Resolution(854, 480, "480p")
    HD_720P = Resolution(1280, 720, "720p")
    FHD_1080P = Resolution(1920, 1080, "1080p")
    UHD_4K = Resolution(3840, 2160, "4K")
    UHD_8K = Resolution(7680, 4320, "8K")

    def __gt__(self, other: "Resolution") -> bool:
        return (self.width * self.height) > (other.width * other.height)

    @property
    def total_pixels(self) -> int:
        return self.width * self.height
```

### Entidade Movie Atualizada

```python
# domain/media/entities/movie.py

class Movie(DomainEntity):
    """Um filme na biblioteca de mídia.

    Attributes:
        id: External ID (formato mov_xxx).
        library_id: Biblioteca à qual pertence.
        title: Título de exibição.
        original_title: Título original, se diferente.
        year: Ano de lançamento.
        synopsis: Sinopse do filme.
        poster_path: Caminho para imagem do poster.
        backdrop_path: Caminho para imagem de fundo.
        genres: Lista de gêneros.
        files: Arquivos de vídeo disponíveis (variantes).
        tmdb_id: ID no TMDB.
        imdb_id: ID no IMDb.
        added_at: Quando foi adicionado à biblioteca.
        updated_at: Última atualização.

    Properties:
        primary_file: Arquivo marcado como principal.
        best_file: Arquivo com melhor qualidade.
        available_resolutions: Lista de resoluções disponíveis.
        total_size: Tamanho total de todos os arquivos.
    """
    id: MovieId | None = None
    library_id: LibraryId
    title: Title
    original_title: Title | None = None
    year: Year
    synopsis: Synopsis | None = None
    poster_path: FilePath | None = None
    backdrop_path: FilePath | None = None
    genres: list[Genre]
    files: list[MediaFile]          # MÚLTIPLAS VARIANTES
    tmdb_id: str | None = None
    imdb_id: str | None = None
    added_at: datetime
    updated_at: datetime

    @property
    def primary_file(self) -> MediaFile | None:
        """Retorna o arquivo marcado como principal."""
        return next((f for f in self.files if f.is_primary), None)

    @property
    def best_file(self) -> MediaFile | None:
        """Retorna o arquivo com melhor resolução."""
        if not self.files:
            return None
        return max(self.files, key=lambda f: f.resolution.total_pixels)

    @property
    def available_resolutions(self) -> list[Resolution]:
        """Lista de resoluções disponíveis, ordenadas."""
        resolutions = [f.resolution for f in self.files]
        return sorted(resolutions, key=lambda r: r.total_pixels, reverse=True)

    @property
    def duration(self) -> Duration | None:
        """Duração do arquivo principal (ou melhor disponível)."""
        file = self.primary_file or self.best_file
        return file.duration if file else None

    @property
    def total_size(self) -> int:
        """Tamanho total de todos os arquivos em bytes."""
        return sum(f.file_size for f in self.files)

    def get_file_by_resolution(self, resolution: Resolution) -> MediaFile | None:
        """Encontra arquivo pela resolução especificada."""
        return next((f for f in self.files if f.resolution == resolution), None)
```

### Seleção de Variante

```python
# domain/media/services/file_selector.py

class FileSelector:
    """Seleciona a melhor variante de arquivo baseado em preferências."""

    def select_file(
        self,
        files: list[MediaFile],
        preferred_resolution: Resolution | None,
        max_resolution: Resolution | None,
        prefer_hdr: bool = True,
    ) -> MediaFile | None:
        """Seleciona o melhor arquivo baseado nas preferências.

        Algoritmo de seleção:
        1. Filtra por max_resolution (se definido)
        2. Se preferred_resolution definida, busca exata ou próxima inferior
        3. Se prefer_hdr, prioriza arquivos com HDR
        4. Desempata por maior bitrate

        Args:
            files: Lista de arquivos disponíveis.
            preferred_resolution: Resolução desejada, ou None para melhor.
            max_resolution: Limite máximo de resolução.
            prefer_hdr: Se deve priorizar HDR sobre SDR.

        Returns:
            Melhor arquivo disponível, ou None se lista vazia.

        Example:
            >>> selector = FileSelector()
            >>> file = selector.select_file(
            ...     files=movie.files,
            ...     preferred_resolution=Resolution.FHD_1080P,
            ...     max_resolution=None,
            ...     prefer_hdr=True,
            ... )
        """
        if not files:
            return None

        candidates = files.copy()

        # Filtrar por resolução máxima
        if max_resolution:
            candidates = [
                f for f in candidates
                if f.resolution.total_pixels <= max_resolution.total_pixels
            ]

        if not candidates:
            return None

        # Buscar resolução preferida ou próxima inferior
        if preferred_resolution:
            exact_match = [
                f for f in candidates
                if f.resolution == preferred_resolution
            ]
            if exact_match:
                candidates = exact_match
            else:
                # Pegar a maior resolução que seja <= preferida
                lower = [
                    f for f in candidates
                    if f.resolution.total_pixels <= preferred_resolution.total_pixels
                ]
                if lower:
                    max_lower = max(lower, key=lambda f: f.resolution.total_pixels)
                    candidates = [
                        f for f in candidates
                        if f.resolution == max_lower.resolution
                    ]

        # Priorizar HDR se desejado
        if prefer_hdr:
            hdr_files = [f for f in candidates if f.hdr_format is not None]
            if hdr_files:
                candidates = hdr_files

        # Desempatar por bitrate (maior = melhor)
        return max(candidates, key=lambda f: f.video_bitrate or 0)
```

### Preferências na Library

```python
# domain/library/value_objects/library_settings.py (atualizado)

class LibrarySettings(ValueObject):
    """Configurações de uma biblioteca.

    Attributes:
        preferred_audio_language: Idioma de áudio preferido.
        preferred_subtitle_language: Idioma de legenda preferido.
        subtitle_mode: Modo de exibição de legendas.
        preferred_resolution: Resolução preferida, ou None para melhor.
        max_resolution: Resolução máxima permitida.
        prefer_hdr: Se deve priorizar HDR quando disponível.
        generate_thumbnails: Se deve gerar thumbnails.
        detect_intros: Se deve detectar intros para skip.
        auto_refresh_metadata: Se deve atualizar metadados periodicamente.
    """
    # Preferências de áudio/legenda
    preferred_audio_language: LanguageCode = LanguageCode("en")
    preferred_subtitle_language: LanguageCode | None = None
    subtitle_mode: SubtitleMode = SubtitleMode.FOREIGN_AUDIO_ONLY

    # Preferências de vídeo (NOVO)
    preferred_resolution: Resolution | None = None  # None = sempre melhor
    max_resolution: Resolution | None = None        # None = sem limite
    prefer_hdr: bool = True

    # Comportamento de scan
    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False
```

### Detecção de Variantes no Scan

O scanner precisa identificar quando múltiplos arquivos representam o mesmo conteúdo:

```python
# infrastructure/file_system/variant_detector.py

class VariantDetector:
    """Detecta variantes do mesmo conteúdo baseado em padrões de nome."""

    # Padrões comuns de resolução em nomes de arquivo
    RESOLUTION_PATTERNS = [
        (r"2160p|4k|uhd", Resolution.UHD_4K),
        (r"1080p|fullhd|fhd", Resolution.FHD_1080P),
        (r"720p|hd", Resolution.HD_720P),
        (r"480p|sd", Resolution.SD_480P),
    ]

    def extract_base_name(self, file_path: FilePath) -> str:
        """Remove indicadores de qualidade para obter nome base.

        Example:
            >>> detector.extract_base_name("Inception.2010.1080p.BluRay.mkv")
            "Inception.2010"
            >>> detector.extract_base_name("Inception.2010.4K.HDR.mkv")
            "Inception.2010"
        """
        ...

    def are_variants(self, file1: FilePath, file2: FilePath) -> bool:
        """Verifica se dois arquivos são variantes do mesmo conteúdo."""
        return self.extract_base_name(file1) == self.extract_base_name(file2)

    def group_variants(self, files: list[FilePath]) -> dict[str, list[FilePath]]:
        """Agrupa arquivos por conteúdo base.

        Returns:
            Dicionário com nome base como chave e lista de variantes como valor.
        """
        ...
```

## Consequências

### Positivas

1. **Metadados unificados**: Um filme, um conjunto de metadados, múltiplos arquivos
2. **Escolha do usuário**: Pode selecionar qualidade na hora de reproduzir
3. **Auto-seleção inteligente**: Sistema escolhe melhor versão baseado em preferências
4. **UI limpa**: Não polui biblioteca com "duplicatas"
5. **Flexibilidade**: Suporta cenários de migração gradual de qualidade
6. **Estatísticas corretas**: Contagem de filmes reflete conteúdo real

### Negativas

1. **Complexidade no scan**: Precisa detectar e agrupar variantes
2. **Ambiguidade possível**: Arquivos com nomes muito diferentes podem não ser agrupados
3. **Mais lógica de seleção**: Player precisa decidir qual arquivo usar

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Falso positivo no agrupamento | Baixa | Alto | Permitir separação manual |
| Falso negativo no agrupamento | Média | Médio | Permitir merge manual |
| Arquivo principal deletado | Baixa | Médio | Promover outro a principal automaticamente |

## Alternativas Consideradas

### 1. Uma Entidade por Arquivo

Cada arquivo de vídeo cria uma entidade Movie separada.

**Rejeitado porque:**
- Duplica metadados (título, sinopse, poster baixados 3x)
- Biblioteca poluída com "Inception", "Inception", "Inception"
- Difícil manter consistência entre "cópias"

### 2. Apenas Melhor Qualidade

Sistema ignora versões inferiores, mantém apenas a melhor.

**Rejeitado porque:**
- Usuário pode querer versão específica
- Não atende cenários de compatibilidade
- Perda de flexibilidade

### 3. Soft Links com Entidade Principal

Uma entidade principal, outras são "links" para ela.

**Rejeitado porque:**
- Complexidade desnecessária
- Ainda teria múltiplas entradas no banco
- Value Object dentro da entidade é mais simples

## Referências

- [Plex Multiple Versions](https://support.plex.tv/articles/200381043-multi-version-movies/)
- [Jellyfin Multiple Versions](https://jellyfin.org/docs/general/server/media/movies/#multiple-versions-of-a-movie)
- [Matroska Container](https://www.matroska.org/technical/elements.html)

---

## Notas de Implementação

### Exibição na UI

```
┌────────────────────────────────────────────────────────┐
│  Inception (2010)                                      │
│  ══════════════════════════════════════════════════════│
│                                                        │
│  Versões disponíveis:                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ● 4K Dolby Vision     │ HEVC │ 45.2 GB │ ▶ Play │  │
│  │ ○ 1080p               │ H264 │ 12.1 GB │ ▶ Play │  │
│  │ ○ 720p                │ H264 │  4.3 GB │ ▶ Play │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ☑ Auto-selecionar melhor qualidade                   │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### Estrutura de Pastas Atualizada

```
domain/
├── media/
│   ├── entities/
│   │   ├── movie.py         # Contém files: list[MediaFile]
│   │   ├── episode.py       # Contém files: list[MediaFile]
│   │   └── series.py
│   ├── value_objects/
│   │   ├── media_file.py    # NOVO: MediaFile, Resolution, VideoCodec
│   │   ├── tracks.py        # AudioTrack, SubtitleTrack
│   │   └── ...
│   └── services/
│       ├── file_selector.py # NOVO: Seleção de variante
│       └── track_selector.py
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-02-03 | Lucas | Criação inicial |
