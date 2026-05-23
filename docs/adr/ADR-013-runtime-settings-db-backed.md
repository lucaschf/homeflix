# ADR-013: Runtime settings persistidos em banco para tunables operacionais

**Status:** Aceito
**Data:** 2026-05-21
**Deciders:** Lucas Cristovam
**Technical Story:** Planejamento 2026-05-21 de exposição de tunables operacionais via admin panel.

---

## Contexto

O arquivo `.env` hoje carrega três classes distintas de configuração misturadas: bootstrap (`DATABASE_URL`, `SECRET_KEY`, `HOST`, `PORT`, `ALLOWED_ORIGINS`), secrets de terceiros (`TMDB_API_KEY`, `OMDB_API_KEY`) e tunables operacionais (`SCHEDULER_*`, `THUMBNAIL_BACKFILL_*`, `INTRO_DETECTION_*`, `FFMPEG_THREADS`, `HLS_CACHE_MAX_SIZE_MB`, `AVATAR_*`).

Os tunables operacionais mudam ao longo do tempo conforme o operador calibra o sistema: `FFMPEG_THREADS` precisa ser ajustável para capear CPU no servidor (auditoria HLS de 2026-05-15 recomenda exatamente esse knob); os parâmetros de `INTRO_DETECTION_*` foram calibrados em PRs sucessivos conforme detecções reais expuseram limites do algoritmo; jobs como `THUMBNAIL_BACKFILL_ENABLED` precisam poder ser ligados/desligados sem deploy. Cada alteração hoje exige editar `.env` no host e reiniciar o processo. Não há audit (quem mudou, quando), nem UI, nem validação além do startup do Pydantic.

O `/admin` panel já está em produção desde a rollout de PR #154, com pattern estabelecido para superfícies administrativas (`admin_user_routes`, scan runs, intro editor). Estender essa superfície para tunables operacionais é a próxima evolução natural.

Secrets de terceiros e bootstrap ficam fora do escopo deste ADR: secrets exigem cifragem em repouso e mascaramento na UI (ADR próprio quando relevante); bootstrap tem dependência cíclica (`DATABASE_URL` precisa ser lido antes de qualquer conexão com DB).

## Decisão

Tunables operacionais são persistidos em uma tabela `app_settings` no banco de dados, agrupados em Value Objects coesos por domínio (intro detection, thumbnail backfill, scheduler, streaming, avatar) e expostos via admin panel para edição em runtime. O `.env` deixa de ser consultado para esses knobs — bootstrap e secrets de terceiros continuam lá, mas os tunables operacionais saem completamente.

**Agrupamento em Value Objects:** os tunables relacionados são modelados como VOs Pydantic coesos no domínio do BC `settings/`, em vez de campos avulsos no `Settings`. Os VOs definidos:

- `SchedulerConfig` — `enabled`, `reconcile_interval_minutes`.
- `ThumbnailBackfillConfig` — `enabled`, `batch_size`, `interval_minutes`, `subdir`.
- `IntroDetectionConfig` — `enabled`, `batch_size`, `interval_minutes`, `audio_window_seconds`, `min_confidence`, `max_hash_hamming`, `tolerance_hashes`, `min_intro_seconds`, `max_intro_seconds`.
- `StreamingConfig` — `ffmpeg_threads`, `hls_cache_max_size_mb`.
- `AvatarConfig` — `storage_subdir`, `max_size_mb`, `size_pixels`.

Cada VO recebe um `model_validator` para invariantes cross-field (ex.: `IntroDetectionConfig` valida `min_intro_seconds < max_intro_seconds`, hoje uma invariante implícita não-verificada). O `Settings` expõe esses VOs como atributos aninhados — consumers passam a ler `settings.intro_detection.min_confidence` no lugar de `settings.intro_detection_min_confidence`.

**Esquema da tabela** (single-table key/value JSON, uma row por VO):

```sql
CREATE TABLE app_settings (
    key                TEXT PRIMARY KEY,   -- nome do VO ('intro_detection', 'scheduler', ...)
    value_json         TEXT NOT NULL,      -- VO serializado completo
    source             TEXT NOT NULL,      -- 'migration_seed' | 'admin' | 'sql_override'
    updated_at         TIMESTAMP NOT NULL,
    updated_by_user_id TEXT                -- NULL quando source='migration_seed'
);
```

Cada row contém um VO inteiro serializado. Exemplo conceitual:

```json
{
  "key": "intro_detection",
  "value_json": {
    "enabled": true,
    "batch_size": 1,
    "interval_minutes": 30,
    "audio_window_seconds": 600,
    "min_confidence": 0.7,
    "max_hash_hamming": 10,
    "tolerance_hashes": 2,
    "min_intro_seconds": 5.0,
    "max_intro_seconds": 120.0
  },
  "source": "admin",
  "updated_at": "2026-05-21T14:32:11Z",
  "updated_by_user_id": "usr_abc123"
}
```

Editar qualquer campo via UI reescreve o row inteiro do VO; `updated_by_user_id` registra quem submeteu o form, granularidade alinhada ao que o operador realmente fez.

**Camada de acesso:** novo BC `src/modules/settings/` (segue ADR-008) com:

- `domain/value_objects/` — VOs Pydantic listados acima, seguindo ADR-001 e ADR-007 (imutáveis, com `model_validator` para invariantes cross-field).
- `domain/entities/setting.py` — agregado `Setting(key, value_vo, source, updated_at, updated_by_user_id)`, polimórfico sobre o tipo de VO.
- `domain/repositories/setting_repository.py` — ABC.
- `application/services/runtime_settings.py` — facade snapshot-pattern: carrega todos os VOs do DB, monta um `Settings` aninhado em memória, expõe via `current()` com TTL.
- `infrastructure/persistence/` — model, mapper, repository SQLAlchemy.
- `presentation/routes/admin_settings_routes.py` — endpoints CRUD agrupados por VO (`PATCH /admin/settings/intro-detection`, `PATCH /admin/settings/streaming`, etc.).

**Precedência (resolução de valor):** DB > default do Pydantic Field. O `.env` deixa de ser consultado para campos migrados.

- Row presente no DB → DB ganha.
- Row ausente no DB → cai no default declarado em `Settings` (`Field(default=...)`).

Na primeira execução após o deploy desta mudança, uma migration one-time lê valores existentes nas env vars correspondentes e popula `app_settings` com `source='migration_seed'`; valores ausentes ficam ausentes (caem no default). Em deploys subsequentes, definir essas env vars no shell ou no `.env` não tem efeito — o startup loga warning identificando cada variável obsoleta para que o operador a remova do arquivo.

**Cache:** em memória, TTL de 30s. Endpoint admin de write invalida cache imediatamente. Não usar pub-sub neste estágio — complexidade desproporcional para single-instance.

**Validação de write:** reaproveita as constraints do `Settings` (`Field(ge=..., le=...)`) via reflection — uma fonte de verdade para limites.

**Escopo de campos migrados** (Fases 2 e 3 do rollout, agrupados por VO; campos renomeados para remover prefixo redundante):

| VO | Campos no VO |
|---|---|
| `SchedulerConfig` | `enabled`, `reconcile_interval_minutes` |
| `ThumbnailBackfillConfig` | `enabled`, `batch_size`, `interval_minutes`, `subdir` |
| `IntroDetectionConfig` | `enabled`, `batch_size`, `interval_minutes`, `audio_window_seconds`, `min_confidence`, `max_hash_hamming`, `tolerance_hashes`, `min_intro_seconds`, `max_intro_seconds` |
| `StreamingConfig` | `ffmpeg_threads`, `hls_cache_max_size_mb` |
| `AvatarConfig` | `storage_subdir`, `max_size_mb`, `size_pixels` |

**Rollout em 5 PRs sequenciais:** ADR (este) → infra core (tabela + facade + testes, sem migrar consumers) → migrar jobs (scheduler/backfill/intro) → migrar streaming/avatar → admin UI.

## Consequências

### Positivas

- Operador altera tunables via UI sem restart; efeito propaga em até 30s (TTL do cache).
- Audit nativo: `updated_at` + `updated_by_user_id` na própria tabela; coluna `source` distingue valor da migração inicial vs. edição no admin vs. override SQL manual.
- `.env` volta a ser apenas bootstrap + secrets de terceiros — superfície de configuração mais limpa, com propósito único.
- Resolução de valor tem só dois caminhos (DB ou default no código), eliminando a confusão "será que o `.env` está sobrescrevendo isso?".
- Validação aproveita Pydantic `Field` constraints existentes — sem duplicar `ge`/`le` na camada de write.
- Pattern reutilizável: novos tunables futuros entram só adicionando o campo no `Settings` e expondo no admin UI, sem nova migration.

