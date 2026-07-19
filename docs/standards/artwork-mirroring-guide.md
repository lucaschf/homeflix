# Guia — Mirror de Artwork de Provider

Este guia cobre a operação do **mirror de artwork** (ADR-029): o
espelhamento das artes do catálogo (poster, backdrop, logo) — hoje URLs
absolutas do TMDB — para storage que o deploy controla, servidas por um
endpoint próprio e estável.

> **Fonte da verdade da decisão:** [`docs/adr/ADR-029-artwork-mirroring-storage.md`](../adr/ADR-029-artwork-mirroring-storage.md).

---

## 1. Visão Geral

Toda arte do catálogo é enriquecida como **URL absoluta do TMDB** e, por
padrão, servida verbatim ao cliente. Isso acopla a exibição do catálogo à
disponibilidade de um terceiro: imagem removida upstream, rate limit, CDN
fora do ar ou **uso offline** fazem a arte sumir.

O mirror sobrepõe uma camada de durabilidade **sem** alterar o enrichment:
o `EnrichMovie/SeriesMetadataUseCase` continua gravando a URL remota, e um
**job de background** reconcilia depois — baixa os bytes, guarda no
storage e troca a coluna por uma referência local estável
(`/api/v1/artwork/{key}`).

Fluxo: **enrichment** grava URL remota → **job de background**
(`homeflix:artwork-mirror`) encontra colunas ainda remotas → baixa
(SSRF-guarded) → `ArtworkStoragePort.save` → **atualiza a coluna** com a
referência local → o proxy `GET /api/v1/artwork/{key}` serve os bytes do
storage.

É **best-effort e não bloqueante**: enquanto a arte não foi espelhada, a
coluna mantém a URL remota e o cliente funciona exatamente como antes
(fallback gracioso). Uma falha de download/store é logada e re-tentada no
tick seguinte — a URL remota autoritativa nunca é descartada.

### Escopo entregue

- ✅ Campos top-level **poster / backdrop / logo** de **Movie** e
  **Series** (`ArtworkColumns`).
- ✅ **Poster de Season** — mirrorado por coluna direta (`seasons.poster_path`),
  sem round-trip do agregado.
- ✅ **Still de episódio** (`episodes.thumbnail_path`) — mesma via de coluna
  direta; viaja no campo `still` do `ArtworkColumns`.
- ⏳ Artes localizadas por locale e fotos de elenco: **planejados**
  (follow-ups do ADR-029 §5), ainda não implementados.

---

## 2. Endpoint de serving (`GET /api/v1/artwork/{key}`)

Proxy read-only definido em
`src/modules/media/presentation/routes/artwork_routes.py`. O frontend
**nunca** fala com o backend de storage direto — trocar disco por
object-store não vaza para o cliente.

**Auth:** nenhuma (arte de catálogo é imagem pública embutida em `<img>`,
que não carrega header de auth — espelha como as URLs do TMDB eram
servidas). · **Tenant-scoped:** não.

| Param | Origem | Papel |
|-------|--------|-------|
| `key` (path) | URL armazenada na coluna | Nome do objeto no storage. Validado contra `ARTWORK_KEY_PATTERN` (`^[A-Za-z0-9._-]+$`) e rejeitado se for só pontos. |
| `origin` (query, opcional) | URL remota de origem | Para onde redirecionar quando o objeto ainda não foi espelhado. |

**Respostas**

| Status | Quando |
|--------|--------|
| 200 | Objeto existe no storage — serve os bytes com `Cache-Control: public, max-age=31536000, immutable` e `X-Content-Type-Options: nosniff`. |
| 302 | Objeto ausente **e** `origin` é uma URL `https` num host allow-listed (`ALLOWED_ARTWORK_HOSTS` = `{image.tmdb.org}`) — bounce para o provider enquanto o job não alcança. |
| 400 | `key` fora do charset seguro ou só pontos. |
| 404 | Objeto ausente e sem `origin` válido. |

!!! warning "Sem open redirect"
    O fallback `origin` só redireciona para hosts de provider
    allow-listed (`ALLOWED_ARTWORK_HOSTS`, o **mesmo** conjunto de onde o
    downloader baixa). Um `origin` para host arbitrário é tratado como
    miss (404), não como redirect.

!!! note "Cache imutável"
    A chave é content-addressed (hash dos bytes), então o objeto é
    imutável — daí o `Cache-Control` de 1 ano `immutable`. Arte trocada
    upstream vira uma **chave nova**, então o cliente refetcha sozinho
    (cache-busting embutido, sem invalidação manual).

