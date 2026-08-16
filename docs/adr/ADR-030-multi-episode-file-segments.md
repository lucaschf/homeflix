# ADR-030: Arquivos de Mídia Multi-Título (Segmentos de Tempo)

**Status:** Aceito
**Data:** 2026-08-09
**Deciders:** Lucas
**Technical Story:** Minisséries antigas onde vários episódios vivem num único arquivo de vídeo (ex.: `20,000 Leagues Under the Sea (1997)`, 2 episódios num só `.mkv`)

---

## Contexto

Coleções reais contêm o caso inverso do ADR-006. O ADR-006 modela **N arquivos → 1 conteúdo** (variantes de resolução do mesmo título). Este ADR trata **1 arquivo → N conteúdos**: um único arquivo físico que contém vários episódios concatenados.

```
G:/homeflix/Series/20,000 Leagues Under the Sea (1997)/
  20,000 Leagues Under the Sea (1997).mkv   # contém E1 (00:00–01:19) + E2 (01:19–02:38)
```

Isso é comum em minisséries antigas ripadas antes de convenções de nomenclatura por episódio. O TMDB enriquece a série corretamente (2 episódios, elenco, sinopses), mas o modelo atual **não consegue mapear os 2 episódios ao mesmo arquivo**:

1. `MediaFile` (VO) modela o arquivo como unidade indivisível, de duração inteira — sem noção de início/fim (`value_objects/media_file.py`).
2. Duas travas no banco impedem compartilhar o arquivo: `media_files.file_path` é `unique` global e `ck_media_file_single_owner` força `movie_id XOR episode_id` (um dono só) (`persistence/models/media_file.py`).
3. O scanner emite **1 arquivo = 1 episódio** (`file_scanner_port.py`, `scanner.py`).
4. O streaming resolve `episode.file_path` e toca o arquivo **do início ao fim** — existe só o seek `start`, não há `end`/clamp de duração (`generate_hls_playlist.py`, `hls_service.py`).

Sintoma observável hoje: a série aparece com E1 (disponível, apontando pro arquivo único) e **E2 "INDISPONÍVEL"** (sem `media_file`), e o E1 na prática reproduz os dois episódios seguidos.

## Decisão

**Introduzimos `FileSegment` como Value Object opcional dentro de `MediaFile`.** Um `MediaFile` passa a poder representar ou o arquivo inteiro (`segment is None`, comportamento atual) ou uma **janela temporal `[start, end]` dentro de um arquivo físico compartilhado**. Vários episódios podem apontar para o **mesmo `file_path`** com segmentos disjuntos.

Uma mídia = uma entidade. Um arquivo físico pode ser referenciado por N segmentos (um por título).

### Modelo de Domínio

```python
# modules/media/domain/value_objects/file_segment.py  (NOVO)

class FileSegment(CompoundValueObject):
    """Janela temporal [start, end] dentro de um arquivo físico.

    Presente quando um único arquivo contém vários títulos (ex.: minissérie
    com 2 episódios num .mkv). Ausente (None) => o MediaFile é o arquivo inteiro.

    Attributes:
        start_seconds: Segundo (inclusivo) onde o título começa no arquivo.
        end_seconds: Segundo (exclusivo) onde o título termina no arquivo.
    """
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_range(self) -> "FileSegment":
        if self.end_seconds <= self.start_seconds:
            raise DomainValidationException(
                message="Segment end must be greater than start",
                message_code="INVALID_FILE_SEGMENT",
            )
        return self

    @property
    def duration_seconds(self) -> int:
        return self.end_seconds - self.start_seconds
```

```python
# modules/media/domain/value_objects/media_file.py  (campo novo)

class MediaFile(CompoundValueObject):
    file_path: FilePath
    file_size: int = Field(ge=0)
    resolution: Resolution
    # ... campos existentes ...
    segment: FileSegment | None = None   # NOVO — None = arquivo inteiro

    @property
    def is_segment(self) -> bool:
        return self.segment is not None
```

**Invariantes de domínio mantidos fora do streaming.** `IntroMarker`, `CreditsMarker` e `WatchProgress` permanecem **relativos ao episódio** (segundo 0 = início do episódio, não do arquivo). A duração do episódio segue sendo `segment.duration_seconds`. A tradução episódio-relativo → arquivo-absoluto acontece **apenas** na borda de streaming (ver Notas de Implementação).

### Persistência

Colunas novas em `media_files` (ambas nullable; `NULL` = arquivo inteiro):

```
start_offset_seconds  INTEGER NULL
end_offset_seconds    INTEGER NULL
```

A unicidade global de `file_path` é **substituída** por uma unique index composta que tolera segmentos disjuntos e ainda barra duplicatas de arquivo inteiro:

```sql
-- antes: UNIQUE(file_path)
CREATE UNIQUE INDEX ux_media_file_path_segment
  ON media_files (file_path, COALESCE(start_offset_seconds, -1), COALESCE(end_offset_seconds, -1));
```

