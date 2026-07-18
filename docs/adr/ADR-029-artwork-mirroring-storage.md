# ADR-029: Mirror de Artwork de Provider via Port de Storage

**Status:** Proposto
**Data:** 2026-07-18
**Deciders:** Lucas
**Technical Story:** Durabilidade de artes do catálogo — hoje poster/backdrop/logo/still são URLs absolutas do TMDB servidas verbatim ao frontend; se o TMDB remove a imagem, aplica rate limit, o CDN cai, ou o uso é offline, a arte some.

---

## Contexto

Toda arte de catálogo (poster/cover, backdrop/fanart, logo de título, still de episódio, foto de elenco) é hoje armazenada como **URL absoluta do TMDB** e servida **sem alteração** ao cliente. O caminho é:

- `TmdbClient._image_url` (`media/infrastructure/metadata/tmdb_client.py:161`) monta `https://image.tmdb.org/t/p/original/<file_path>` a partir de `_TMDB_IMAGE_BASE` (linha 65). **O fragmento `file_path` cru e o tamanho (`original`) são descartados na fronteira do adapter** — só a URL montada sobrevive downstream.
- A application traduz essas strings em VOs de domínio: `_metadata_field_merge.py:COMMON_FILL_IF_EMPTY` mapeia `poster_url/backdrop_url/logo_url → ImageUrl`; `enrich_series_metadata` embrulha `still_url → ImageUrl(thumbnail_path)`; as artes **localizadas** viram `str` cru dentro do JSON blob de `LocalizedMetadata` (ADR-023), **não** `ImageUrl`.
- A persistência guarda tudo como `String(1000)`/`Text`. A presentation devolve a string **como está** (as DTOs de application são a wire shape) — o browser baixa direto de `image.tmdb.org`.

Isso acopla a **disponibilidade do catálogo à disponibilidade de um terceiro**. Cenários concretos de perda: imagem removida/trocada no TMDB (comum em títulos menos populares), rate limit / indisponibilidade do CDN, e **uso offline** — que para um media manager pessoal servindo mídia de HD local é requisito implícito, não hipótese remota.

Fatos do código que orientam o design:

- **`ImageUrl` (shared_kernel) já é dual-mode.** Aceita URL http(s) **ou** path local absoluto e expõe `is_remote`. O `scrub_preview_path` (sprite VTT gerado localmente) já usa esse mesmo VO com path local — ou seja, há precedente de campo de imagem carregando referência local. **O VO não precisa mudar** para carregar uma referência mirrorada.
- **Já existe um port de storage no projeto.** `AvatarStoragePort` + `LocalAvatarStorage` (módulo identity) esconde o backend, retorna uma **URL relativa `/api/...`** (não path de filesystem), processa bytes com Pillow em `asyncio.to_thread`, é idempotente no delete e usa dir config-driven. O docstring dele antecipa este ADR: *"A future S3 / object-store implementation would just be another adapter satisfying the same contract."* É o template a seguir.
- **Não há storage de artwork** (buscas por `blob`/`minio`/`s3`/storage de imagem de catálogo não acharam nada).

## Decisão

Nós iremos **mirrorar as artes de provider em storage próprio** e servi-las pela nossa API, mantendo a URL remota apenas como fonte de origem e fallback. Concretamente:

**1. Port de storage na application do módulo `media`.**
Introduzir `ArtworkStoragePort` (ABC) em `media/application/ports/`, com adapter concreto em `media/infrastructure/storage/`. A implementação **default é local-disk** (`LocalArtworkStorage`), escrevendo os arquivos sob um diretório configurável (`artwork_storage_directory`, mesmo estilo bootstrap de `hls_cache_directory`) — espelha o precedente `LocalAvatarStorage`. O port é a fronteira; o adapter esconde o backend e **não decide política** (ADR-009: infra via port+adapter; ADR-025: tradução/orquestração de fonte externa é concern de application, a borda não decide). Um adapter de **object storage (MinIO / S3)** é uma implementação válida do mesmo contrato para um cenário multi-node / prod, mas **não é o default** — para escala pessoal single-node o disco local basta e evita a dependência operacional (ver Alternativa 3).

