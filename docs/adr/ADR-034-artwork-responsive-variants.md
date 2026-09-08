# ADR-034: Variantes Responsivas de Artwork Espelhado

**Status:** Aceito
**Data:** 2026-09-08
**Deciders:** Lucas
**Technical Story:** A Home "trava" sem carregar imagens — todo artwork é servido no tamanho `original` do provider (backdrop ~560 KB em média, até 3,2 MB; poster ~520 KB; logo ~300 KB, até 6,8 MB), e um card de 280 px baixa um poster de 2000×3000. O frontend precisa de `srcset` para escolher o tamanho pela viewport e pelo DPR, mas o espelho (ADR-029) só guarda um objeto por imagem.

---

## Contexto

O mirror de artwork (ADR-029) baixa a URL absoluta que o `TmdbClient` montou — sempre `https://image.tmdb.org/t/p/original/<file>` — e a guarda como um único objeto content-addressed (`ArtworkKey` = `sha256(bytes) + ext`), servido por `GET /api/v1/artwork/{key}` com `Cache-Control: immutable`. O tamanho do provider é descartado na borda do adapter (ADR-029, riscos), e o próprio provider oferece renditions menores de graça (`w780`, `w1280` para backdrops; `w342`, `w500` para posters; `w300`, `w500` para logos) que o espelho deixou de aproveitar.

Fatos que orientam o desenho:

- **O original precisa continuar disponível.** Telas largas (3440×1440) exibem o hero em largura total; `w1280` ficaria visivelmente suave. O `srcset` do front declara o original como último candidato.
- **A URL de origem já foi perdida** para ~98% do acervo: a coluna guarda só `/api/v1/artwork/<key>`. Qualquer estratégia que dependa de pedir tamanhos ao TMDB não cobre o que já está espelhado.
- **Pillow já é dependência** e `LocalAvatarStorage` ratificou o padrão de redimensionar em `asyncio.to_thread` a partir do formato decodificado (não do MIME declarado).
- **A escrita do `LocalArtworkStorage` não era atômica** (`write_bytes` direto). Isso era inofensivo enquanto a coluna só apontava para o objeto depois do `save`; deixa de ser quando um objeto é escrito em resposta ao próprio GET que o serve.
- **A rota valida input não confiável com regra de domínio** (`ARTWORK_KEY_PATTERN`) — precedente para validar a largura pedida da mesma forma.
- **Front e back precisam concordar numa escada**: a UI monta `srcset` tanto para URL espelhada (`?w=`) quanto para URL remota do provider (`/t/p/wNNN/`), então a escada só pode conter larguras que o provider também serve.

## Decisão

Nós iremos **servir variantes redimensionadas derivadas do original espelhado**, mantendo o original intocado, com uma escada fixa de larguras compartilhada com o frontend.

**1. Variante é um objeto derivado, nomeado a partir do original.**
`ArtworkKey.variant(width)` produz `<stem>.w<width><ext>` (ex.: `ab12…ef.w1280.jpg`). O marcador fica antes da extensão, então o `LocalArtworkStorage` deriva o mesmo content type da variante e do original, e a chave continua dentro de `ARTWORK_KEY_PATTERN`. Uma variante de variante é rejeitada no domínio (`DomainValidationException`), e a rota devolve 400 — a perda de qualidade nunca se acumula.

**2. Escada no domínio, alinhada ao provider.**
`ArtworkKind` (poster/backdrop/logo/still), `ArtworkWidth` (VO inteiro restrito à união `{300, 342, 500, 780, 1280}`) e `ARTWORK_WIDTH_LADDER` (backdrop 780/1280; poster 342/500; logo 300/500; still 300) vivem em `metadata/domain/value_objects/artwork_variant.py`. A rota valida `?w=` com `ArtworkWidth`; o job pré-gera a escada do tipo; `ArtworkKey.variant` só aceita `ArtworkWidth`, então um objeto fora da escada não pode ser cunhado. O frontend replica a mesma tabela em `utils/artwork.ts`.

**3. Derivação híbrida: sob demanda no GET + pré-geração no mirror.**
`ArtworkVariantService.ensure(key, width)` (application, ADR-025) serve a variante armazenada; num miss lê o original, redimensiona pelo `ArtworkResizerPort`, grava a variante e a serve. O job de mirror chama `pregenerate(key, kind, …)` logo após gravar um original novo, então o primeiro espectador de um título recém-espelhado não paga o resize; o acervo já espelhado ganha variantes conforme é visitado. Não há job de backfill.

