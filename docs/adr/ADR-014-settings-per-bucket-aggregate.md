# ADR-014: Settings — Aggregate por Bucket (não Mega-Aggregate)

**Status:** Aceito
**Data:** 2026-05-21
**Deciders:** Lucas Cristovam
**Technical Story:** Fase 1 do ADR-013 — modelagem do agregado `Setting`

---

## Contexto

ADR-013 decidiu persistir tunables operacionais em uma tabela `app_settings` (key/value JSON), agrupando-os em cinco Value Objects coesos: `SchedulerConfig`, `ThumbnailBackfillConfig`, `IntroDetectionConfig`, `StreamingConfig`, `AvatarConfig`. Esse ADR não definiu como o domínio modela o **agregado** que cobre essas rows — restou a pergunta: um aggregate por bucket (5 instâncias, uma por VO) ou um único mega-aggregate `Settings` com 5 atributos tipados?

A pergunta importa porque define:

- A unidade de consistência: o que precisa estar válido junto?
- A unidade de auditoria: o que `updated_at`/`updated_by_user_id` cobrem?
- O comportamento sob concorrência: o que dois admins editando formulários diferentes disputam?
- A forma da tabela e do repositório.

Ambas as opções podem encostar no mesmo esquema de DB (uma row por VO), então a escolha é sobre **fronteiras de consistência no domínio**, não sobre persistência.

## Decisão

Cada bucket é seu próprio aggregate root: a entidade `Setting` é polimórfica sobre `SettingKey` (id) e `ConfigVO` (value union), e cada row de `app_settings` corresponde a uma instância independente. Não existe `Settings` mega-aggregate — "configuração do sistema" é o conjunto desses agregados, não um único objeto.

```python
class Setting(AggregateRoot[SettingKey]):
    id: SettingKey                 # ex. SettingKey.INTRO_DETECTION
    value: ConfigVO                # union dos 5 VOs; invariante: type(value) bate com id
    source: SettingSource
    updated_by_user_id: str | None
```

O polimorfismo é encapsulado: consumidores leem via `RuntimeSettings.intro_detection() -> IntroDetectionConfig` (tipo concreto), o `value: ConfigVO` união só aparece no mapper.

## Consequências

### Positivas

- **Casamento natural com a tabela**: `Setting.id == SettingKey == app_settings.key`. Mapper trivial: 1 row → 1 aggregate.
- **Audit independente por bucket**: editar `intro_detection` no admin toca apenas `source`/`updated_at`/`updated_by_user_id` daquela row. Mega-aggregate forçaria audit no nível do "tudo" (perda de granularidade) ou audit paralelo por atributo (duplicação).
- **Atomicidade por bucket = ausência de race entre forms diferentes**: dois admins editando `scheduler` e `intro_detection` simultaneamente escrevem rows distintas, sem disputar optimistic lock. Mega-aggregate produziria conflito espúrio mesmo em campos disjuntos.
- **Ausência parcial é natural**: row faltando = fallback para o `Field(default=...)` do VO. Mega-aggregate exigiria todos os 5 campos `Optional` na entidade ou hidratação com defaults na leitura, complicando invariantes.
- **Extensibilidade barata**: adicionar 6º bucket = `SettingKey.<NEW>` + novo VO + entrada no `_KEY_TO_VO_TYPE`. Sem migração de schema do agregado, sem risco de quebrar ORM por mudança de tipo de atributo.
- **Alinhamento com "small aggregates"** (Vaughn Vernon): cada VO modela uma capacidade independente; partilham tabela só por economia de infra, não por consistência conjunta.

### Negativas

- **Type-narrowing necessário em código que toca `Setting.value` diretamente**: a união `ConfigVO` exige `cast` ou `isinstance` para descer ao tipo concreto. Mitigado por (a) o atributo só ser tocado no mapper e (b) consumidores irem pelo facade tipado (`RuntimeSettings.scheduler()`).
- **Mais código de scaffold**: invariante `type(value) == _KEY_TO_VO_TYPE[id]` precisa de `model_validator` na entidade e no mapper. Mega-aggregate teria esse acoplamento implícito no schema.
- **Repository devolve coleção polimórfica**: `list_all() -> Sequence[Setting]` exige iteração + dispatch. Mega-aggregate devolveria um único objeto com atributos tipados.
- **`Setting.id` como `SettingKey` quebra a convenção `id: IdT | None = None` da `DomainEntity` base**: a entidade exige id não-nulo na construção (faz sentido — `Setting` sem chave é incoerente), mas diverge da heurística do framework.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Mapper esquece de adicionar um novo VO ao `_KEY_TO_VO_TYPE` | Baixa | Médio | Teste unitário parametrizado por `SettingKey` garante round-trip de todos os VOs |
| Consumer importa `Setting.value` direto e tropeça na união | Média | Baixo | `RuntimeSettings` é o único ponto de leitura suportado; documentar no facade para não usar o aggregate diretamente |
| Invariante `value matches key` esquecido em algum construtor | Baixa | Alto | `@model_validator(mode="after")` na entidade força o check em qualquer caminho de construção (incluindo `with_updates`) |
| Operador edita `app_settings` direto via SQL com chave válida mas JSON de outro VO | Baixa | Médio | Mapper valida no hidrate (`vo_type.model_validate(payload)`); row inválida levanta antes de chegar ao consumer; cache mantém último snapshot válido |