**2. Mirror assíncrono, desacoplado do enrichment.**
O `EnrichMovie/SeriesMetadataUseCase` continua gravando a **URL remota** do TMDB (comportamento atual, inalterado). Um **job de background** (scheduler da infra compartilhada) reconcilia depois: para cada `ImageUrl.is_remote`, baixa os bytes, faz `storage.save(...)`, e substitui o campo por um `ImageUrl` apontando para a referência própria. O enrich **não** fica mais lento nem acoplado à disponibilidade da imagem naquele instante.

**3. Serving via proxy da API (URL estável `/api/...`).**
Os campos de imagem passam a guardar uma referência própria que resolve para um endpoint nosso (ex.: `/api/v1/artwork/{key}`). A API serve os bytes lendo do storage via port. O frontend **nunca** fala com o backend de storage direto — trocar filesystem por object-store não vaza pro cliente. Como a presentation já devolve a string armazenada como está, **a superfície da API muda sem editar schemas** (só entra o passo de resolução chave → URL e o endpoint de serve).

**4. Fallback gracioso — o mirror nunca bloqueia.**
Enquanto uma arte não foi mirrorada (job ainda não rodou, download falhou, TMDB indisponível no momento), o campo mantém a **URL remota** e o cliente continua funcionando exatamente como hoje. O mirror é uma melhoria de durabilidade sobreposta, não um caminho crítico. Falha de mirror é logada e re-tentada, não propagada.

**5. Escopo v1 — todas as artes.**
Top-level (`poster_path`, `backdrop_path`, `logo_path` de Movie/Series + poster de Season), **episode stills** (`thumbnail_path`), **artes localizadas por locale** (`LocalizedFields.{poster,backdrop,logo}_path` — tratadas à parte por serem `str` cru no JSON, não `ImageUrl`) e **fotos de elenco** (`profile_path`). O `scrub_preview_path` **fica fora** — é asset gerado localmente, não vem de provider.

**6. Chave de armazenamento determinística e content-addressed.**
A chave do objeto deriva de `(tipo de entidade, id, tipo de arte, locale, hash do conteúdo)`. Content-hash dá dedup natural (mesmo poster referenciado por vários títulos ocupa um objeto) e cache-busting embutido (mudou a arte → muda a chave → o cliente refetcha), espelhando o `?v=...` do avatar.

## Consequências

### Positivas

- O catálogo deixa de depender do TMDB em runtime para exibir artes: remoção upstream, rate limit, CDN fora do ar e **uso offline** passam a ser tolerados assim que a arte foi mirrorada uma vez.
- O `ImageUrl` VO absorve a mudança **sem alteração** (já dual-mode); a presentation muda "de graça" (devolve a string armazenada). O blast radius fica nos dois choke points já conhecidos: construção (`TmdbClient._image_url`) e atribuição (`_metadata_field_merge` + localized helpers).
- A fronteira fica nítida e discoverable: port de storage (infra, ADR-009), orquestração do mirror (application, ADR-025), invariantes e VO (domínio). Reaproveita o padrão já ratificado pelo `AvatarStoragePort`.
- Proxy via API desacopla o cliente do backend de storage: o disco fica privado, e uma futura troca (MinIO/S3, outro backend) não vaza pro frontend.
- **Zero dependência operacional nova**: o default local-disk não adiciona container, credenciais nem bucket — só um diretório, backupável copiando a pasta. Cabe na escala pessoal single-node sem infra extra.

### Negativas

