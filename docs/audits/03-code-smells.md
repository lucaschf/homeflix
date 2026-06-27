# Auditoria 03 — Code Smells de Modelagem de Domínio

**Tipo:** READ-ONLY (nenhum código modificado).
**Metodologia:** skill `code-smell-review` (9 smells de modelagem/design de objetos).
**Âncora de severidade (HomeFlix):** o pior dano é **corrupção de dado persistido ou perda silenciosa** — valor que grava errado, não faz round-trip na leitura, ou cai em fallback sem erro.
**Escopo:** camadas de **domínio e aplicação** dos módulos `media`, `library`, `watch_progress`, `collections`, e a base `building_blocks` + `shared_kernel`. Cheiros estruturais (direção de import, fronteira de BC) foram deixados para a auditoria de arquitetura.

> Convenção: cada achado traz `arquivo:linha`, severidade, smell, confiança (0–1), e linhas de **O quê / Dano / Correção**.

---

## Resumo executivo

A base (`building_blocks` + `shared_kernel`) é a parte mais saudável e estabelece um padrão alto: VOs `frozen` validados na construção, `DomainModel.__init_subclass__` forçando invariantes no tipo, enums em todos os discriminadores. Os agregados de lifecycle (`MediaConflict`, `Season` intro-detection, `WatchProgress`, `CustomList`, `Library`) são **ricos e bem modelados** — não anêmicos.

O eixo de dano concentra-se em **um conceito de domínio ausente**: **metadados localizados** são carregados como `dict[str, dict[str, Any]]` com chaves mágicas, atravessam domínio e aplicação, são persistidos e relidos via `json_extract` — e **já causaram drift silencioso** (tagline perdida entre as variantes movie/series). É o achado mais grave e mais recorrente. Ao redor dele orbitam a regra de reconciliação de metadados anêmica (espalhada ~23×) e o flag `force: bool` que a parametriza.

### Contagem por módulo e severidade

| Módulo | Crítico | Alto | Médio | Baixo | Total |
|---|---:|---:|---:|---:|---:|
| media (domínio) | — | 1¹ | 3 | 3 | 7 |
| media (aplicação) | — | 2 | 4 | 1² | 7 |
| **localized metadata (cross-cutting domínio+aplicação)** | 1 | — | — | — | 1 |
| library | — | — | 1 | 1 | 2 |
| watch_progress | — | — | — | 1 | 1 |
| collections | — | — | 1 | — | 1 |
| building_blocks | — | — | 1 | — | 1 |
| shared_kernel | — | — | 1 | 1 | 2 |
| **Total** | **1** | **3** | **11** | **7** | **22** |

¹ O smell `lang: str` (ALTO) está contado em media-domínio; sua manifestação na aplicação (BAIXO²) é a mesma raiz.
² Não dupla-contado no total agregado de "localized" — ver achado cross-cutting.

---

## Achado cross-cutting (CRÍTICO)

### [CRÍTICO] Stringly-Typed + Anemic — metadados localizados como `dict[str, dict[str, Any]]`
**arquivo:linha (domínio):** `src/modules/media/domain/entities/movie.py:95`; `series.py:78`; `episode.py:67`; `season.py:57`
**arquivo:linha (aplicação):** `src/modules/media/application/use_cases/enrich_movie_metadata.py:344`; `enrich_series_metadata.py:260`; `_localized_metadata_helpers.py:45-61`
**smell:** Stringly-Typed Code + Primitive Obsession + Anemic Domain · **confiança: 0.9**
**Princípio:** estado ilegal representável + comportamento longe dos dados
- **O quê:** O provider entrega um `LocalizedTextFields` tipado; o use case o **achata** de volta para um dict aninhado com chaves de linguagem-string e chaves literais internas (`"title"`, `"synopsis"`, `"tagline"`, `"poster_path"`…). As quatro entidades de conteúdo o carregam e o leem com ~24 acessores `str(loc.get("title") or self.title.value)`. `LanguageCode`/`LanguageTag` existem em `shared_kernel` e são ignorados.
- **Dano (âncora HomeFlix):** o dict é **persistido e relido via SQL `json_extract(localized, lang)`** para ordenação/busca. Uma chave interna ou string de locale errada grava dado que **silenciosamente nunca faz round-trip na leitura** — corrupção de dado persistido sem erro. **Já ocorreu**: o docstring de `_localized_metadata_helpers` registra que as variantes movie/series divergiram (a de movie levava `tagline`, a de series o descartava). `Any` desliga o type checker exatamente sobre o dado persistido.
- **Correção:** Extract Value Object `LocalizedMetadata` (registro por-locale tipado, chaveado por `LanguageTag`) com um método `merge(other, policy)`; serializar **só** na borda de persistência. Centraliza chaves mágicas + fallback num único lugar.
- **Esforço:** Grande. **Candidato a ADR** ("Metadados localizados como Value Object").

