# ADR-032: Decompor o módulo `media` em subdomínios

**Status:** Aceito
**Data:** 2026-08-16
**Deciders:** Lucas Cristovam
**Technical Story:** Auditoria de débito técnico (multi-agente, 2026-08-16) — achado dominante: `media` é um monólito de ~39.8k LOC que solda subdomínios de volatilidade independente. Onda 2 do `docs/tech-debt-remediation-plan.md`. Depende do ADR-033 (ISP em repositórios) como enabler.

---

## Contexto

O bounded context `media` (`src/modules/media/`) tem **~39.8k LOC — cerca de 10× o próximo módulo** (collections, 4.8k). Ele concentra responsabilidades que mudam por razões diferentes:

- **Catálogo** (core): agregados Movie / Series / Season / Episode, CRUD, busca (FTS5), navegação por gênero, variantes de arquivo, dedup/conflitos.
- **Streaming / Playback**: geração HLS, probe (ffprobe/NVENC), thumbnails/trickplay, range/file streaming, OCR de legendas.
- **Metadata / Enrichment**: cliente TMDB, reconciliação de metadados, artwork mirror.
- **Detecção de playback** (marcadores): skip-intro (frame-hash), créditos (sinais visuais), scrub-preview.

A auditoria mediu a assimetria de volatilidade: `infrastructure/streaming/` teve **44 commits** contra 9 de `file_system/`. Isso é **Divergent Change** materializado — um ajuste de flag de codec, um quirk de NVENC, um fix de timing WebVTT e uma mudança de política de enrichment editam o **mesmo** módulo, e cada mudança re-testa e re-deploya os 39.8k LOC inteiros.

Crucialmente, a auditoria confirmou que **os seams já estão desenhados**: `hls_service.py` importa **zero entidades** (só ports + `track_naming`) e `GenerateHlsPlaylistUseCase` opera inteiramente via `HlsPlaylistPort` recebendo `file_path: str`. O trabalho pesado de desacoplamento já foi feito; falta formalizar a fronteira.

O ADR-008 estabeleceu módulos como bounded contexts; este ADR **refina a fronteira interna do `media`**, que cresceu além de um único subdomínio coeso.

## Decisão

Nós iremos **extrair os subdomínios do `media` em módulos próprios de forma incremental (Strangler-Fig)**, um por vez, na ordem de menor fricção → maior acoplamento. A comunicação cross-BC continua por **ports + ACL + integration events** (ADR-009, ADR-024) — nunca import direto entre módulos.

**Ordem de extração:**

1. **Streaming / Playback** (subdomínio *Generic*) — **primeiro**. O seam já existe: consome `file_path`/probe primitives via ports e devolve playlists/streams/ranges. Novo módulo `playback` (ou `streaming`) com HLS, probe, thumbnail, range streaming e OCR de legendas. Contrato de port: `file_path` in → m3u8/range out. A fatia de OCR de legendas é levemente mais acoplada (resolve o `file_path` a partir da entidade), então recebe um **media-lookup port** dedicado.

2. **Metadata / Enrichment + Artwork** (subdomínio *Supporting*) — **segundo**. Mais acoplado: `enrich_movie_metadata` chama `uow.movies.save`. Resolver a escrita de volta com um **evento de integração `MetadataResolved`** ou um write-port estreito, em vez de o módulo de metadata escrever direto no agregado de catálogo.

3. **Marcadores de playback** (intro / créditos / scrub) — **terceiro**. Hoje vazados como colunas nos agregados Episode/Season/Movie. Modelar como **read-model keyed by `media_id`** (ex.: `PlaybackMarkers`), removendo as colunas dos agregados de catálogo (requer migration).

**O que permanece em `media`:** o núcleo de catálogo — os agregados Movie/Series/Season/Episode, CRUD, busca, navegação por gênero, variantes e dedup/conflitos.

Cada extração é seu próprio PR faseado, precedido pela segregação do repositório correspondente (ADR-033), e validado contra a suíte antes do merge.

## Consequências

### Positivas

- **Blast radius menor**: uma mudança de HLS/transcode deixa de re-testar/re-deployar o catálogo inteiro.
- **Volatilidade isolada**: o subdomínio de maior churn (streaming) sai do caminho crítico do catálogo.
- **Fronteiras de subdomínio explícitas** (Core vs Generic vs Supporting), alinhadas à linguagem ubíqua.
- **Deploy/teste independentes** por subdomínio; menor superfície de colisão em reviews/merges.

### Negativas

- Mais módulos e mais plumbing cross-BC (ports, ACL, eventos) — overhead real de indireção.
- Alguns fluxos hoje síncronos (enrichment escrevendo no catálogo) viram assíncronos/event-driven, com a complexidade de consistência eventual associada.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Extração introduz regressão de comportamento | Média | Alto | Strangler-Fig um-por-vez; os seams já existem (streaming não importa entidades); ~3.340 testes como rede; cada fatia é PR isolado com CI. |
| Extração de marcadores toca o schema do catálogo | Média | Médio | Migration dedicada movendo as colunas para o read-model; feature-flag/backfill se necessário. |
| Módulos acabam anêmicos (só transporte) | Baixa | Médio | Só extrair subdomínios com volatilidade e linguagem próprias (streaming, metadata, markers têm); não fatiar por camada. |
| Over-plumbing de eventos antes da necessidade | Baixa | Baixo | Começar por streaming (port simples, sem evento); introduzir eventos só onde o acoplamento de escrita exige (metadata). |

## Alternativas Consideradas

### 1. Manter `media` como monólito

Não fazer nada.

**Rejeitado porque:** o imposto de Divergent Change cresce com cada feature de streaming/detecção; a auditoria já mostra 44 commits concentrados num subdomínio que não pertence ao catálogo.

### 2. Reescrita big-bang (extrair tudo de uma vez)

Quebrar `media` em N módulos num único esforço.

**Rejeitado porque:** risco desproporcional num agregado central com integrações vivas (watch_progress, collections, catalog_requests). Strangler-Fig entrega valor incremental e reversível.

### 3. Fatiar por camada (separar toda a infrastructure, etc.)

**Rejeitado porque:** não reduz acoplamento — os subdomínios continuam soldados horizontalmente. A fronteira que importa é vertical (por subdomínio de negócio), não por camada técnica.

## Referências

- ADR-008: Screaming Architecture com Módulos (fronteira de bounded context)
- ADR-009: Cross-BC Read Ports + ACL
- ADR-024: Contratos de Presentation Publicados para Imports Cross-BC
- ADR-033: Interface Segregation em Repositórios (enabler desta decomposição)
- `docs/tech-debt-remediation-plan.md` — Ondas 3-4
- Vlad Khononov, *Balancing Coupling in Software Design* (volatilidade × distância × força)

---

## Notas de Implementação

Sequência por subdomínio (cada um seguindo o plano de remediação):

1. **Enabler (ADR-033):** segregar o repositório do subdomínio em role-interface antes de mover o código.
2. **Mover** infra + application + use cases do subdomínio para o novo módulo.
3. **Contrato cross-BC:** definir o port/ACL (e evento, quando houver escrita de volta) na fronteira; nunca `from src.modules.<outro>` direto.
4. **Container próprio** (`StreamingContainer`, `MetadataContainer`), composto no `main.py` — o padrão já existente (Onda 5 do plano).
5. **Validar** contra a suíte + smoke, então merge.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-08-16 | Lucas Cristovam | Criação inicial |