- A durabilidade da arte passa a depender do **mesmo disco** do resto do app (não há redundância que um object-store daria) e o diretório **cresce** com o catálogo — o backup precisa incluí-lo. Aceitável na escala pessoal; se virar prod multi-node, trocar pelo adapter de object storage (mesmo port).
- Passa a existir **cópia de bytes** e um job de reconciliação com estado (o que já foi mirrorado, o que falhou, retry/backoff) — mais partes móveis que o "só guarda a URL" atual.
- As artes **localizadas** exigem um caminho de código separado do mirror dos campos `ImageUrl` (são `str` no JSON blob), duplicando a lógica de "é remoto? baixa, troca por local".
- **Custo de armazenamento e staleness**: mirrorar tudo (incluindo stills por episódio e fotos de elenco, que têm bastante churn) consome espaço e pode reter arte desatualizada se o provider trocar a imagem sem trocar o `file_path` — mitigado só parcialmente pelo content-hash.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| O job de background nunca roda / falha silenciosa e nada é mirrorado — falsa sensação de durabilidade | Média | Alto | Observabilidade explícita (contagem de pendentes/mirrorados/falhos por execução, log estruturado); fallback gracioso garante que o produto segue funcional mesmo com o job parado |
| Diretório de artwork perdido (disco corrompido / reset) leva junto todo o mirror | Baixa | Médio | Fallback gracioso: o serve degrada para redirect à URL remota de origem quando o arquivo não existe; incluir o diretório no backup; re-mirror reconstrói a partir das URLs remotas ainda armazenadas |
| `file_path` cru do TMDB descartado no adapter dificulta re-derivar tamanho/original para o download | Alta | Baixo | O mirror baixa a partir da **URL já montada** armazenada (é o que existe); não precisa do fragmento cru — a URL absoluta é suficiente para o GET |
| Explosão de armazenamento com stills + elenco em catálogo grande | Baixa | Médio | Content-hash deduplica; escopo é revisável — stills/elenco podem virar opt-in por config se o custo doer |
| Arte trocada upstream com mesmo `file_path` → mirror retém versão velha | Baixa | Baixo | Re-mirror periódico opcional; content-hash detecta mudança quando o `file_path` também muda (caso comum) |

## Alternativas Consideradas

### 1. Manter a URL do TMDB (status quo / não fazer nada)

Continuar guardando e servindo a URL absoluta do provider.

**Rejeitado porque:** é exatamente a fonte do problema — acopla a exibição do catálogo à disponibilidade de um terceiro e **quebra o uso offline**, que é implícito num media manager de HD local.

### 2. Mirror síncrono durante o enrichment

Baixar e subir a imagem dentro do `EnrichMovie/SeriesMetadataUseCase`, na hora.

**Rejeitado porque:** lentifica o enrich (I/O de rede por arte, N artes por título+temporadas+episódios) e o acopla à disponibilidade da imagem **naquele instante** — se o download falha no meio do enrich, ou o enrich vira caminho crítico de imagem, ou some a arte. O mirror assíncrono desacopla as duas preocupações e mantém o enrich como está.

### 3. Object storage (MinIO / S3) como default

Subir MinIO (ou apontar pra um bucket S3) e implementar o adapter S3-compatible como backend default, em vez do disco local.

**Rejeitado (como default, por ora) porque:** adiciona uma dependência operacional (container + credenciais + bucket + config) desproporcional à escala pessoal single-node do HomeFlix, que hoje roda com SQLite/filesystem. O disco local cobre o caso e o backup é copiar uma pasta. **Continua sendo um adapter válido do mesmo `ArtworkStoragePort`** — é exatamente o ponto de troca se o deploy virar multi-node / prod, sem tocar em domínio, use case ou rota.

### 4. URL direta / presigned do backend para o browser

Guardar a URL do objeto no backend de storage (arquivo servido por outro host, ou presigned de object-store) e o cliente baixa direto de lá.

**Rejeitado porque:** acopla o cliente ao endpoint do backend, exige-o acessível externamente, e faz uma troca de backend vazar pro frontend. O proxy via API mantém o backend privado e a URL do cliente estável (`/api/...`), consistente com o `AvatarStoragePort`.

### 5. Mirror lazy no primeiro acesso