### Negativas

- Nova camada (`RuntimeSettings`, repository, cache, rotas admin) — código adicional para manter.
- Perde tipagem SQL (`value_json` é texto). Recuperada na aplicação via Pydantic ao ler/escrever.
- Cache stale window de até 30s — não-determinístico em testes que dependem de mudança de setting; testes precisam usar API de flush.
- Operador perde o escape hatch "edita `.env` + restart" para campos migrados. Substituído por `UPDATE app_settings SET value_json=...` direto, documentado no runbook.
- Knobs hot-path (`ffmpeg_threads`, lido a cada invocação de ffmpeg) ganham um lookup em dict cacheado — overhead esperado < 1μs, mas precisa ser medido na Fase 3.
- Customização "factory" por deploy via env var (ex.: deploy A com `INTRO_DETECTION_ENABLED=true` default, deploy B com `false`) deixa de ser possível — exige code change no `Field(default=...)` ou seed via SQL. Aceito porque o HomeFlix é single-instance homelab, onde esse caso quase nunca aparece.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Cache stale durante incident (operador alterou knob mas jobs ainda usam valor antigo) | Média | Médio | TTL de 30s; endpoint de write invalida cache imediatamente; runbook documenta tempo de propagação |
| Migração de campo quebra consumer que ainda lê de `Settings` direto | Média | Alto | Manter campos no Pydantic `Settings` como fallback durante todas as fases |
| DB lento/indisponível bloqueia leitura de setting em hot path | Baixa | Alto | Cache mantém último valor válido entre TTLs; em cache miss + DB down, cai no default do Pydantic e loga warning |
| Operador grava valor inválido via SQL direto (bypass UI) | Baixa | Médio | Facade `RuntimeSettings` valida na leitura (`Field` constraints); valor inválido é descartado, default é usado, warning é logado |
| Regressão silenciosa de performance no hot path (ffmpeg invocations) | Baixa | Médio | Fase 3 inclui benchmark antes/depois de start-de-stream HLS; rollback para snapshot na construção do `HlsService` se houver regressão |
| Operador edita env var antiga esperando override e a mudança é ignorada silenciosamente | Média | Baixo | Startup loga warning identificando cada env var obsoleta com referência a este ADR; `.env.example` removido das seções migradas |

## Alternativas Consideradas

### 1. Manter tudo em `.env` (status quo)

Operador edita arquivo no host e reinicia processo. Funciona, é familiar e segue 12-factor.

**Rejeitado porque:** não escala com o crescimento do admin panel. UX inconsistente — algumas configurações (libraries, usuários, scan runs) são editáveis na UI, outras exigem SSH no host. Restart é fricção alta para mudanças triviais como ajustar `INTRO_DETECTION_MIN_CONFIDENCE`. Sem audit de "quem mudou o quê".

### 2. Tabela por bucket (uma tabela para scheduler, outra para intro detection, etc.)

Cada bucket vira uma tabela com colunas tipadas (`scheduler_settings.enabled BOOLEAN`, etc.). Recupera tipagem SQL.

**Rejeitado porque:** inflar migrations a cada novo tunable. Pior ratio de código/utilidade — 5 tabelas para ~17 campos, cada uma com seu repository, mapper, model. Acoplamento desnecessário entre tunables que só compartilham o domínio textual ("backfill"), não comportamento.

### 3. External config tool (Consul, etcd, AWS AppConfig)

Ferramentas dedicadas a config dinâmica e distribuída.

**Rejeitado porque:** overkill para um homelab single-instance. Adiciona dependência operacional substancial (outro processo para rodar, monitorar, fazer backup). Toda capacidade que precisamos cabe em uma tabela SQLite.

### 4. Precedência `.env` > DB > default

Convenção 12-factor — variável de ambiente sempre ganha.

**Rejeitado porque:** quebra o contrato da UI. Se o operador altera um knob no admin panel mas `.env` tem o valor antigo esquecido de um debug session, a mudança "não faz nada" e a UI mente. 12-factor presume config estática de deploy; aqui o contrato é runtime-mutable, então o vetor primário (admin panel) tem que mandar.

### 5. Manter `.env` como seed-on-first-read (versão híbrida `DB > .env (seed) > default`)

Versão anterior desta proposta: na ausência de row no DB, `.env` é lido e o valor persistido com `source='env_seed'`. Depois disso, `.env` é ignorado para aquela key. Preserva customização "factory" por deploy via env var.

