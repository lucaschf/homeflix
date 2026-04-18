# ADR-009: Ports de leitura entre Bounded Contexts

**Status:** Aceito
**Data:** 2026-04-18
**Deciders:** Lucas Cristovam
**Technical Story:** Auditoria Clean Architecture + DDD (Fase 1 do plano em `docs/clean-architecture-refactoring-plan.md`).

---

## Contexto

Até aqui, os módulos `library`, `collections` e `watch_progress` importavam diretamente repositórios e entidades do módulo `media` para compor suas respostas (contagens por path, título/poster de itens, árvore de seasons/episodes). O módulo `media` fazia o mesmo na direção oposta, importando `WatchProgressRepository` para anexar progresso no payload de `GET /series/{id}`.

Isso viola a regra do CLAUDE.md:

> Módulos não importam entre si (comunicação futura via integration events)

E quebra o isolamento de Bounded Contexts: qualquer mudança em repositórios ou entidades do `media` arrastava 3 outros BCs; qualquer mudança em `WatchProgress` quebrava o `media`. A linguagem ubíqua também vazava — VOs como `MovieId` / `SeriesId` circulavam em código que nem é do Media BC.

Escrever dados cruzados entre BCs é problema maior (eventual consistency, integration events) e fica fora do escopo deste ADR. **Leitura cruzada**, porém, é necessidade recorrente — a UI exige telas que misturam dados de vários BCs.

## Decisão

Toda leitura que atravessa a fronteira de um Bounded Context é feita através de um **port local** no BC consumidor. O adapter que implementa a port vive na camada de infraestrutura do consumidor e é o **único** ponto que importa do domínio do BC provedor.

Estrutura para cada par (consumidor, provedor):

```
src/modules/<consumer>/
├── application/
│   └── ports/
│       └── <provider>_lookup_port.py    # Interface + DTOs do contrato
└── infrastructure/
    └── acl/
        └── <provider>_lookup_adapter.py # Implementa a port usando repos do provider
```

Regras:

1. **DTOs da port pertencem ao consumidor.** Cada BC define o shape que precisa — não se reutiliza o DTO de outro BC nem se promove o shape para `shared_kernel` sem evidência concreta de que são iguais em todos os usos.
2. **Nomes da port refletem a linguagem do consumidor.** Não é "MovieRepository" — é "MediaLookupPort" do ponto de vista do consumidor.
3. **Adapter é o único import cross-BC domain.** Use case só conhece a port local.
4. **ACL vive sempre no consumidor**, nunca no provedor. O provedor não deve saber quem o consome.
5. **Port por direção.** Se A→B e B→A, são ports separadas, uma em cada BC.
6. **O wiring fica na composition root** (`src/config/containers/*.py`). O container do consumidor declara o adapter como `providers.Factory(...)`. Quando possível (não houver ciclo de declaração), receber o repo do provider via `providers.Dependency()` vindo do `main.py` é preferível a importar a implementação concreta do provider no container do consumidor.

## Consequências

### Positivas

- BCs viram unidades substituíveis: mexer em `media.domain` não arrasta consumidores desde que a port (e seus DTOs) permaneçam estáveis.
- Testes de use case ficam mais enxutos: só mockam a port local, não o repositório completo do outro BC com todos os seus métodos.
- Adiciona um ponto natural para trocar repositório síncrono por fila/RPC/integration events quando a leitura cruzada precisar virar assíncrona.
- Torna explícito em review o contrato mínimo que um BC precisa do outro — qualquer campo novo passa por discussão.

### Negativas