**4. Nunca upscale; o original é o fallback universal.**
Original não mais largo que a largura pedida → serve o original e não grava nada. Original corrompido, formato não redimensionável (GIF animado, AVIF) ou falha de disco → serve o original como está e loga. Uma variante é uma otimização, nunca uma nova forma de uma imagem sumir.

**5. Mesmo formato do original.**
JPEG continua JPEG (q85, progressivo), PNG mantém o canal alfa, WebP continua WebP. Sem conversão para um formato canônico: o content type segue a extensão da chave como hoje. A orientação EXIF é aplicada antes do resize, porque a variante perde o tag.

**6. Escrita atômica no storage e single-flight por processo.**
`LocalArtworkStorage._write` grava num arquivo temporário irmão e faz `os.replace` — um leitor concorrente nunca vê um objeto pela metade (que seria cacheado `immutable` por um ano). O serviço mantém um `asyncio.Lock` por chave de variante enquanto alguém a deriva, então um pico de primeiros acessos ao mesmo backdrop redimensiona uma vez; o mapa é limpo quando o lock é liberado. Isso é por processo — suficiente para o deploy single-node; um segundo processo apenas duplicaria trabalho, nunca corromperia o objeto.

**7. Contrato da rota.**
`GET /api/v1/artwork/{key}?w=<width>`: 200 com a variante (ou o original, regra 4) e o mesmo `Cache-Control: immutable`; 400 para largura fora da escada ou chave já variante (validação manual, como o guard de charset — Pydantic devolveria 422); 302/404 como hoje quando o original não foi espelhado. Sem `?w=`, comportamento inalterado.

## Consequências

### Positivas

- Um card de 280 px passa a baixar ~50 KB em vez de ~520 KB; o hero em 1080p baixa `w1280` (~200 KB) em vez de até 3 MB; a tela de 3440 px continua recebendo o original. O tráfego da Home cai perto de 5x sem perder qualidade onde ela importa.
- Original intocado e content-addressed: nenhuma migração de dados, nenhuma coluna nova, nenhum reprocessamento obrigatório do acervo. O `Cache-Control: immutable` continua válido para variantes.
- A escada é um contrato explícito front ↔ back ↔ provider: a mesma URL lógica funciona para arte espelhada e para arte ainda remota.
- Port + adapter (`ArtworkResizerPort` / `PillowArtworkResizer`) e serviço de application seguem exatamente o desenho da ADR-029 e o precedente de `LocalAvatarStorage`; a rota e o job compartilham uma única política.
- A escrita atômica do storage corrige uma fragilidade latente do espelho, independentemente das variantes.

### Negativas

- O diretório de artwork cresce até ~4 objetos extras por imagem (na prática ~30%: variantes são bem menores que os originais).
- O primeiro acesso a cada variante do acervo antigo paga um resize (100–300 ms em thread) e CPU no servidor; a pré-geração só cobre imagens espelhadas daqui para frente.
- A dedup de derivação é por processo; multi-worker duplicaria resizes concorrentes (sem corrupção).
- Mais peças móveis: um port, um adapter, um serviço com estado (mapa de locks), e um segundo caminho de escrita no storage.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Objeto parcial servido e cacheado `immutable` por um ano | Baixa | Alto | Escrita atômica (`tmp` + `os.replace`) no storage; single-flight evita gravações concorrentes da mesma chave |
| `os.replace` falha no Windows por leitor concorrente segurando o arquivo | Baixa | Baixo | `OSError` no `save` → serve o original e loga; a próxima request tenta de novo |
| Original corrompido ou em formato não suportado | Baixa | Baixo | Serve o original como está (status quo), sem cache negativo — o parse que falha é barato |
| MIME e extensão discordam (provider serviu PNG como `image/jpeg`) | Baixa | Baixo | Herdado do original: já falharia sob `nosniff`; a variante se comporta igual |
| Escada diverge entre front e back | Média | Médio | Tabela única no domínio com teste de "união == permitido"; o front replica com comentário de sincronização; largura fora da escada é 400, não silêncio |
| Pico de CPU quando muitos títulos antigos são abertos de uma vez | Baixa | Médio | Resize em thread, single-flight por chave; se doer, uma varredura de pré-geração do acervo é um job novo (não previsto) |

## Alternativas Consideradas

### 1. Baixar os tamanhos do provider no momento do mirror

Pedir `w780`/`w1280`/`w500` ao TMDB e guardar cada um como objeto próprio.