Baixar-e-cachear na primeira vez que a arte é servida pelo proxy.

**Rejeitado porque:** se o TMDB já ficou indisponível **antes** do primeiro acesso, a arte se perde — justamente o cenário que o ADR quer cobrir. Além disso o primeiro request fica lento. O job de background mirrora proativamente, sem depender de alguém ter aberto o título.

## Referências

- ADR-009 (Cross-BC Read Ports + ACL) — port+adapter para infra externa
- ADR-025 (Reconciliação de Metadados de Provider é Concern de Application) — a orquestração do mirror é application; a borda não decide
- ADR-023 (Metadados Localizados como Value Object) — as artes localizadas vivem no JSON blob como `str`, tratadas à parte
- ADR-006 (Variantes de Arquivo de Mídia), ADR-017 (Invariantes na camada de domínio)
- `src/modules/identity/application/ports/avatar_storage_port.py` + `src/modules/identity/infrastructure/storage/local_avatar_storage.py` — template do par port/adapter
- `src/shared_kernel/value_objects/image_url.py` — VO dual-mode (URL remota / path local), `is_remote`
- `src/modules/media/infrastructure/metadata/tmdb_client.py` (`_image_url`, `_TMDB_IMAGE_BASE`) — choke point de construção da URL
- `src/modules/media/application/use_cases/_metadata_field_merge.py` — choke point de atribuição `str → ImageUrl`
- `src/config/settings.py` — `thumbnails_directory` / `hls_cache_directory` (padrão de dir config-driven a estender)

---

## Notas de Implementação

```python
# media/application/ports/artwork_storage_port.py
class ArtworkStoragePort(ABC):
    """Persiste bytes de arte e resolve chave -> URL servível pela API.

    O adapter esconde o backend (disco local default; MinIO/S3 alternativo) e
    NÃO decide política — só armazena, recupera e remove.
    """

    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        """Armazena os bytes sob `key`; retorna a URL relativa /api/... servível."""

    async def open(self, key: str) -> StoredArtwork | None:
        """Bytes + content-type (StoredArtwork) para o proxy; None se ausente."""

    async def delete(self, key: str) -> None: ...  # idempotente


# media/application/use_cases/mirror_artwork.py  (rodado pelo scheduler)
#   para cada entidade com ImageUrl.is_remote:
#     bytes, ctype = await http.get(image_url.value)
#     key = artwork_key(kind, entity_id, art_kind, locale, sha256(bytes))
#     served_url = await storage.save(content=bytes, content_type=ctype, key=key)
#     entity = entity.with_poster_path(ImageUrl(served_url))   # troca remoto -> local
#   falha de download/save -> log + retry; mantém a URL remota (fallback gracioso)
#   artes localizadas: mesmo fluxo sobre LocalizedFields.{poster,backdrop,logo}_path (str)
```

Pontos de toque no código (blast radius): endpoint novo `GET /api/v1/artwork/{key}` na presentation de `media`; use case `MirrorArtwork` + registro no scheduler; `ArtworkStoragePort` + `LocalArtworkStorage` + registro no container de `media`; config `artwork_storage_directory` em `settings.py`. `ImageUrl`, mappers e schemas de presentation **não** mudam.

Faseamento (1 PR por item): **PR 1** entrega a fundação — port, `LocalArtworkStorage`, endpoint de proxy, config e fiação (sem mudar o enrichment); **PR 2** o mirror dos campos top-level `ImageUrl` (use case + job em background); **PR 3** estende a stills, artes localizadas e elenco.

Docs a sincronizar ao implementar (docs-maintainer): página do módulo `media` (novo endpoint + fluxo de mirror), `README.md` da raiz (contagem de endpoints), e este ADR promovido de **Proposto → Aceito**.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-07-18 | Lucas | Criação inicial (Proposto) |
| 2026-07-18 | Lucas | Default de storage passa de object-store (MinIO) para disco local; MinIO/S3 vira adapter plugável (Alternativa 3) |
