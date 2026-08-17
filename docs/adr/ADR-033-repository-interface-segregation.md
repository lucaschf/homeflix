# ADR-033: Interface Segregation em Repositórios

**Status:** Aceito
**Data:** 2026-08-16
**Deciders:** Lucas Cristovam
**Technical Story:** Auditoria de débito técnico (multi-agente, 2026-08-16) — as ABCs `series_repository` (~36 métodos) e `movie_repository` (29) são god-interfaces que misturam concerns de subdomínios. Onda 2 do `docs/tech-debt-remediation-plan.md`. Enabler do ADR-032 (decomposição do `media`).

---

## Contexto

As interfaces (ABCs) de repositório do catálogo cresceram em god-interfaces que misturam **razões-de-mudar não relacionadas**:

- `src/modules/media/domain/repositories/series_repository.py` (~724 LOC) declara **~36 métodos**: CRUD/busca de catálogo **+** artwork-mirror (`update_series_artwork`, `find_with_remote_artwork`) **+** intro-detection (`find_seasons_pending_intro_detection`) **+** credits-detection (`count_episode_credits_states`) **+** scrub-preview (`update_episode_scrub_preview_path`) **+** stats.
- `movie_repository.py` (~29 métodos) repete o padrão, incluindo cirurgia de FK em raw-SQL (relink/promote) ao lado de reads simples.

Isso viola o **Interface Segregation Principle**: um job agendado que precisa de 2-3 métodos (ex.: o intro-detection job) recebe o **port inteiro** via `uow.series` / `uow.movies`. Pior, é o **mecanismo concreto que solda os subdomínios** — cada nova feature (skip-intro, créditos, artwork, scrub) altera a **mesma** interface, e nenhum subdomínio pode ser extraído (ADR-032) sem carvar o repositório primeiro.

A auditoria observou que **o padrão certo já é idiomático no próprio repo**: `intro_detection_run_repository`, `scan_run_repository`, `media_conflict_repository` e `subtitle_ocr_run_repository` são ports estreitos, focados. As god-interfaces são a exceção, não a regra.

## Decisão

Nós iremos adotar a política **"um port por razão-de-mudar"** nos repositórios de catálogo:

- Um **repositório de catálogo enxuto** por agregado (Movie, Series): CRUD, busca, paginação, variantes — o núcleo estável.
- **Role-interfaces** por subdomínio, cada uma migrando junto com seu subdomínio na decomposição (ADR-032):
  - `ArtworkMirrorRepository`
  - `IntroDetectionRepository`
  - `CreditsDetectionRepository`
  - `ScrubPreviewRepository`
- Use cases e jobs dependem **apenas da role-interface que usam**, não do port inteiro.
- **A classe SQLAlchemy pode implementar várias role-interfaces** contra a mesma tabela — a segregação é na *interface* (o contrato que o consumidor vê), não obrigatoriamente na implementação de persistência.

Ressalva de escopo: métodos que atualizam **atributos das entidades-filhas do agregado** (marcadores de intro/créditos, artwork de season/episode) são coesão-por-agregado legítima enquanto essas colunas viverem no agregado Series/Movie. A segregação de interface **sozinha não desacopla** os subdomínios — as entidades ainda carregam as colunas; o desacoplamento completo vem quando os marcadores viram read-model próprio (ADR-032, fatia 3). O que é claramente fora de lugar e sai agora são as **projeções/counters orientados a job** (ex.: `find_with_remote_artwork → RemoteArtworkRow`, `count_episode_credits_states → dict[str,int]`).

## Consequências

### Positivas

- **ISP respeitado**: cada consumidor vê só o contrato que precisa; a intenção fica explícita na assinatura da dependência.
- **Desbloqueia a decomposição** (ADR-032): cada role-interface é a unidade que migra com seu subdomínio.
- **Menor superfície de mudança**: uma feature de créditos altera a `CreditsDetectionRepository`, não a interface do catálogo inteiro.

### Negativas

- Mais interfaces (uma por role) — mais arquivos, embora cada um seja pequeno e focado.
- A classe SQLAlchemy passa a implementar múltiplas ABCs — mais declarações de herança (mitigado: a impl continua uma só, contra uma tabela).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Over-segregação (um port por método) | Baixa | Médio | Segregar por **razão-de-mudar** (subdomínio), não por método; o teste é "isso muda por um motivo diferente?". |
| Confundir coesão-de-agregado com concern separado | Média | Médio | Manter no repo de catálogo os updates que são atributos legítimos do agregado; só extrair projeções/counters orientados a job (ver ressalva). |

## Alternativas Consideradas

### 1. Manter as god-interfaces

**Rejeitado porque:** viola ISP, força jobs a receberem o port inteiro, e trava a decomposição do ADR-032 (não dá para mover um subdomínio sem carvar a interface).

### 2. Um repositório por método

Segregação máxima.

**Rejeitado porque:** granularidade excessiva — explode o número de interfaces sem ganho; a unidade correta é o subdomínio (razão-de-mudar), não a operação.

### 3. Query-objects avulsos sem role-interfaces

Extrair só as queries pesadas para funções/objetos soltos.

**Rejeitado porque:** resolve o tamanho do arquivo mas não a segregação do contrato — os consumidores continuariam dependendo do port inteiro. Role-interfaces atacam o acoplamento na dependência.

## Referências

- ADR-032: Decompor o módulo `media` em subdomínios (esta é o enabler)
- ADR-004: Injeção de Dependências (ports, não concretos)
- Precedente no repo: `intro_detection_run_repository`, `scan_run_repository`, `media_conflict_repository`, `subtitle_ocr_run_repository`
- `docs/tech-debt-remediation-plan.md` — Onda 3.1

---

## Notas de Implementação

```python
# domain/repositories/ — role-interfaces por subdomínio
class SeriesRepository(ABC):  # catálogo enxuto
    async def find_by_id(self, series_id: SeriesId) -> Series | None: ...
    async def save(self, series: Series) -> Series: ...
    # ... CRUD / busca / paginação

class IntroDetectionRepository(ABC):  # role-interface (migra com o subdomínio)
    async def find_seasons_pending_intro_detection(self) -> list[...]: ...
    async def update_episode_intro_marker(self, ...) -> None: ...

# infrastructure/ — uma classe SQLAlchemy pode satisfazer várias contra a mesma tabela
class SQLAlchemySeriesRepository(
    SeriesRepository, IntroDetectionRepository, CreditsDetectionRepository
):
    ...

# use case / job — depende só da role que usa
class RunIntroDetectionJob:
    def __init__(self, repo: IntroDetectionRepository) -> None: ...
```

Ordem: segregar a interface **antes** de mover o subdomínio (ADR-032). As projeções/counters orientados a job (`RemoteArtworkRow`, `count_episode_credits_states`, ...) saem para a role-interface correspondente; os updates que são atributos do agregado ficam no repo de catálogo até a fatia de read-model dos marcadores.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-08-16 | Lucas Cristovam | Criação inicial |
