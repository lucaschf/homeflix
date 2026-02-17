# ADR-007: Immutable Entities with `with_*` Convention

**Status:** Aceito
**Data:** 2026-02-17
**Deciders:** Lucas
**Technical Story:** Alinhar entidades com o padrão de imutabilidade já usado em Value Objects

---

## Contexto

Domain entities (Movie, Series, Season, Episode, Library) eram **mutáveis** — métodos como `add_genre()`, `add_season()` alteravam o estado interno in-place sem retornar nada. Isso criava uma classe de bugs onde chamadores esqueciam que a operação era void e não reatribuíam o resultado:

```python
# Bug silencioso: add_genre retorna None, movie não muda na referência do chamador
movie.add_genre("Sci-Fi")  # muta internamente, mas fácil esquecer o padrão
```

Value Objects já usavam `frozen=True` desde ADR-001. Entities precisavam seguir o mesmo padrão para consistência arquitetural.

Além disso, `DomainEntity.touch()` (que atualizava `updated_at` in-place) era incompatível com imutabilidade e representava acoplamento desnecessário — cada método `with_*` agora gerencia o timestamp explicitamente.

## Decisão

Nós iremos:

1. **Tornar `DomainEntity` frozen** adicionando `frozen=True` ao `model_config` da classe base, eliminando a necessidade de repetir a configuração em cada entidade concreta.

2. **Remover `touch()`** de `DomainEntity` — `with_updates()` agora atualiza `updated_at` automaticamente via `setdefault`.

3. **`with_updates()` faz bump automático de `updated_at`** — usa `kwargs.setdefault("updated_at", utc_now())` para que chamadores não precisem lembrar de passar o timestamp. Valores explícitos ainda são respeitados.

4. **Adotar a convenção `with_*`/`without_*`** para todos os métodos que modificam estado, retornando `Self`:
   - `Movie.add_genre()` → `Movie.with_genre()` → retorna nova instância, ou `self` para duplicata
   - `Series.add_season()` → `Series.with_season()` → retorna nova instância, ou `self` para duplicata
   - `Season.add_episode()` → `Season.with_episode()` → retorna nova instância, ou `self` para duplicata
   - `Library.add_path()` → `Library.with_path()` → retorna nova instância (erro para duplicata)
   - `Library.remove_path()` → `Library.without_path()` → retorna nova instância, ou `self` se não encontrado

## Consequências

### Positivas

- **Elimina bugs de mutação silenciosa** — chamadores são forçados a capturar o retorno
- **Consistência** — Entities e Value Objects seguem o mesmo padrão frozen
- **Thread-safety** — objetos imutáveis são inherentemente thread-safe
- **Código auto-documentado** — `with_genre()` torna claro que retorna uma nova instância
- **Menos duplicação de config** — `model_config` definido uma vez em `DomainEntity`, herdado por todas as entidades

### Negativas

- **Alocação extra** — cada operação cria um novo objeto (impacto negligível para domain objects)
- **Verbosidade no chamador** — requer reatribuição: `movie = movie.with_genre("Sci-Fi")`

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Performance com muitas operações encadeadas | Baixa | Baixo | Domain objects são leves; operações em batch são raras |
| PrivateAttr (`_events`) não funcionar com frozen | Baixa | Alto | Testado — PrivateAttr NÃO é afetado por frozen=True |

## Alternativas Consideradas

### 1. Manter entidades mutáveis com retorno de `Self`

Mudar a assinatura de `add_genre() -> None` para `add_genre() -> Self` retornando `self`, mantendo mutabilidade.

**Rejeitado porque:** Não resolve o problema — o chamador ainda pode ignorar o retorno e o objeto teria sido mutado silenciosamente. Frozen + `with_*` é a única forma de tornar o padrão obrigatório.

### 2. Usar `@dataclass(frozen=True)` em vez de Pydantic

Abandonar Pydantic para entidades e usar dataclasses frozen.

**Rejeitado porque:** Perderíamos validação automática, conversão de tipos, e model_validate — benefícios centrais de ADR-001.

## Referências

- ADR-001: Pydantic para Domain Models
- [Pydantic v2 — Frozen Models](https://docs.pydantic.dev/latest/concepts/config/#frozen)
- Domain-Driven Design — Entity immutability patterns

---

## Notas de Implementação

Padrão para métodos `with_*` (`with_updates` faz bump automático de `updated_at`):

```python
def with_genre(self, genre: Genre | str) -> Self:
    if isinstance(genre, str):
        genre = Genre(genre)
    if genre in self.genres:
        return self  # no-op para duplicatas
    return self.with_updates(genres=[*self.genres, genre])
```

Padrão para métodos `without_*`:

```python
def without_path(self, path: FilePath | str) -> Self:
    if isinstance(path, str):
        path = FilePath(path)
    if path not in self.paths:
        return self  # no-op se não encontrado
    if len(self.paths) == 1:
        raise ValueError("Cannot remove the last path")
    return self.with_updates(paths=[p for p in self.paths if p != path])
```

Todos os métodos `with_*`/`without_*` devem retornar `self` quando não há mudança (duplicata ou item não encontrado), garantindo comportamento uniforme.

## Historico de Revisoes

| Data | Autor | Mudanca |
|------|-------|---------|
| 2026-02-17 | Lucas | Criacao inicial |