---

## media — domínio

### [ALTO] Primitive Obsession — `lang: str = "en"` em todos os acessores localizados
**arquivo:linha:** `movie.py:131,136,141,146,154,168,180`; `series.py:106,111,116,124,138,150`; `episode.py:95,100`; `season.py:139,146`
**smell:** Primitive Obsession (VO ignorado) · **confiança: 0.85**
- **O quê:** O locale é `str` cru com default mágico `"en"` em ~20 assinaturas, embora `LanguageTag`/`LanguageCode` existam e estejam importáveis.
- **Dano:** Sem normalização na borda (`"pt-BR"` vs `"pt_BR"` vs `"PT-br"` não casa a chave localizada); um tag inválido retorna o fallback silenciosamente; o conceito "linguagem" da linguagem ubíqua se perde.
- **Correção:** Tipar o parâmetro como `LanguageTag` (ou coagir uma vez na borda). **Candidato a ADR** (locale como VO no catálogo).
- **Esforço:** Médio.

### [MÉDIO] Primitive Obsession — `confidence: float` sem limites
**arquivo:linha:** `src/modules/media/domain/entities/intro_detection_run.py:43` (`EpisodeDetectionResult.confidence`), `:85` (`min_confidence`)
**smell:** Primitive Obsession (invariante ignorada) · **confiança: 0.8**
- **O quê:** Confiança (`[0.0,1.0]`) é `float` irrestrito aqui, enquanto `IntroMarker`/`CreditsMarker` impõem `Field(ge=0.0, le=1.0)` no mesmo conceito.
- **Dano:** O agregado de auditoria pode persistir `confidence=1.7`/`-0.3` — a invariante protegida nos markers cai silenciosamente no registro que os explica; confiança corrupta em linhas voltadas ao operador.
- **Correção:** Extract VO `Confidence` (valida `[0,1]`) e reusar em markers + `EpisodeDetectionResult`. **Candidato a ADR** (aparece em 4+ lugares).
- **Esforço:** Médio.

### [MÉDIO] Data Clump + Primitive Obsession — pares candidato id/type em `MediaConflict`
**arquivo:linha:** `src/modules/media/domain/entities/media_conflict.py:111-114,122`
**smell:** Data Clumps + Primitive Obsession · **confiança: 0.7**
- **O quê:** `candidate_a_id: str` + `candidate_a_type: MediaType` (e o par `_b_`) andam sempre juntos por `detect()` (6+ params), `resolve()`, `loser_id()`, com ids como string crua.
- **Dano:** O conceito "referência de mídia = (id, type)" é implícito; fácil casar id com o type errado; ids escapam do VO de id prefixado.
- **Correção:** Introduce Parameter Object `ConflictCandidate(id, type)`.
- **Esforço:** Pequeno.

### [MÉDIO] Stringly-Typed — `ScanRun.summary: dict[str, Any]` com duas formas implícitas
**arquivo:linha:** `src/modules/media/domain/entities/scan_run.py:85` (uso `:105,114`)
**smell:** Stringly-Typed Code · **confiança: 0.6**
- **O quê:** Dict contador de chaves mágicas (`movies_created`, `enriched`…) cuja forma depende silenciosamente do `kind` (scan vs enrich).
- **Dano:** Contrato de chaves implícito e duplicado em escrita/leitura; contador renomeado ou chave do kind errado falha em silêncio numa linha de histórico persistida. (Trade-off "evitar tabela larga" é legítimo — mas as chaves mágicas são o custo.)
- **Correção:** Dois VOs contadores tipados (`ScanCounters`/`EnrichCounters`) ou união marcada, serializados na coluna única.
- **Esforço:** Médio.