- Mais arquivos (port + adapter + DTOs) por cada par de BCs acoplados. Custo de boilerplate.
- DTOs parcialmente redundantes (ex.: "o título da obra" aparece em vários BCs). Aceitamos essa duplicação — é o preço do isolamento.
- Quando o dataset de leitura cruzada crescer (ex.: `collections` buscando centenas de summaries), o adapter precisa bater em `find_by_ids` (batch) em vez de `find_by_id` (N+1). Regra: a port expõe **o shape batch** desde o começo.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Duplicação de DTO escala mal com o número de pares | Média | Baixo | Revisar periodicamente se 2+ BCs descrevem o mesmo shape — aí sim promover para `shared_kernel` |
| Ciclo de wiring entre containers (A depende de B e B depende de A) | Média | Médio | Quando `providers.Container(...)` cruzado é inviável, o adapter pode instanciar o repo concreto do provider (infra→infra) via import direto. Aceito como compromisso |
| Adapter virar "repositório mal disfarçado" com dezenas de métodos | Baixa | Médio | PR review rejeita ports que crescem além do read-only essencial. Se um BC precisa de escrita cruzada, é sinal de domain service / integration event — não de port maior |

## Alternativas Consideradas

### 1. Continuar importando diretamente os repositórios do outro BC

O estado anterior. Funcionava, mas quebrava a regra de isolamento entre módulos e deixava os 4 BCs acoplados em um grafo denso.

**Rejeitado porque:** inviabiliza evolução independente dos BCs; é o problema que motivou este ADR.

### 2. Promover os repositórios compartilhados para `shared_kernel`

Mover `MovieRepository`/`SeriesRepository` para `shared_kernel` e deixar qualquer BC importar.

**Rejeitado porque:** agregados são sempre de um BC específico — `Movie` é do Media Catalog. `shared_kernel` serve para VOs genuinamente universais (ex.: `FilePath`, `LanguageCode`), não para conceitos que pertencem a um BC.

### 3. Domain events / integration events já na Fase 1

Em vez de read ports, fazer cada BC publicar eventos e materializar uma read model local.

**Rejeitado por enquanto:** complexidade alta demais para um `/series/{id}` que hoje é síncrono. Vale voltar a esse modelo quando algum cruzamento ficar grande o suficiente para justificar ou quando houver requisito de consistência eventual. A port **não atrapalha** essa futura migração — ela só substitui o adapter por um `CachedReadModelAdapter` que consulta uma tabela alimentada por eventos.

### 4. Query bus com handlers por BC

Um `QueryBus` central onde `media` publica handlers de suas próprias queries e `watch_progress` os invoca por tipo.

**Rejeitado porque:** reintroduz acoplamento indireto no dispatcher (todos os BCs conhecem o bus), complexidade maior que o benefício para uma app de 5 BCs.

## Referências

- `docs/clean-architecture-refactoring-plan.md` — Fase 1 detalha a ordem de migração e os pares afetados.
- `docs/adr/ADR-004-dependency-injection.md` — explica por que o container é o composition root.
- `docs/adr/ADR-008-screaming-architecture.md` — organização por BC que este ADR reforça.
- Vaughn Vernon, *Implementing Domain-Driven Design* — capítulo sobre Anti-Corruption Layer entre BCs.

---

## Notas de Implementação

Exemplo do padrão, consumidor `watch_progress` → provedor `media`:

```python
# src/modules/watch_progress/application/ports/media_lookup_port.py
@dataclass(frozen=True)
class MovieDisplayInfo:
    media_id: str
    title: str              # já localizado
    poster_path: str | None
    backdrop_path: str | None


class MediaLookupPort(ABC):
    @abstractmethod
    async def get_movie(self, media_id: str, lang: str) -> MovieDisplayInfo | None: ...
```

```python
# src/modules/watch_progress/infrastructure/acl/media_lookup_adapter.py
class MediaLookupAdapter(MediaLookupPort):
    def __init__(self, movie_repository: MovieRepository, ...) -> None: ...

    async def get_movie(self, media_id: str, lang: str) -> MovieDisplayInfo | None:
        movie = await self._movie_repo.find_by_id(MovieId(media_id))
        if movie is None:
            return None
        return MovieDisplayInfo(
            media_id=media_id,
            title=movie.get_title(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
        )
```

```python
# src/config/containers/watch_progress.py
class WatchProgressContainer(containers.DeclarativeContainer):
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    media_lookup = providers.Factory(
        MediaLookupAdapter,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        progress_repository=progress_repository,
        media_lookup=media_lookup,   # port, não repositório
    )
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-04-18 | Lucas Cristovam | Criação inicial (Fase 1 da refatoração Clean Architecture) |
