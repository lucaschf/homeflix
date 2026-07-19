# Funcionalidades

O que o HomeFlix oferece hoje, por área. Esta página descreve **capacidades já
implementadas** — cada item se apoia num módulo do código ou num ADR aceito.
Para os requisitos completos (incluindo o que ainda é planejado), veja
[Requisitos](homeflix-requirements.md); para o que vem a seguir, o
[Roadmap](roadmap.md).

## Bibliotecas e configuração

- **Múltiplas bibliotecas** (filmes, séries ou misto), cada uma com suas fontes
  de diretório e idioma de metadados. A biblioteca é a entidade de configuração
  do sistema ([ADR-005](adr/ADR-005-library-as-configuration-entity.md)).
- **Provedores de metadados ordenados** (TMDB, OMDb) com fallback por prioridade.
- **Preferências de reprodução por biblioteca** — idioma de áudio/legenda e modo
  de legenda (sempre, só se áudio estrangeiro, só forçadas, desligado).
- **Scan agendado** por biblioteca via expressão cron ou apenas manual.
- **Runtime settings** persistidos em banco, por bucket, ajustáveis em runtime
  ([ADR-013](adr/ADR-013-runtime-settings-db-backed.md) /
  [ADR-014](adr/ADR-014-settings-per-bucket-aggregate.md)).

## Scan e detecção de mídia

- **Scanner de filesystem** que detecta vídeos, remove entradas de arquivos
  apagados e deduplica por identidade de conteúdo
  ([ADR-015](adr/ADR-015-scanner-deduplication-by-content-identity.md)).
- **Faixas de áudio e legenda** detectadas do container (via ffprobe) e de
  legendas externas na mesma pasta.
- **Variantes de arquivo** — múltiplas versões do mesmo título (720p/1080p/4K,
  HDR) agrupadas como uma mídia com vários arquivos
  ([ADR-006](adr/ADR-006-media-file-variants.md)).
- **Detecção de abertura (intro)** por frame-hash de vídeo, plugável
  ([ADR-020](adr/ADR-020-pluggable-intro-detector-frame-hash.md)).
- **Detecção de créditos** por sinais visuais (borda + movimento), por arquivo
  ([ADR-021](adr/ADR-021-credits-detector-per-file-visual.md)).
- **Enriquecimento de metadados** via TMDB, localizado por locale
  ([ADR-023](adr/ADR-023-localized-metadata-value-object.md)) e reconciliado na
  camada de aplicação
  ([ADR-025](adr/ADR-025-provider-metadata-reconciliation-in-application.md)).
- **Mirror de artwork do provider** — um job de background baixa poster,
  backdrop e logo (hoje URLs do TMDB) para storage próprio e passa a servi-los
  por um endpoint estável (`/api/v1/artwork/{key}`), com fallback gracioso para
  a URL remota enquanto a arte ainda não foi espelhada. O catálogo deixa de
  depender do CDN do TMDB para exibir artes
  ([ADR-029](adr/ADR-029-artwork-mirroring-storage.md)). Detalhes operacionais no
  [Guia de Mirror de Artwork](standards/artwork-mirroring-guide.md).

## Reprodução (player)

- **Streaming HLS** no navegador, com **transcodificação por hardware**
  (NVENC/NVDEC) e encoder selecionável por configuração
  ([ADR-019](adr/ADR-019-hardware-accelerated-transcoding.md)).
- **Seleção de faixa autoritativa no servidor** — o backend resolve a faixa
  default de áudio/legenda a partir das preferências e o front confia no
  `/tracks` ([ADR-026](adr/ADR-026-server-authoritative-track-selection.md)),
  usando um serviço de domínio `TrackSelector`
  ([ADR-005](adr/ADR-005-library-as-configuration-entity.md)).
- **Multi-áudio e multi-legenda** com nomes de faixa normalizados.
- **OCR de legendas baseadas em imagem** (PGS/VOBSUB) convertidas para faixas de
  texto selecionáveis ([ADR-027](adr/ADR-027-ocr-image-based-subtitles.md)).
- **Skip intro / skip créditos** a partir dos marcadores detectados, e
  **trickplay** (thumbnails de scrub) na barra de progresso.

## Progresso e histórico

- **Salvamento automático de progresso**, com marcação de "completo" ao atingir
  ~90% e retomada exata (*continue watching*). O progresso é **escopo por
  perfil**.

## Listas e coleções

- **Watchlist**, **favoritos** e **listas personalizadas** (com reordenação),
  todos escopo por perfil.

## Busca e navegação

- **Busca full-text** (SQLite FTS5) sobre campos localizados, com navegação por
  gênero e por ator, ordenados pelo título localizado.

## Multi-usuário e identidade

- **Usuários, perfis e sessões** com autenticação por cookie
  ([ADR-010](adr/ADR-010-identity-bounded-context.md) /
  [ADR-011](adr/ADR-011-authentication-strategy.md)).
- **ACL por perfil** — cada perfil enxerga apenas as bibliotecas permitidas
  (`allowed_library_ids`), com flag de perfil infantil e avatares.
- **Catalog Requests ("Em breve")** — pedidos de títulos ausentes com
  **subscriptions multi-usuário e fanout**, resolvidos quando o scanner encontra
  o título ([ADR-022](adr/ADR-022-catalog-requests-subscriptions-fanout.md)).
- **Notificações** de eventos de catálogo e da casa.

## Administração e operação

- **Painel admin** com dashboard de tarefas (job runs), execuções de scan,
  edição manual de marcadores de abertura e sinalização de mídia enriquecida
  incorretamente para revisão.
- **Contratos de presentation publicados** para imports cross-BC
  ([ADR-024](adr/ADR-024-published-presentation-contracts-cross-bc.md)).