### [BAIXO] Modelagem inconsistente — `directors`/`writers: list[str]` ao lado de `cast: list[CastMember]`
**arquivo:linha:** `src/modules/media/domain/entities/movie.py:82-83`
**smell:** Primitive Obsession (assimétrico) · **confiança: 0.55**
- **O quê:** Cast é VO rico (name/role/tmdb_id); directors/writers são strings cruas no mesmo agregado.
- **Dano:** Sem paridade "navegar por diretor"; colisão de homônimos. Baixo — metadado aditivo, não corrupção.
- **Correção:** VO `CrewMember` (ou generalizar `CastMember`) se navegação por crew for desejada; senão aceitar.
- **Esforço:** Pequeno.

### [BAIXO] Inconsistência — segundos `int` nos markers vs `float` em `EpisodeDetectionResult`
**arquivo:linha:** `intro_detection_run.py:42-43` (`start_seconds: float`, `end_seconds: float`) vs `intro_marker.py:51-52` / `credits_marker.py:52` (`int`)
**smell:** Primitive Obsession / inconsistência · **confiança: 0.5**
- **O quê:** O mesmo "offset em segundos" é `float` no registro de detecção e `int` no marker persistido; `(start_seconds, end_seconds)` recorre como time-span implícito.
- **Dano:** Mismatch de arredondamento/identidade ao comparar detecção vs marker gerado. Menor.
- **Correção:** Um tipo numérico para segundos no módulo; opcionalmente VO `TimeSpan`.
- **Esforço:** Pequeno.

### [BAIXO] Primitive Obsession (borderline / delegado) — `library_id: str`
**arquivo:linha:** `movie.py:58`, `series.py:52`, `scan_run.py:81`, candidatos em `media_conflict.py`
**smell:** Primitive Obsession · **confiança: 0.3**
- **O quê:** Referência à library dona como `str` cru, embora `shared_kernel/value_objects/library_id.py` (`LibraryId`) exista e seja importável.
- **Dano:** Baixo; documentado como trade-off de fronteira ADR-008. **Território da skill de arquitetura** — apontado, não analisado aqui.
- **Correção:** Avaliar `LibraryId` na fronteira se a auditoria de arquitetura concordar.
- **Esforço:** Médio.

---

## media — aplicação

### [ALTO] Anemic Domain + Shotgun Surgery — regra de reconciliação de metadados nos use cases
**arquivo:linha:** `enrich_movie_metadata.py:236-345`; `enrich_series_metadata.py:165-480`; `_localized_metadata_helpers.py:15-101`
**smell:** Anemic Domain Model + Shotgun Surgery · **confiança: 0.85**
- **O quê:** A regra "provider ⇄ entidade" (`if meta_val and (force or not entity_val): updates[...] = convert(meta_val)`) vive em funções de use case soltas, repetida ~23× (11 series, 12 movie). `Movie`/`Series` não têm `apply_metadata`/`merged_with` — só existe `with_enrichment_review_flagged`.
- **Dano:** **Já causou drift real** (tagline divergiu entre as cópias movie/series — registrado no docstring). Adicionar campo ou mudar o guard exige editar muitos pontos paralelos; omissões são silenciosas.
- **Correção:** Move Method — serviço de domínio `MetadataReconciler` ou `entity.merged_with(metadata, policy)` dono da regra "preencher-se-vazio" uma vez.
- **Esforço:** Grande.

### [ALTO] Boolean Blindness — `force: bool` enfiado em ~12 assinaturas de enrich
**arquivo:linha:** `enrich_movie_metadata.py:240,293,317`; `enrich_series_metadata.py:171,276,290,354,450`
**smell:** Boolean Blindness / Flag Argument · **confiança: 0.8**
- **O quê:** Um único `force` bifurca cada função apply em dois comportamentos (preencher-se-vazio vs sobrescrever) e é plumbado por ~12 funções.
- **Dano:** Cada call site reraciocina o que `force=True` significa; o split de comportamento é invisível na chamada (`_apply_episode_metadata(ep, meta, force=force)`).
- **Correção:** Replace Flag with enum (`MergePolicy.FILL_IF_EMPTY | OVERWRITE`) carregado pelo reconciler; casa com o achado anterior.
- **Esforço:** Médio.