`ck_media_file_single_owner` **permanece** — cada linha ainda pertence a exatamente um episódio; a novidade é que duas linhas (de episódios distintos) podem apontar pro mesmo `file_path`. O partial-unique index de `file_path` na tabela `episodes` recebe o mesmo tratamento composto.

## Consequências

### Positivas

1. **Enriquecimento correto**: a minissérie continua sendo uma Série com N episódios reais, todos disponíveis e reproduzíveis.
2. **Sem cortar arquivos**: preserva o arquivo físico original (não-destrutivo).
3. **Retrocompatível**: `segment=None` reproduz exatamente o comportamento atual; dados existentes não migram de valor.
4. **Domínio cirúrgico**: markers e progresso ficam episódio-relativos; só o streaming conhece o offset absoluto.
5. **Alinhado ao vocabulário do ADR-006**: `MediaFile` continua sendo a unidade de reprodução; segmento é uma visão limitada dela.

### Negativas

1. **Ingestão não é 100% automática**: sem capítulos embutidos, o ponto de corte precisa ser informado (endpoint admin).
2. **Cache HLS por segmento**: o `path_hash` passa a incluir `end`; dois episódios do mesmo arquivo geram buckets distintos.
3. **Mais um caminho no streaming**: a borda precisa clampar o encode do ffmpeg (`-t`).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Offsets errados (áudio/legenda dessincronizados) | Média | Médio | Validar `end > start`; permitir edição via endpoint admin |
| Regressão no caminho arquivo-inteiro | Baixa | Alto | `segment=None` é o default; testes de retrocompatibilidade |
| Keyframe distante do `start` causa seek impreciso | Média | Baixo | `-accurate_seek` já usado; segmentos começam em corte de cena |
| Marker validado contra duração errada | Baixa | Médio | Duração do episódio = `segment.duration_seconds` na criação |

## Alternativas Consideradas

### 1. Cortar o arquivo fisicamente (ffmpeg split)

Dividir o `.mkv` em `S01E01`/`S01E02` e re-escanear.

**Rejeitado porque:** destrutivo, manual por item, duplica bytes ou reencoda, e não resolve o caso de forma sistemática. (É uma saída pontual válida, mas não a decisão arquitetural.)

### 2. Catalogar como Movie único

Tratar o arquivo como um filme.

**Rejeitado porque:** o título é uma minissérie de TV no TMDB — a busca de filme casa mal, degradando o enriquecimento; e perde a estrutura de episódios.

### 3. Série de 1 episódio (arquivo inteiro)

Modelar como série de 1 temporada / 1 episódio.

**Rejeitado porque:** perde a granularidade dos N episódios (metadata, progresso e navegação por episódio), que é justamente o que o TMDB fornece.

### 4. Offsets direto no `MediaFile` sem VO dedicado

Adicionar `start_seconds`/`end_seconds` soltos no `MediaFile`.

**Rejeitado porque:** violaria a coesão de VO (Primitive Obsession — dois inteiros acoplados sem invariante encapsulada). O `FileSegment` encapsula a regra `end > start >= 0` e a `duration_seconds`.

## Referências

- [ADR-006](ADR-006-media-file-variants.md) — decisão inversa (N arquivos → 1 conteúdo)
- [Jellyfin — Multi-episode files](https://jellyfin.org/docs/general/server/media/shows/#multiple-episodes-in-one-file)
- [Plex — Multiple episodes in a single file](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/#toc-3)

---

## Notas de Implementação

### Tradução episódio-relativo → arquivo-absoluto (borda de streaming)

```python
# presentation/stream_routes.py (resolução do episódio segmentado)
segment = episode.primary_file.segment            # FileSegment | None
base = segment.start_seconds if segment else 0
file_start = base + resume_position               # resume vem episódio-relativo
end = segment.end_seconds if segment else None

GenerateHlsPlaylistInput(file_path=..., start=file_start, end=end)
```

```python
# application: GenerateHlsPlaylistInput ganha `end: int | None = None`
# port: ensure_playlist(file_path, start=0, end=None)
# hls_service: quando end is not None -> ffmpeg recebe `-t (end - start)`
#              path_hash key = f"{file_path}:{start}:{end}"
```

### Faseamento (PRs sequenciais)

- **PR 1 — Domínio + persistência (`media`)**: VO `FileSegment`, campo `segment` no `MediaFile`, colunas `start/end_offset_seconds`, unique index composto, mapper, migration Alembic. `segment=None` default → mergeable sozinho, sem mudança de comportamento.
- **PR 2 — Streaming (clamp de sub-range)**: `end` no `GenerateHlsPlaylistInput`/port/`hls_service`, `path_hash` por segmento, tradução episódio-relativo → arquivo-absoluto na rota. Depende do PR 1.
- **PR 3 — Ingestão (popular segmentos)**: use case/endpoint admin pra declarar `(episode_number, start, end)` sobre um arquivo compartilhado — e/ou leitura de capítulos embutidos via ffprobe. Depende do PR 1 (e PR 2 pra reproduzir).

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-08-09 | Lucas | Criação inicial (Proposto) |
| 2026-08-10 | Lucas | Aceito — implementado em 3 PRs (domínio/persistência, streaming, endpoint admin) |