**Rejeitado porque:** a URL de origem já não existe para o acervo espelhado (a coluna guarda só a chave local), então nada do que já foi espelhado ganharia variante; além disso acopla a escada ao provider e não funciona para arte de outra origem.

### 2. Só pré-geração no job + backfill do acervo antigo

Gerar variantes apenas no mirror e criar um finder/job que varre objetos já espelhados.

**Rejeitado porque:** exige um job e um finder novos (as linhas já espelhadas não casam com os finders atuais) e deixa o acervo inteiro sem variantes até a varredura terminar. A derivação sob demanda cobre o acervo antigo sem código de backfill e pela ordem de uso real.

### 3. Redimensionar em toda request, sem armazenar

Sem objetos derivados; a rota redimensiona e devolve.

**Rejeitado porque:** CPU em cada acesso e latência constante, contra um cache de um ano que existe justamente para evitar o proxy em revisitas.

### 4. Tamanho no path (`/api/v1/artwork/{key}/w/{w}`) em vez de query

**Rejeitado porque:** é a mesma coisa com uma rota a mais, e a query preserva a URL do objeto (o que a coluna guarda) como identidade única; `?w=` é ignorado pela rota antiga, então o front degrada bem antes do deploy do backend.

### 5. Deixar o front pedir tamanhos direto ao TMDB

**Rejeitado porque:** contraria a ADR-029 — voltaria a depender do CDN do provider em runtime, justamente o que o espelho elimina.

### 6. Converter as variantes para WebP

~25–35% menores que JPEG/PNG equivalentes, com alfa.

**Rejeitado (por ora) porque:** muda o content type da variante em relação ao original e exige tratar a extensão na chave; o ganho é incremental sobre o que a redução de largura já entrega. Pode virar uma revisão desta ADR.

## Referências

- ADR-029 (Mirror de Artwork via Port de Storage) — objeto original, chave content-addressed, rota de proxy, job de mirror
- ADR-025 (Reconciliação de Provider é Concern de Application) — a política de derivação vive no serviço, os adapters só relatam fatos
- ADR-023 (Metadados Localizados) — não alterada; artes localizadas espelhadas pela revisão de 2026-09-08 da ADR-029 servem variantes do mesmo jeito
- `src/modules/identity/infrastructure/storage/local_avatar_storage.py` — padrão de resize com Pillow em thread
- `homeflix-web/src/utils/artwork.ts` — réplica da escada e montagem de `srcset` no frontend
- Guia operacional: `docs/standards/artwork-mirroring-guide.md`

---

## Notas de Implementação

```python
# metadata/domain/value_objects/artwork_variant.py
class ArtworkKind(StrEnum): POSTER, BACKDROP, LOGO, STILL
ALLOWED_ARTWORK_WIDTHS = frozenset({300, 342, 500, 780, 1280})
class ArtworkWidth(IntValueObject): ...  # só larguras da união
ARTWORK_WIDTH_LADDER = {BACKDROP: (780, 1280), POSTER: (342, 500), LOGO: (300, 500), STILL: (300,)}

# metadata/domain/value_objects/artwork_key.py
ArtworkKey("ab12.jpg").variant(ArtworkWidth(780))  # -> ArtworkKey("ab12.w780.jpg")
ArtworkKey("ab12.w780.jpg").is_variant             # -> True (variant() levanta)

# metadata/application/ports/artwork_resizer_port.py
class ArtworkResizerPort(ABC):
    async def resize(self, content: bytes, *, width: int) -> ResizedArtwork | None: ...
    # None = fonte não é mais larga; UnsupportedArtworkImageError = não decodifica

# metadata/application/services/artwork_variant_service.py
class ArtworkVariantService:
    async def open_original(self, key) -> StoredArtwork | None
    async def ensure(self, key, width) -> StoredArtwork | None   # variante | original | None
    async def pregenerate(self, key, kind, *, content, content_type) -> None  # best-effort
```

Pontos de toque: `artwork_variant.py` (novo), `artwork_key.py` (`variant`/`is_variant`), `artwork_resizer_port.py` + `pillow_artwork_resizer.py` (novos), `artwork_variant_service.py` (novo), `local_artwork_storage.py` (escrita atômica), `artwork_routes.py` (`?w=`), `containers/metadata.py` + `containers/main.py` (fiação), `artwork_mirror_job.py` (pré-geração por tipo de campo).

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-09-08 | Lucas | Criação inicial (Aceito, implementado junto) |