## Alternativas Consideradas

### 1. Mega-aggregate `Settings` com 5 atributos tipados

```python
class Settings(AggregateRoot):
    id: int = 1                              # singleton
    scheduler: SchedulerConfig
    thumbnail_backfill: ThumbnailBackfillConfig
    intro_detection: IntroDetectionConfig
    streaming: StreamingConfig
    avatar: AvatarConfig
    updated_at: datetime
    updated_by_user_id: str | None
```

Singleton-like, com type-safety direta nos consumers.

**Rejeitado porque:**

- **Audit chapado**: um único `updated_by` para o sistema todo apaga a granularidade que o admin precisa (saber quem mexeu em `intro_detection` ontem). Para preservar, teria que duplicar `source`/`updated_at`/`updated_by_user_id` por atributo — 15 colunas/campos só de metadata.
- **Conflito espúrio sob concorrência**: optimistic lock no nível do agregado faz duas edições simultâneas em buckets disjuntos colidirem. Em homelab single-user o risco é teórico, mas a Fase 2 do admin abre múltiplos forms, e o modelo precisa ser robusto.
- **Identity degenerada**: `Settings` aggregate sempre tem id=1 (ou é singleton implícito). A "natural key" da tabela (`SettingKey`) não tem reflexo no domínio — perde-se a correspondência 1:1 entre row e aggregate.
- **Persistência descasa**: ou se acha uma forma artificial de mapear 1 mega-aggregate → N rows (com identity manual), ou se vai pra 1 row enorme com todos os VOs serializados num JSON gigante (perdendo o ponto de granularidade de audit/atomicidade).
- **Fricção pra estender**: sexto bucket = alterar schema do mega-aggregate + migração de mapper + risco de quebrar ORM. O design atual: adicionar `SettingKey.<NEW>` + classe VO + entrada em dois dicts. Zero migração.

### 2. Mega-aggregate persistido como 1 row JSON única

Variante de (1) onde o mega-aggregate inteiro é serializado em uma row `app_settings(key='ALL', value_json={...})`.

**Rejeitado porque:** elimina a vantagem de "atomicidade por bucket" — escrever um campo escreve a row inteira, com todos os problemas de race da opção (1) **e** ainda perde a audit per-bucket. Junta o pior dos dois mundos.

### 3. Uma entidade tipada por bucket (5 classes irmãs, sem polimorfismo)

```python
class SchedulerSetting(AggregateRoot): value: SchedulerConfig; source: SettingSource; ...
class IntroDetectionSetting(AggregateRoot): value: IntroDetectionConfig; source: SettingSource; ...
# ... e assim por diante
```

Cada bucket vira uma classe concreta — sem union, sem `_KEY_TO_VO_TYPE`.

**Rejeitado porque:** explosão linear de boilerplate (5 entidades quase idênticas + 5 repositórios + 5 mappers, ou 1 repositório com 5 métodos `get_scheduler_setting`/`upsert_scheduler_setting`/...), sem ganho real. O polimorfismo via `SettingKey` enum + `ConfigVO` union já é validado em tempo de construção pelo `model_validator`; entidades irmãs só transfeririam essa validação pro tipo, ao custo de 5x mais código pra manter.

## Referências

- [ADR-013](./ADR-013-runtime-settings-db-backed.md) — decisão de persistir tunables em DB
- [ADR-007](./ADR-007-immutable-entities-with-convention.md) — `with_updates` que cada `Setting` herda
- Vernon, Vaughn — *Implementing Domain-Driven Design*, capítulo 10 ("Aggregates"), regra "Design Small Aggregates"

---

## Notas de Implementação

Invariante `value matches key` enforçado na entidade:

```python
_KEY_TO_VO_TYPE: ClassVar[dict[SettingKey, type]] = {
    SettingKey.SCHEDULER: SchedulerConfig,
    SettingKey.THUMBNAIL_BACKFILL: ThumbnailBackfillConfig,
    SettingKey.INTRO_DETECTION: IntroDetectionConfig,
    SettingKey.STREAMING: StreamingConfig,
    SettingKey.AVATAR: AvatarConfig,
}

@model_validator(mode="after")
def _validate_value_matches_key(self) -> Self:
    expected = self._KEY_TO_VO_TYPE[self.id]
    if not isinstance(self.value, expected):
        raise ValueError(...)
    return self
```

Consumer-facing API expõe tipo concreto, escondendo a união:

```python
class RuntimeSettings:
    async def scheduler(self) -> SchedulerConfig: ...
    async def intro_detection(self) -> IntroDetectionConfig: ...
    # ...
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-21 | Lucas Cristovam | Criação inicial |