### [MÉDIO] Stringly-Typed — sentinela `"Unknown"` de resolução no scan
**arquivo:linha:** `scan_media_directories.py:180` (`... or "Unknown"`), `:203` (`current.resolution.name == "Unknown"`)
**smell:** Stringly-Typed Code · **confiança: 0.75**
- **O quê:** Literal mágico `"Unknown"` constrói o VO `Resolution` na escrita, e o gate de re-probe compara `.name == "Unknown"` na leitura.
- **Dano:** A regra "resolução desconhecida?" está partida entre literal-na-escrita e compare-de-string-na-leitura; rename/typo quebra o gate silenciosamente (nunca re-probar, ou sempre).
- **Correção:** Constante `Resolution.UNKNOWN` + método `resolution.is_unknown()` no VO.
- **Esforço:** Pequeno.

### [MÉDIO] Temporal Coupling — validação descartada antes do update direto de coluna
**arquivo:linha:** `set_episode_intro.py:87`; `set_credits_marker.py:70`
**smell:** Temporal Coupling · **confiança: 0.7**
- **O quê:** Ambos chamam `entity.with_intro_marker(marker)` / `with_credits_marker(marker)` só pelo efeito de rodar a invariante "marker ≤ duração", **descartam a cópia imutável retornada**, e persistem via update de coluna separado (`update_episode_intro` / `update_creditable_credits`).
- **Dano:** A chamada de validação e a de persistência são independentes; nada força a primeira preceder a segunda. Se um edit futuro remover a linha 87/70, a checagem some mas a escrita ainda passa → marker fora de faixa persiste em silêncio.
- **Correção:** O método de repositório recebe a entidade/marker validado e impõe o bound, ou retornar-e-usar a cópia validada (caminho único).
- **Esforço:** Pequeno.

### [MÉDIO] Data Clump — par `(paths, by_path)` em cinco métodos do scan
**arquivo:linha:** `scan_media_directories.py:261,287,299,312,354`
**smell:** Data Clumps · **confiança: 0.7**
- **O quê:** O par `paths: list[str]` + `by_path: dict[str, ScannedFile]` viaja junto por cinco métodos; é "um grupo de variantes escaneadas".
- **Dano:** Long parameter lists; cada método refaz `by_path[path]`; adicionar dado de grupo toca os cinco.
- **Correção:** Parameter Object `VariantGroup(scanned_files)` com `paths`/lookup como métodos.
- **Esforço:** Pequeno.

### [MÉDIO] Feature Envy / Anemic — upsert de episódio/season fora do agregado
**arquivo:linha:** `scan_media_directories.py:554-575` (`_upsert_episode_in_season`, `_upsert_season_in_series`)
**smell:** Feature Envy / Anemic Domain · **confiança: 0.65**
- **O quê:** Funções de módulo fazem replace-or-append em `Season.episodes`/`Series.seasons`, mexendo em internos do agregado embora `Series` já tenha `with_season`/`get_season`.
- **Dano:** A invariante de coleção (sem episode_number duplicado por season) vive fora do agregado dono; ignora o vocabulário de upsert do próprio agregado.
- **Correção:** Move Method — `Season.with_episode_upserted(...)`, `Series.with_season_upserted(...)`.
- **Esforço:** Médio.

### [BAIXO] Primitive Obsession (read-path) — `lang: str` nos helpers de summary
**arquivo:linha:** `_movie_summary_helpers.py:14`; `_series_summary_helpers.py`; `list_by_genre.py`; `search_catalog.py` (14 arquivos)
**smell:** Primitive Obsession · **confiança: 0.5**
- **O quê:** `lang: str = "en"` cru no caminho de leitura/exibição; mesma raiz do achado ALTO do domínio.
- **Dano:** Baixo (display), mas é bypass uniforme de um VO existente; tag inválido cai no fallback em silêncio.
- **Correção:** Aceitar `LanguageCode`/`LanguageTag` na borda do use case; parsear a string crua uma vez na presentation.
- **Esforço:** Médio (junto com o ADR de locale).

---

## library