---

## 3. Chave content-addressed (`ArtworkKey`)

`src/modules/media/domain/value_objects/artwork_key.py`. A chave é
`sha256(bytes) + extensão` (ex.: `ab12…ef.jpg`):

- **Dedup natural** — o mesmo poster referenciado por vários títulos ocupa
  um único objeto.
- **Cache-busting** — arte diferente → hash diferente → chave diferente.
- **Single source of truth do charset** — a rota valida input não-confiável
  e o job constrói chaves via `ArtworkKey.for_content`, então tanto a
  leitura quanto a escrita passam pela mesma regra.

Extensão derivada do `Content-Type` (`image/jpeg→.jpg`, `png`, `webp`,
`gif`, `avif`), com fallback para o sufixo da URL de origem e, por fim,
`.jpg`.

---

## 4. Storage (`ArtworkStoragePort`)

Port em `src/modules/media/application/ports/artwork_storage_port.py`
(`save` / `open` / `delete`). O adapter esconde o backend e **não decide
política** — só armazena, recupera e remove.

| Backend | Adapter | Status |
|---------|---------|--------|
| **Disco local (default)** | `LocalArtworkStorage` (`infrastructure/storage/local_artwork_storage.py`) | **Implementado** — o único adapter que existe hoje. Escala pessoal single-node; zero dependência operacional, backup é copiar a pasta. |
| Object storage (MinIO / S3) | — (mesmo port, ainda não implementado) | **Planejado** (ADR-029 Alternativa 3). Ponto de troca para multi-node / prod: basta um adapter novo satisfazendo o `ArtworkStoragePort`, sem tocar em domínio, job ou rota. |

O `LocalArtworkStorage` grava arquivos flat sob `root_directory`, deriva
o content-type da extensão da chave na leitura, e confina o path resolvido
ao diretório raiz (defesa em profundidade contra traversal). I/O de disco
roda em `asyncio.to_thread` (não bloqueia o event loop).

### Onde os arquivos ficam

Um **store central e content-addressed**, não co-localizado por arquivo de
mídia (diferente dos scrub-preview sprites, que ficam em `.homeflix/` ao
lado do vídeo). Concretamente:

- Todas as imagens vão **flat** dentro de um único diretório
  (`artwork_storage_directory`, default `./artwork`), cada uma nomeada
  `{sha256-do-conteúdo}.{ext}` (ex.: `010616cc…bd0.jpg`).
- Content-addressed ⇒ **dedup natural**: o mesmo pôster referenciado por
  vários títulos ocupa **um** arquivo só. Por isso o store é central (por
  título, não por arquivo de vídeo), cobrindo uniformemente movie / series
  / season / episode.
- A coluna no banco guarda a referência própria `/api/v1/artwork/{key}`; a
  rota proxy serve lendo desse mesmo diretório.

Em **produção**, aponte o diretório para um **caminho absoluto num volume
persistente** (ex.: `ARTWORK_STORAGE_DIRECTORY=/data/homeflix/artwork`) —
assim os arquivos não somem em redeploy e o backup é copiar essa pasta.

### Configuração de bootstrap

| Setting | Default | Onde |
|---------|---------|------|
| `artwork_storage_directory` | `./artwork` | `src/config/settings.py` (env/config de boot, no estilo de `hls_cache_directory` / `thumbnails_directory`). |

> Diretório perdido (disco corrompido / reset) não quebra o produto: o
> serve degrada para redirect à URL de origem, e o re-mirror reconstrói a
> partir das URLs remotas ainda armazenadas. **Inclua o diretório no
> backup** se quiser durabilidade real da cópia local.

---

## 5. Download (`ArtworkDownloaderPort`) — SSRF-guarded

Port em `src/modules/media/application/ports/artwork_downloader_port.py`;
adapter `HttpxArtworkDownloader` em `infrastructure/metadata/`. Como o job
baixa uma **URL vinda do banco**, o fetch é uma primitiva de SSRF se não
for restringido. As guardas:

- **`https` + host allow-list** — só `ALLOWED_ARTWORK_HOSTS`
  (`image.tmdb.org` hoje; estender conforme novos providers).
- **Sem seguir redirects** — o alvo não pode desviar o fetch para um host
  interno.
