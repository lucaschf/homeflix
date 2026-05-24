# ADR-015: Scanner Deduplication by Content Identity

**Status:** Aceito
**Data:** 2026-05-23
**Deciders:** Lucas Cristovam
**Technical Story:** Discussão de design — reorganização de pastas, troca por remaster, duplicatas acidentais

---

## Contexto

O scanner atual deduplica mídia exclusivamente por `file_path` (UNIQUE constraint em `media_files.file_path`, ver `src/modules/media/application/use_cases/scan_media_directories.py:230-241`). Quando o mesmo conteúdo lógico aparece em paths diferentes — operador moveu o arquivo, substituiu por remaster (1080p substituindo 720p), ou baixou duplicata acidental por erro — o scanner cria entidade nova com `external_id` (`mov_xxx`) novo. Toda FK que apontava pra entidade antiga (watch progress, custom lists, intro markers, thumbnails enriquecidos) fica órfã. Não há cleanup de órfãos: entidades quebradas acumulam indefinidamente no DB.

Três cenários reais motivam revisitar isso:

1. **Reorganização do disco** — agrupar uma coleção temática (ex: filmes de um mesmo diretor ou franquia) espalhada em várias libraries numa pasta dedicada.
2. **Remaster swap** — substituir versão 720p por Blu-ray 1080p remasterizada.
3. **Duplicata acidental** — mesma mídia baixada de dois sources, ambos escaneados.

Os três quebram da mesma forma (perda de dados de usuário + acúmulo de entidades órfãs) porque compartilham a mesma causa raiz: o scanner trata `file_path` como identidade primária da mídia, sem nenhuma noção de identidade de conteúdo.

## Decisão

Introduzir **identidade de conteúdo** como camada secundária de deduplicação, executada **após o enriquecimento de metadata** (TMDB), e materializar colisões não-óbvias como aggregate `MediaConflict` em `modules/media/`, resolvido pelo operador via admin UI.

**Estratégia em duas camadas:**

1. **Identidade primária**: continua sendo `file_path` (não muda). Scanner cria/atualiza entidades pelo path, como hoje.
2. **Identidade de conteúdo (nova)**: após enrich popular `tmdb_id`, um passo de pós-processamento detecta colisões:
   - **Match key forte**: `tmdb_id` quando ambos os lados têm TMDB ID populado.
   - **Match key de fallback**: `(normalized_original_title, year)` quando um ou ambos os lados não têm TMDB match.

**Comportamento na colisão:**