### [MÉDIO] Stringly-Typed (dict-as-struct) — `metadata_providers`/`settings` como `list[dict[str,Any]]`
**arquivo:linha:** `update_library.py:71-79`; DTOs `library_dtos.py:60-62,81-83`; espelhado em `create_library._build_settings`
**smell:** Stringly-Typed Code / Primitive Obsession · **confiança: 0.7**
- **O quê:** `metadata_providers: list[dict[str, Any]]` e `settings: dict[str, Any]` cruzam a fronteira da aplicação e são desempacotados por chave mágica, embora `MetadataProviderConfig` (VO real) já exista.
- **Dano:** Typo de chave ou mudança de shape só falha em runtime (`KeyError`); tratamento inconsistente — `p["provider"]` é obrigatório mas `p.get("priority",1)`/`p.get("enabled",True)` defaultam em silêncio, persistindo config errada-mas-válida; lógica duplicada entre create e update (risco de Shotgun Surgery).
- **Correção:** Tipar o campo do DTO de input como o VO estruturado (ou sub-model de request tipado), converter uma vez na borda.
- **Esforço:** Médio. (Recorre com o padrão de settings ADR-013/014 — se reaparecer em outros módulos, vira ADR "request models tipados na borda".)

### [BAIXO] Primitive Obsession — `scan_schedule: str` (cron) validado por regex frouxo
**arquivo:linha:** `library.py:66-69`
**smell:** Primitive Obsession · **confiança: 0.4**
- **O quê:** Expressão cron como `str | None` validada por `^(\S+\s+){4}\S+$`.
- **Dano:** Regex aceita cron semanticamente inválido (`99 99 99 99 99`); schedule ruim persiste e nunca dispara. Baixo (validado num só lugar).
- **Correção:** VO `CronExpression` validando faixas reais dos campos.
- **Esforço:** Pequeno.

---

## watch_progress

### [BAIXO] Stringly-Typed / sentinela sobrecarregada — `subtitle_track: int | None`
**arquivo:linha:** `watch_progress.py:64-65,112-113`
**smell:** Magic Value / sentinel overload · **confiança: 0.45**
- **O quê:** `subtitle_track` sobrecarrega dois sentidos — `None` = "não mudar", `-1` = "legenda off"; a convenção `-1` vive só num docstring.
- **Dano:** `0`/`None`/`-1` não distinguem "off" de "no-op" sem ler a prosa; valor errado persiste preferência ruim.
- **Correção:** Modelar preferência como VO/enum (`Off | Track(index)`), ou separar "clear" de "set".
- **Esforço:** Pequeno.

---

## collections

### [MÉDIO] Temporal Coupling — `item_count` denormalizado drifta dos itens reais
**arquivo:linha:** `custom_list.py:117,196-219`; conduzido por `add_item_to_custom_list.py:42-53` e `remove_item_from_custom_list.py:24-31`
**smell:** Temporal Coupling + invariante denormalizada · **confiança: 0.7**
- **O quê:** `item_count` é contador armazenado no agregado, mas os itens vivem numa coleção de repositório separada. Toda mutação exige **duas** chamadas coordenadas — `add_item()` + `increment_item_count()`/`update()` (e remove + decrement) — sem nada forçando o pareamento.
- **Dano:** Se algum caminho adicionar/remover sem a chamada de contador correspondente (ou reordenar as duas em falha), o count drifta → rejeição errada de `MAX_ITEMS_PER_LIST` ou total exibido errado. A invariante "lista cheia" é checada contra o contador, não as linhas reais.
- **Correção:** Derivar o count dos itens (`COUNT` query / agregado dono dos itens), ou unir add-item-e-bump num único método do agregado.
- **Esforço:** Médio.

---

## building_blocks

### [MÉDIO] Temporal Coupling — `with_updates` muta a fonte ao copiar
**arquivo:linha:** `entity.py:104-115` (`AggregateRoot.with_updates`)
**smell:** Temporal Coupling / mutação surpresa em API "imutável" · **confiança: 0.7**
- **O quê:** `with_updates` retorna uma nova instância mas **muta a fonte** — `self._events.clear()` esvazia os eventos pendentes do agregado antigo como efeito colateral da cópia (`new_instance._events = self._events[:]; self._events.clear()`).
- **Dano:** Numa entidade imutável, quem chama razoavelmente mantém a referência antiga; qualquer `old.pull_events()` após `with_updates` retorna vazio em silêncio → eventos de domínio (que dirigem persistência/integração) são perdidos sem erro. A ordem obrigatória (usar a instância retornada, nunca a antiga) não é forçada por nada.
- **Correção:** Tornar o hand-off de eventos explícito (coletor separado puxado no save) ou contrato hard return-only, para que a cópia imutável nunca mute a fonte.
- **Esforço:** Médio.

---

## shared_kernel