- **Teto de tamanho (`max_bytes`)** — o adapter aborta em vez de bufferizar
  um corpo maior, para uma URL hostil/mis-dimensionada não exaurir memória.

Timeout, erro de transporte, status não-2xx ou corpo acima do teto viram
`GatewayException` — o job captura, mantém a URL remota e re-tenta depois.

---

## 6. Job de background (`homeflix:artwork-mirror`)

`src/infrastructure/scheduling/artwork_mirror_job.py`. Registrado no
scheduler **no boot**, apenas quando o bucket `artwork_mirror` está
`enabled=true` (default), com cadência `interval_minutes`.

Por tick:

1. Lê o snapshot `ArtworkMirrorConfig` (ADR-013) — edições valem no próximo
   tick.
2. Divide o orçamento `batch_size` entre os *kinds* (movies, series), em
   ordem.
3. Para cada título com coluna ainda remota (`find_with_remote_artwork`):
   baixa cada campo remoto, valida que a resposta é uma **imagem suportada**
   (senão mantém a URL remota — evita gravar uma página HTML de rate-limit
   ou um `svg`), calcula a `ArtworkKey`, `storage.save`, e **atualiza a
   coluna** com a referência local.
4. Loga por *kind* quantos títulos foram atualizados e quantas imagens
   foram espelhadas vs. mantidas remotas.

!!! note "Sem round-trip de aggregate"
    A escrita é um **update direto de coluna** numa UoW fresca por título
    (não um save de aggregate) — não apaga coleções-filhas. É um
    last-writer-wins a partir do snapshot de leitura; uma re-enrichment
    concorrente na janela curta fetch→persist poderia ser revertida, mas a
    cadência de 30 min e o re-mirror auto-curativo no tick seguinte tornam
    isso aceitável.

!!! warning "Falsa sensação de durabilidade"
    Se o job nunca roda (bucket desligado, scheduler parado), **nada** é
    espelhado e o catálogo segue dependendo do TMDB — sem quebrar, mas sem
    a durabilidade prometida. Confirme `enabled=true` e acompanhe o log
    `[artwork-mirror] tick complete` (contagens de `mirrored`/`failed` por
    kind).

---

## 7. Configuração (bucket `artwork_mirror`)

Runtime setting persistido em banco, por bucket (ADR-013/014). Definido em
`src/modules/settings/domain/value_objects/artwork_mirror_config.py`.

| Campo | Default | Descrição |
|-------|---------|-----------|
| `enabled` | `true` | Registra o job periódico no boot. |
| `batch_size` | `20` | Máximo de títulos (movies + series) processados por tick. Limita trabalho de rede + disco por run num catálogo grande. |
| `interval_minutes` | `30` | Cadência do job. |
| `max_bytes` | `10485760` (10 MiB) | Teto de uma imagem baixada. Maiores são puladas (mantêm URL remota). |

O bucket aparece no agregado `GET /api/v1/admin/settings` (junto dos demais
buckets, com `source='default'` se nunca foi editado) e é editável por
`PATCH /api/v1/admin/settings/artwork-mirror` (full-replace, body = o
`ArtworkMirrorConfig`; admin-only), no mesmo padrão dos outros buckets.

> `batch_size` e `max_bytes` são lidos **por tick** (edição vale no próximo
> run). `enabled` e `interval_minutes` são lidos **no boot** ao registrar o
> job — mudá-los exige restart.

---

## 8. Diagnóstico Rápido

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Artes ainda apontam para `image.tmdb.org` | Job desligado ou ainda não alcançou o título | Confirmar bucket `enabled=true`; olhar o log `[artwork-mirror] tick complete`; baixar `batch_size`/`interval_minutes` se preciso |
| `404` em `/api/v1/artwork/{key}` sem redirect | Objeto ausente **e** sem `origin` válido | Esperado antes do mirror rodar; garantir que o front passa `?origin=<url-remota>` para o fallback 302 |
| Log `non-image response; keeping remote URL` | Provider serviu HTML (rate-limit/geoblock) ou tipo não suportado | Benigno — a URL remota é mantida e re-tentada; sem ação |
| Diretório de artwork perdido | Disco corrompido / reset | Serve degrada para redirect à origem; re-mirror reconstrói; incluir o diretório no backup |
| Arte não muda após troca upstream com mesmo `file_path` | Content-hash não detecta troca se o `file_path` não mudou | Re-mirror periódico opcional; caso comum (novo `file_path`) já é coberto |