**Rejeitado porque:** adiciona uma terceira camada de configuração no caminho de resolução para ganho marginal num contexto single-instance homelab. O caso de uso ("deploy A liga `INTRO_DETECTION_ENABLED` por default, deploy B não") quase nunca aparece — quando aparece, o operador abre a UI e ajusta. A complexidade extra (lógica de seed, semântica de "veio do `.env` mas o `.env` mudou depois", coluna `source='env_seed'` órfã após primeira leitura) não se paga.

### 6. Manter campos flat em `Settings` (sem agrupar em VOs)

Persistir cada tunable como uma row separada em `app_settings` (`key='intro_detection_min_confidence'`, `value_json=0.7`), mantendo a estrutura plana atual do Pydantic `Settings`. Granularidade fina no audit (quem mudou *esse* campo específico).

**Rejeitado porque:** os tunables relacionados não fazem sentido isolados — `min_confidence` sem o contexto dos outros parâmetros de intro detection é ruído semântico. Agrupar em VOs entrega (a) coesão (cada VO modela uma responsabilidade do sistema), (b) validação cross-field explícita (ex.: `min_intro_seconds < max_intro_seconds`), (c) atomicidade natural no admin (operador edita "o form de intro detection" e não campos individuais), (d) alinhamento com ADR-001 e ADR-007. A tabela passa de ~17 rows para ~5; o audit per-bucket reflete a unidade real de mudança feita pelo operador, não fragmenta um único form em N entradas.

## Referências

- ADR-005: Library como Entidade de Configuração (precedente de "config como dado de domínio")
- ADR-007: Entidades Imutáveis com Convenção `with_*`
- ADR-008: Screaming Architecture com Módulos (justifica o novo BC `modules/settings/`)
- ADR-009: Cross-BC Read Ports (caso outros BCs precisem ler settings via port)
- ADR-011: Authentication Strategy (escopo dos campos `session_*` permanece aqui)
- `docs/standards/api-response-standard-rest-v3.md`
- Auditoria de pico de CPU no startup do HLS (2026-05-15, recomendação: capear `FFMPEG_THREADS`)

---

## Notas de Implementação

Esboço da facade:

```python
# src/modules/settings/application/services/runtime_settings.py
class RuntimeSettings:
    """Mirrors Settings with DB-backed overrides for grouped config VOs.

    Each row in app_settings holds an entire config VO (IntroDetectionConfig,
    ThumbnailBackfillConfig, etc.) serialized as JSON. The Pydantic VO
    validates types and cross-field invariants on every load — invalid
    state in the DB raises on refresh, before any consumer observes it.
    """

    def __init__(
        self,
        repository: SettingRepository,
        defaults: Settings,
        cache_ttl_seconds: int = 30,
    ) -> None:
        self._repo = repository
        self._defaults = defaults
        self._snapshot: Settings = defaults
        self._snapshot_loaded_at: float = 0.0
        self._ttl = cache_ttl_seconds

    async def refresh(self) -> None:
        """Rebuild snapshot from DB. Each row is a full VO; merged into Settings."""
        rows = await self._repo.list_all()
        # e.g. {"intro_detection": {"enabled": True, ...}, "streaming": {...}}
        overrides = {row.key: row.value for row in rows}
        self._snapshot = self._defaults.model_copy(update=overrides)
        self._snapshot_loaded_at = time.monotonic()

    async def current(self) -> Settings:
        """Return current snapshot, refreshing if TTL expired."""
        if time.monotonic() - self._snapshot_loaded_at > self._ttl:
            await self.refresh()
        return self._snapshot

    async def invalidate(self) -> None:
        """Force refresh on next read. Called by admin write endpoints."""
        self._snapshot_loaded_at = 0.0
```

Exemplo de uso em consumer (`intro_detection_job.py`):

```python
# Antes (Settings flat, .env autoritativo)
threshold = self._settings.intro_detection_min_confidence

# Depois (Settings aninhado em VOs, snapshot do RuntimeSettings)
settings = await self._runtime_settings.current()
threshold = settings.intro_detection.min_confidence
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-21 | Lucas Cristovam | Criação inicial |
| 2026-05-23 | Lucas Cristovam | Rollout completo — backend nas PRs #221 (foundation), #222 (scheduler/backfill/intro), #223 (streaming/avatar), #224 (admin routes); frontend em homeflix-web#156 (/admin/system/settings). Status: Aceito. |