### [MÉDIO] Primitive Obsession + Stringly-Typed — formato composto de `episode_composite_id`
**arquivo:linha:** `episode_composite_id.py:31-33,59-83`
**smell:** Primitive Obsession + Stringly-Typed (duplicação de formato wire) · **confiança: 0.65**
- **O quê:** `series_id: str` (cru, não `SeriesId`); o formato `epi_ser_{id}_{S}_{E}` é montado/parseado por cirurgia de string (`media_id[4:]`, `rsplit("_",2)`), duplicando o esquema de prefixo que `media_id.py` já possui. `parse` retorna `None` em qualquer má-formação, engolindo "não é chave de episódio" vs "chave corrompida".
- **Dano:** O formato vive em dois lugares — mudar o esquema `epi_`/`ser_` exige caçar ambos. `None` silencioso deixa um id malformado-mas-presente cair num branch errado.
- **Correção:** Centralizar o formato composto junto de `parse_media_id`; tipar `series_id` como `SeriesId`; distinguir "não-episódio" de "malformado".
- **Esforço:** Médio.

### [BAIXO] Stringly-Typed — `codec: str` / `format: str` em tracks
**arquivo:linha:** `tracks.py:54,119`
**smell:** Stringly-Typed Code · **confiança: 0.4**
- **O quê:** `AudioTrack.codec` e `SubtitleTrack.format` são `str` aberta do ffprobe. `format` é efetivamente fechado (dirige `is_text_based`/`is_image_based`) mas continua string crua.
- **Dano:** Baixo — `format` typo'd reporta ambos `is_text_based` e `is_image_based` como `False` em vez de erro. Vocabulário de codec é genuinamente aberto.
- **Correção:** Opcional: promover `format` a enum `SubtitleFormat`; deixar `codec` como `str`. Tolerável.
- **Esforço:** Pequeno.

---

## Padrões recorrentes (candidatos a ADR)

1. **Locale como Value Object no catálogo** — `lang: str`/`"en"` aparece em ~20 acessores de entidade + 14 use cases, e o **dict `localized` não-tipado** é o achado CRÍTICO. Um ADR "Metadados localizados + locale como VO" + cards de migração incremental (Strangler Fig) cobre o eixo de maior dano.
2. **`Confidence` VO `[0,1]`** — bounds impostos em markers mas não em `EpisodeDetectionResult`/`min_confidence`; um VO único elimina o drift de invariante (4+ lugares).
3. **Request models tipados na borda** — `list[dict[str,Any]]` em library espelha o padrão de settings buckets (ADR-013/014); se recorrer, vira decisão de padrão, não card isolado.
4. **`MergePolicy` enum** substituindo `force: bool` — acompanha a extração do `MetadataReconciler`.

## O que está bom (calibra a confiança no resto)

- **`building_blocks`/`shared_kernel`** — a parte mais saudável. VO base `frozen` + validado; `DomainModel.__init_subclass__` força `extra="forbid"`/`validate_assignment` no tipo; `ExternalId`/`MediaType`/`Severity` como enums; `FilePath`/`LanguageCode`/`LanguageTag` ricos e validados; `SqlAlchemyUnitOfWork` usa `raise` em vez de `assert` (respeita `python -O`).
- **Agregados de lifecycle ricos** — `MediaConflict` (`detect()`/`resolve()`/`loser_id()` + 5 `model_validator`s tornando estados ilegais irrepresentáveis); `Season` intro-detection (transições `with_detection_*` + `_guard_transition`); `WatchProgress` (`_watched_ratio` como fonte única de verdade, transição COMPLETED interna); `CustomList`/`WatchlistItem` (`MAX_LISTS`/`MAX_ITEMS` via keyword-only não-bypassável, validador `media_id↔media_type`); `Library` (paths únicos/não-vazios + prioridades únicas no `model_validator`).
- **`IntroMarker`/`CreditsMarker`** — invariante cruzada `source`+`confidence` corretamente imposta; `with_*` dos markers checam "marker ≤ duração" dentro da entidade (Tell, Don't Ask).
- **DTOs/converters anêmicos por design** — `_movie_summary_helpers`/`_credits_media_helpers` corretamente finos; `resolve_media_conflict` delega a invariante ao agregado (`conflict.resolve(...)`); `streaming/thumbnail_vtt.py` com `SpriteLayout` VO + funções puras.