| Situação | Comportamento |
|----------|---------------|
| Um dos lados está órfão (arquivo não existe no disco) **E** library root está saudável | **Auto-merge silencioso**: lado vivo absorve metadata e FK refs do órfão, órfão é deletado. Emite evento `MediaAutoMerged` pra audit. |
| Ambos vivos, runtime delta ≤ 5min **OU** ≤ 10% | Cria `MediaConflict` com `suggested_action = LIKELY_SAME_RELEASE`. |
| Ambos vivos, runtime delta > 5min **E** > 10% | Cria `MediaConflict` com `suggested_action = DIFFERENT_EDIT_SUSPECTED` (provável Director's Cut). |
| Library root inteira inacessível | Aborta scan dessa library, não classifica arquivos como órfãos. |

**Resolução de conflito (admin escolhe):**

1. **Merge mantendo ambas variantes** — usa `FileVariantMixin` (ADR-006): vencedor recebe variante do perdedor, perdedor é deletado, player escolhe variante em playback.
2. **Merge descartando variante perdedora** — vencedor mantém só seu arquivo; arquivo perdedor fica no disco mas é desreferenciado.
3. **Mark as distinct** — ambos sobrevivem; registro persistente impede futuras varreduras de re-flag esse par.

**Eventos de domínio:**

- `MediaConflictDetected` — emitido no pós-enrich quando colisão por identidade de conteúdo é encontrada (ambos vivos).
- `MediaAutoMerged` — emitido após auto-merge silencioso (órfão). Audit trail.
- `MediaConflictResolved` — emitido quando admin resolve via UI.

## Consequências

### Positivas

- Reorganização de pastas preserva watch progress, custom lists, intro markers, thumbnails — não exige novo endpoint dedicado de "move".
- Remaster swap flui naturalmente: scanner detecta colisão, admin escolhe "substituir" ou "manter ambas variantes".
- Duplicatas acidentais ficam visíveis em fila dedicada, em vez de poluir silenciosamente o catálogo.
- Reusa `FileVariantMixin` (ADR-006) — não inventa novo conceito de variante.
- Conflitos visíveis ≠ erro silencioso: operador sempre sabe o que aconteceu.

### Negativas

- Adiciona passo de pós-processamento no scan pipeline (custo extra por scan, função da contagem de entidades).
- Cria fluxo de UX adicional (admin monitora fila de conflitos); pra libraries grandes com muitas duplicatas iniciais, pode encher.
- "Identidade por `(original_title, year)`" tem casos extremos: traduções inconsistentes do título entre TMDB regions, filmes sem ano confiável. Fallback é falível por design — espera-se que TMDB ID resolva 90%+ dos casos.
- Auto-merge silencioso assume "arquivo não existe no disco" = "operador removeu intencionalmente". Falsa em caso de I/O transitório — mitigado pelo guard-rail de library-root-health, mas ainda é uma heurística.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Auto-merge dispara durante falha I/O transitória (HD desmontado) | Média | Alto (perda silenciosa de entidade) | Detectar "library root inteira inacessível" antes de tratar arquivos como órfãos; nesse caso, abortar scan da library |
| TMDB retorna mesmo `tmdb_id` para reedições não distinguíveis | Baixa | Médio | Heurística de runtime delta evita auto-merge nesse caso; operador resolve manualmente |
| Fila de conflitos enche pra biblioteca grande/desorganizada na primeira passada | Média | Baixo (cosmético) | UI permite bulk-resolve por critério (ex: "auto-merge todos com runtime delta < 1min") |
| Normalização de `original_title` divergente entre runs (acentos, caps, whitespace) | Baixa | Médio | Função canônica de normalização (lowercase + remove diacríticos + collapse whitespace) aplicada deterministicamente em todos os matches |

## Alternativas Consideradas

### 1. Manter status quo (file_path only)

Não muda nada. Reorganização exige delete + manual move + rescan, perdendo todas as FKs. Remaster idem. Duplicatas acumulam.

**Rejeitado porque:** problema real reportado pelo operador (coleções temáticas espalhadas em múltiplas libraries), e os três cenários compartilham a mesma causa raiz — vale resolver uma vez.

### 2. Dedup automático por TMDB ID, sem fila de conflitos

Scanner mescla toda colisão por TMDB ID silenciosamente.

**Rejeitado porque:** Director's Cut vs Theatrical compartilham TMDB ID em vários filmes — auto-merge produziria fusões incorretas silenciosas, difíceis de detectar depois.

### 3. Endpoint dedicado de "repoint" (manual move + path update via API)

Operador move arquivos manualmente, chama endpoint passando `media_id` + novo `file_path`. Backend valida e atualiza entidade sem rescannear.

**Rejeitado porque:** resolve só o cenário "move", não cobre remaster nem duplicata. Adiciona um endpoint específico em vez de tratar a causa raiz. Pode ser implementado depois como atalho de UX se a fila de conflitos for friccional pro caso de move.

### 4. Content hash (SHA-256) como identidade

Computar hash de cada arquivo durante scan, usar como identity.

**Rejeitado porque:** custo computacional altíssimo (hash de filme inteiro), e remaster não compartilharia hash com versão antiga mesmo sendo "o mesmo filme" logicamente — não resolve o caso de uso principal.

## Referências

- [ADR-006](./ADR-006-media-file-variants.md) — Variantes de Arquivo de Mídia (FileVariantMixin reusado no merge)
- [ADR-008](./ADR-008-screaming-architecture.md) — Screaming Architecture (MediaConflict em `modules/media/`)
- [ADR-013](./ADR-013-runtime-settings-db-backed.md) — Runtime settings persistidos (threshold de runtime delta pode ser tunável via mesmo padrão)
- TMDB API — `/movie/{id}` retorna `original_title`, `release_date`, `runtime`

---

## Notas de Implementação

Implementação sugerida em fases incrementais:

**Fase 1 — Detecção (sem ação automática)**
- `MediaConflict` aggregate + repository
- Endpoint admin `GET /api/v1/admin/conflicts`
- Hook pós-enrich emite `MediaConflictDetected` e cria `MediaConflict`
- Auto-merge ainda não — tudo vai pra fila

**Fase 2 — Admin UI + manual resolve**
- Página `/admin/conflicts` em homeflix-web
- Ações: merge-with-variants, merge-replace, mark-distinct
- Endpoint `POST /api/v1/admin/conflicts/{id}/resolve`

**Fase 3 — Auto-merge silencioso (órfão + library saudável)**
- Health check da library root antes de classificar como órfão
- Path "orphan + healthy library" → auto-merge + `MediaAutoMerged`
- Audit trail visível em UI separada da fila

**Fase 4 (opcional) — Bulk resolve + tunables**
- Threshold de runtime delta tunável via RuntimeSettings (ADR-013), bucket novo `scan_dedup`
- Bulk resolve por critério na UI

```python
# Esboço (modules/media/domain/entities/media_conflict.py)
class MediaConflict(AggregateRoot):
    """Pending content-identity conflict detected by the scanner."""

    id: MediaConflictId
    detected_at: datetime
    candidate_a_id: MovieId | SeriesId
    candidate_b_id: MovieId | SeriesId
    match_reason: MatchReason  # TMDB_ID | TITLE_YEAR_FALLBACK
    runtime_delta_minutes: float | None
    suggested_action: SuggestedAction  # LIKELY_SAME | DIFFERENT_EDIT_SUSPECTED
    resolved_at: datetime | None = None
    resolution: ResolutionAction | None = None  # MERGE_KEEP_BOTH | MERGE_REPLACE | MARK_DISTINCT
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-23 | Lucas Cristovam | Criação inicial — Proposto |
| 2026-05-24 | Lucas Cristovam | Fases 1–4 implementadas e enviadas — Aceito. Bulk resolve entregue como **mark-distinct only** (sem critério `min_runtime_delta`); merge segue 1-a-1. |
