# ADR-035: Faixa Etária por Perfil como Gate de Catálogo e Playback

**Status:** Aceito
**Data:** 2026-09-12
**Deciders:** Lucas
**Technical Story:** O controle parental não é utilizável — restringir um perfil exige que o operador crie uma biblioteca física só de conteúdo infantil e mova ou duplique arquivos no disco, refazendo o trabalho a cada título novo. Nenhum dos 9 perfis da instância usa o mecanismo. O catálogo, porém, já carrega certificação em 87,9% dos filmes e 96,5% das séries.

---

## Contexto

`Profile` carrega hoje dois mecanismos de restrição, e nenhum dos dois funciona como controle parental.

**`is_kids` não gateia nada.** São 22 ocorrências em `src/`, todas de transporte: entity → mapper → DTO → schema → JSON. Não existe um único `if profile.is_kids` em nenhuma camada. A própria docstring do agregado assume o fato (`profile.py:41-43`): *"the kids flag is a UX hint; the ACL is the actual authorization gate"*. E mesmo que fosse lida, um booleano não distingue 10 de 16 anos.

**`allowed_library_ids` responde à pergunta errada.** A ACL é default-deny, tipada, aplicada em ~20 sites de repositório, e pergunta *"este perfil acessa esta prateleira?"* — não *"este perfil pode ver este título?"*. Usá-la como controle parental força a granularidade de biblioteca sobre um problema que é de título, com custo operacional em disco.

Três fatos agravam:

- **A ACL não é vinculante.** `PUT /api/v1/profiles/{id}` valida apenas ownership (`update_profile.py:43-46`), então o próprio membro reescreve o próprio ACL. E `GET /api/v1/libraries` (`library_routes.py:55-64`) não declara nenhuma dependência de autenticação, o que torna os `lib_xxx` enumeráveis. Um PUT e o membro se auto-concede o catálogo inteiro.
- **Adoção zero, medida.** No banco da instância: 9 perfis, todos com `is_kids = 0`, todos com as mesmas 2 bibliotecas. O mecanismo degenerou em "todo mundo vê tudo".
- **Não existe PIN.** `switch_profile.py:43-62` valida existência, ownership e sessão. Nada mais. Não há código de responsável em `User` nem em `Profile`.

**O dado necessário para um mecanismo melhor já está persistido.** 571 de 644 filmes vivos e 55 de 57 séries têm certificação em `content_rating`, importada do TMDB. A distribuição real é majoritariamente ClassInd com uma cauda americana: `R` 128, `14` 98, `L` 88, `16` 70, `12` 62, `PG` 28, `NR` 27, `18` 24, `PG-13` 23, `10` 19, `G` 4, e 73 sem rótulo.

O obstáculo é semântico, não de dados: `ContentRating` é um `StringValueObject` livre de até 20 caracteres (`content_rating.py:22-39`), sem ordenação. Não há como responder se `R` é mais ou menos restritivo que `14`.

Some-se a isso que a política de jurisdição mora na borda: `tmdb_response_mapper.py:329-335` monta o mapa país → certificação e descarta tudo menos um rótulo, inferindo a jurisdição a partir de `supported_locales` — atalho que o próprio docstring admite (`:312-317`) e que já está registrado como dívida em `docs/tech-debt-remediation-plan.md:83`.

## Decisão

Nós iremos introduzir **limite de faixa etária por perfil** como o eixo primário de controle parental, mantendo `allowed_library_ids` como segundo eixo, estrutural. Os dois compõem por AND, deny-wins, dentro de um único value object.

**1. Vocabulário no `shared_kernel`.**
`AgeRating` (`IntValueObject`, 0..21), `RatingSystem` (`StrEnum`) e `Certification` entram em `shared_kernel/value_objects/`; a tabela rótulo → idade e `ViewingPolicy` entram em `shared_kernel/content_policy/`, seguindo o precedente de pacote de `shared_kernel/track_selection/`. O critério do ADR-018 está satisfeito: `media`, `identity`, `collections` e `watch_progress` consomem. `AgeRating` **não reimplementa comparadores** — `IntValueObject` (`building_blocks/domain/value_objects.py:119`) já provê `__lt__/__le__/__gt__/__ge__` nas linhas 164-186.

**2. O sistema de classificação é persistido junto com o rótulo, não inferido.**
`Certification` guarda `system`, `label` e `minimum_age`. Sem `system` persistido, o `PG` de 1972 e o `PG` de 2011 são indistinguíveis — e essa distinção decide se seis filmes de horror pré-1984 entram no catálogo de uma criança de 10 anos. O rótulo exibido (`ContentRating`) permanece inalterado nos DTOs e no badge do frontend.

**3. Certificação ausente ou não normalizável equivale a 18+.**
Regra única, embutida em `AgeRating.allows()`, sem campo por perfil. Um `unrated_policy` configurável adicionaria coluna, enum e um switch de formulário para uma decisão que o responsável não tem informação para tomar. `NR`, `UR` e `N/A` mapeiam para `None` — **nunca para 0**, que é a falha silenciosa clássica deste tipo de tabela.

**4. `Profile.maturity_limit: AgeRating | None`, com `None` = irrestrito.**
O default preserva exatamente o comportamento de hoje, então nenhum dos 9 perfis existentes sofre regressão. `is_kids` passa a ser **propriedade derivada** (`maturity_limit is not None and maturity_limit.value <= 12`), o que elimina o caminho de escrita sem quebrar o contrato da API. `exit_requires_pin` exige `maturity_limit is not None` como invariante do agregado (`PROFILE.EXIT_PROTECTION_REQUIRES_LIMIT`).

**5. `allowed_library_ids` mantém a semântica atual: `[]` é deny-all.**
O default **não** é invertido para `None` = wildcard. `_decode_allowed_libraries` (`profile_mapper.py:36-80`) coage NULL, JSON malformado e não-lista para `[]` — é o único decode fail-closed do sistema, exigido pelo ADR-018 §3. Inverter o default faria corrupção e ausência caírem no mesmo branch, transformando um fail-closed em fail-open.

**6. `ProfileLibraryAccessPort` vira `ProfileViewingPolicyPort`.**
`find_for_profile(profile_id: ProfileId) -> ViewingPolicy` devolve os dois eixos numa chamada, sem round-trip duplo, e corrige de passagem o `profile_id: str` cru de hoje (`profile_library_access_port.py:26`). Cópia local do port por BC consumidor — `media`, `collections` e `watch_progress` — conforme ADR-009. `streaming` não ganha cópia: continua delegando aos use cases de catálogo.

**7. O filtro é projetado em SQL a partir de um único helper.**
`media/infrastructure/persistence/repositories/_visibility_filter.py` substitui os ~20 blocos inline de ACL — `movie_repository.py` (81, 143, 354, 463, 518, 549, 579, 675, 1043), `series_repository.py` (82, 175, 194, 405, 481, 517, 546, 579, 1437) e `_genre_helpers.py` (158, 311). `ViewingPolicy.permits()` é a **definição** da regra (ADR-017); o `WHERE` é a **projeção**, e um teste de integração amarra as duas. O filtro não pode ser aplicado em memória: `list_by_genre` (cursor duplo), `list_recently_added_catalog` (merge por `created_at`) e `search_catalog` (pool de rank) desincronizariam `has_more`, `total_count` e cursores a partir da página 2.

**8. A autoridade de administrador fica suspensa enquanto um perfil restrito estiver ativo na sessão**, salvo unlock parental válido.
`current_admin_user` (`identity/infrastructure/auth/fastapi_users.py:34-57`) checa hoje **apenas** `user.role`; nada no caminho olha o perfil ativo. A topologia real do lar torna isso decisivo: na instância, o usuário admin possui 4 dos 9 perfis, que é como HBO Max e Netflix funcionam e como a UI de perfis convida a fazer. Sem esta decisão, a criança com perfil restrito ativo chama `PATCH /api/v1/admin/movies/{id}/rating` — o endpoint desta própria feature —, grava `min_age = 0` com `rating_source = MANUAL`, imune a re-enrich por design, e assiste qualquer coisa. Uma requisição, sem PIN. O RBAC passa a ser sensível ao contexto de sessão via `ParentalGate.ensure_can_use_admin(active_profile, unlock_valid)` no shim `authenticated_admin` publicado em `identity/presentation/public.py`.

**9. O PIN parental é único por conta (o lar), e o challenge dispara no perfil de destino.**
Hash em `User.parental_pin_hash`, via o `PasswordHasherPort` que já existe (`password_hasher_port.py:20-37`, adicionar `verify()`); contadores de lockout e janela de unlock (`parental_unlock_until`, ~5 min) em `access_tokens`, **por device** — se o lockout fosse por conta, a criança erraria o PIN cinco vezes no tablet e trancaria o responsável na TV da sala. A regra é: existe PIN configurado ⇒ **entrar** em perfil irrestrito ou de limite maior que o atual exige PIN. Um guard de saída seria insuficiente, porque numa sessão nova não há perfil ativo e qualquer device cuja sessão já aponte para perfil irrestrito nunca passaria por ele. Os quatro bypasses de perfil — `switch_profile`, `update_profile`, `delete_profile`, `create_profile` — ficam sob a mesma regra.

**10. A seleção de jurisdição sai do adapter.**
`TmdbResponseMapper` passa a devolver o mapa país → rótulo cru; a política vai para `media/domain/services/content_rating_policy.py`, configurada pelo bucket `SettingKey.CONTENT_RATING` (ADR-013/014) com `{jurisdictions: ["BR", "US"], fallback: "strictest_available"}`. Quando nenhuma jurisdição preferida tem certificação, o fallback escolhe a mais restritiva disponível no mapa, em vez do `None` atual. Isto executa a onda 5.2 da dívida técnica.

**11. Contrato HTTP: 403, nunca 401.**
`homeflix-web/src/api/client.ts:90-95` trata 401 inesperado como sessão expirada e redireciona para `/login` limpando o cache. O gate usa 403 com `PARENTAL_PIN_REQUIRED` / `_INVALID` / `_LOCKED` (este com `retry_after_seconds`). Para título bloqueado: **404 no eixo biblioteca** (esconde existência, comportamento atual) e **403 `CONTENT_RESTRICTED_BY_MATURITY` no eixo etário**, com `required_age` e `profile_limit` nos details e **sem o título** — senão o endpoint vira oráculo de enumeração para a própria criança que o gate protege. Conteúdo sem classificação usa o código distinto `CONTENT_RESTRICTED_UNRATED`, que permite à UI oferecer o atalho de classificação para admin.

## Consequências

### Positivas

- O operador deixa de precisar de biblioteca física de conteúdo infantil. A restrição é transversal a todas as bibliotecas e se aplica sozinha a títulos novos a cada scan.
- Funciona com o acervo existente no dia do deploy: um perfil com limite `12` enxerga 173 filmes e 36 séries sem nenhum backfill; com limite `14`, 322 filmes e 46 séries.
- Os ~20 blocos inline de ACL colapsam em um helper. O saldo é *menos* duplicação do que existe hoje, e um terceiro eixo futuro custa um arquivo, não vinte.
- Fecha, de passagem, buracos de autorização pré-existentes e não relacionados a kids: `watch_progress` (`MediaLookupPort` nem recebe profile), `save_progress.py:22-49` (aceita qualquer `media_id`), `get_watchlist.py:68` (nenhuma ACL) e as escritas de watchlist e listas customizadas.
- Executa a onda 5.2 da dívida técnica movendo a política de classificação do adapter para o domínio.
- `ContentRating` continua sendo o que o badge desenha: nenhuma mudança visual no catálogo.

### Negativas

- O PR de enforcement é grande e mecânico, com alto risco de conflito de merge nos dois repositórios de catálogo.
- A normalização rótulo → idade é convenção, não ciência. `PG → 13` esconde 28 filmes de perfis com limite `12` que um mapeamento mais permissivo mostraria; `R → 17` e `TV-MA → 17` são escolhas análogas. O override manual é a válvula de correção.
- **Enquanto o ADR-036 não for implementado, o gate vale para descoberta e para as rotas de API de playback, não para a entrega dos segmentos HLS.** `GET /stream/hls/{path_hash}/{file_path}` (`hls_routes.py:95-126`) não declara autenticação e `path_hash = md5(caminho absoluto)` (`hls_cache_store.py:85-86`) é determinístico, sem segredo e sem expiração. A UI precisa comunicar essa limitação ao responsável enquanto ela existir.
- Séries são bloqueadas inteiras: `episodes` e `seasons` não têm `content_rating`, e o TMDB não fornece classificação por episódio de forma confiável.
- Toda rota administrativa dos 11 módulos passa a atravessar o `ParentalGate`.
- Um PIN de 4 a 6 dígitos protege contra a criança da casa, não contra um adversário — a mesma pessoa autentica com a senha da conta e desfaz tudo.
- Artwork continua público por design (ADR-034): `<img>` não envia header de autenticação. A chave é content-hash e não é enumerável, mas uma URL vazada entrega o poster com `Cache-Control: immutable`.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Resposta cacheada de um perfil servida a outro — o mesmo path passa a variar por cookie | Média | Alto | `no-store` (ou `Vary: Cookie`) nos endpoints filtrados, com teste de header no PR de enforcement |
| Catálogo restrito vazio por baixa cobertura de certificação | Baixa | Alto | Medido: 173 filmes em `12`. Backfill derivado na própria migration + worklist administrativa |
| Filtro aplicado pós-query desincroniza cursor e paginação | Média | Médio | Filtro obrigatoriamente em SQL; teste de projeção contra o predicado do domínio |
| Re-enrich apaga classificação manual | Alta | Médio | `rating_source = MANUAL` excepcionado em `MergePolicy.OVERWRITE` (`_metadata_field_merge.py:86-88`) |
| Criança com sessão de admin altera a classificação do próprio título | Média | Alto | Decisão 8 — autoridade de admin suspensa sob perfil restrito |
| Lockout de PIN tranca o responsável em todos os devices | Média | Baixo | Contadores em `access_tokens`, por device |
| Índice composto não usado por causa de `COALESCE` no predicado de idade | Média | Médio | Escolher o ramo `OR min_age IS NULL` no build da query em Python |
| Busca perde resultados: o pré-query FTS5 corta em `limit*2` antes de qualquer filtro (`movie_repository.py:1013-1017`) | Alta | Baixo | Aumentar o multiplicador no PR de enforcement; indexar no FTS é follow-up (colunas FTS5 não têm afinidade de tipo e exigiriam `CAST`) |
| Contrato do payload de perfil quebra o frontend na janela entre backend e front | Média | Médio | Teste de contrato garantindo shape idêntico com `is_kids` derivado |

## Alternativas Consideradas

### 1. Manter a ACL de bibliotecas como único mecanismo

Continuar exigindo que o operador crie uma biblioteca separada para conteúdo infantil.

**Rejeitado porque:** exige biblioteca física e trabalho manual por título; não é vinculante, já que o próprio membro edita o próprio ACL; e a adoção zero medida nos 9 perfis reais mostra que o custo operacional é proibitivo na prática, não só em teoria.

### 2. `Library.default_minimum_age` (ADR-005)

Carimbar uma idade mínima por biblioteca, herdada pelos títulos.

**Rejeitado porque:** custa JOIN nos ~20 sites de filtro, ou um job de re-stamp a cada scan, ou um segundo port `media → library`. Resolveria os 108 títulos indeterminados de uma vez — é a ponte honesta entre o mecanismo velho e o novo —, mas override manual e worklist cobrem o caso real de três bibliotecas. Registrado como opção a reconsiderar se o número de bibliotecas crescer.

### 3. Campo `unrated_policy` por perfil

Deixar o responsável escolher se conteúdo sem classificação aparece.

**Rejeitado porque:** adiciona coluna, enum no `shared_kernel` e um switch de formulário para uma decisão que o usuário não tem informação para tomar. A regra única (indeterminado = 18) entrega o comportamento útil de graça: perfil irrestrito vê os indeterminados, perfil com limite não vê.

### 4. Gate por `contextvar` de "modo kids"

Resolver o perfil ativo uma vez e propagar implicitamente por contexto de request.

**Rejeitado porque:** o ADR-010 §3 exige `profile_id` explícito no Input dos use cases. Estado implícito de request é exatamente o que aquele ADR proíbe, e tornaria o teste de arquitetura desta decisão impossível de escrever.

### 5. Alargar o ADR-024 para expor a política como contrato de presentation

Publicar `ViewingPolicy` em `identity/presentation/public.py` e deixar os outros BCs importarem direto.

**Rejeitado porque:** aquele canal existe para primitivas de auth que não comportam port. A política de visualização comporta port, e o override de catálogo pertence a `media/presentation/dependencies.py` — cujo docstring já reserva literalmente "parental controls, kids-mode filtering".

## Referências

- ADR-005 (Library como Entidade de Configuração) — alternativa 2
- ADR-009 (Cross-BC Read Ports + ACL) — port declarado no consumidor, adapter único ponto de import cross-BC
- ADR-010 (Identity Bounded Context) — `profile_id` explícito no Input; ver emendas abaixo
- ADR-011 (Authentication Strategy) — `current_profile_id` em `access_tokens`, troca de perfil sem reemissão de cookie
- ADR-013 / ADR-014 (Runtime Settings, aggregate por bucket) — bucket `CONTENT_RATING`
- ADR-017 (Invariantes de domínio na camada de domínio) — `permits()` é a definição, o `WHERE` é projeção
- ADR-018 (Identificadores de domínio como VOs nas fronteiras) — critério de admissão no `shared_kernel`, default-deny
- ADR-033 (Interface Segregation em Repositórios) — troca de assinatura nas role-interfaces de catálogo
- ADR-034 (Variantes Responsivas de Artwork) — artwork público, resíduo declarado
- `docs/tech-debt-remediation-plan.md:83` — onda 5.2, `ContentRatingPolicy` no domínio, executada por este ADR
- Classificação Indicativa (Ministério da Justiça) — escala L / 10 / 12 / 14 / 16 / 18
- TMDB API — `release_dates` (filmes) e `content_ratings` (séries)

### Emendas a decisões anteriores

- **ADR-010 e `profile.py:41-43`** — a frase *"the kids flag is a UX hint; the ACL is the actual authorization gate"* é exatamente o que este ADR revoga. Nota separada: o ADR-010 descreve `Profile` como "filha de User" enquanto o código a implementa como aggregate root independente; reconciliar o texto na mesma PR.
- **ADR-018 §4** — `allowed_library_ids` é rebaixado a um dos dois eixos. O §3 (drop-and-warn, default-deny por entrada) é mantido e **estendido** ao rating desconhecido.
- **ADR-011** — a troca de perfil ganha challenge de PIN, sem cookie novo e sem claim em token.
- **`docs/roadmap.md:63-66`** — o item 4.2 está marcado como entregue descrevendo a flag sem semântica; precisa de item novo.
- **`docs/homeflix-requirements.md:26-30`** — o documento é v1.0, lista multi-perfil como *Excluído* e não menciona kids nem controle parental. O requisito nunca existiu por escrito: este ADR o carrega no Contexto até que um RF seja criado.
- **Não existe ADR da ACL de biblioteca** — ela é passo de PR do ADR-010 e foi endurecida pelo ADR-018. Este é o primeiro registro escrito de por que ACL de biblioteca não é controle parental.

---

## Notas de Implementação

```python
# shared_kernel/value_objects/age_rating.py
class AgeRating(IntValueObject):          # 0..21; comparadores herdados
    ADULT: ClassVar[int] = 18

    def allows(self, required: "AgeRating | None") -> bool:
        """Ausência de classificação equivale a 18+ (fail-closed)."""
        return (self.ADULT if required is None else required.value) <= self.value

# shared_kernel/value_objects/certification.py
@dataclass(frozen=True)
class Certification:
    system: RatingSystem           # BR_DEJUS | US_MPA | US_TV | NUMERIC | UNKNOWN
    label: ContentRating           # inalterado — é o que o badge desenha
    minimum_age: AgeRating | None  # None = indeterminado

# shared_kernel/content_policy/viewing_policy.py
@dataclass(frozen=True)
class ViewingPolicy:
    allowed_library_ids: tuple[LibraryId, ...]
    maturity_limit: AgeRating | None       # None = irrestrito

    @property
    def denies_everything(self) -> bool:
        return not self.allowed_library_ids

    def permits(self, *, library_id: LibraryId, minimum_age: AgeRating | None) -> bool:
        ...
```

Tabela de normalização (`shared_kernel/content_policy/certification_scale.py`):

| Sistema | Mapeamento |
|---------|------------|
| `BR_DEJUS` | `L`/`Livre` → 0, `10` → 10, `12` → 12, `14` → 14, `16` → 16, `18` → 18 |
| `US_MPA` | `G` → 0, `PG` → 13, `PG-13` → 13, `R` → 17, `NC-17` → 18 |
| `US_TV` | `TV-Y` → 0, `TV-Y7` → 7, `TV-G` → 0, `TV-PG` → 10, `TV-14` → 14, `TV-MA` → 17 |
| Numérico | `^(\d{1,2})\+?$` → o próprio inteiro (cobre `0+`, `6`, `15` de sistemas europeus) |
| `NR` / `UR` / `N/A` | `None` + WARNING — nunca 0 |

`PG → 13` e não 10 porque metade dos 28 filmes `PG` do acervo é anterior a 1984, quando `PG-13` ainda não existia e `PG` absorvia o que hoje seria 13; seis deles são horror. Em controle parental, falso-permitir é a falha que importa. Com `system` persistido, dá para refinar por era depois.

Dois testes que não existem hoje e são condição de pronto do enforcement:

```
tests/modules/media/integration/.../test_visibility_projection.py
    {t for t in catálogo if policy.permits(...)} == resultado do SQL, para ~6 políticas
    # impede permits() de virar enfeite enquanto quem autoriza de fato é o WHERE

tests/architecture/test_visibility_enforcement.py
    nenhum repositório constrói predicado sobre library_id/min_age fora de _visibility_filter.py
    # é por não existir essa rede que watch_progress e watchlist ficaram sem ACL
```

A regra recíproca — "todo use case cujo Input tem `profile_id` declara o port" — foi descartada: dá falso-positivo em 24 use cases fora de `media` (17 em `collections`, 5 em `watch_progress`, 2 em `preferences`) que são profile-scoped por *ownership*, não por visibilidade de catálogo.

Pontos de toque previstos: `age_rating.py`, `rating_system.py`, `certification.py`, `content_policy/` (novos); colunas e índice composto em `movies`/`series` com data-migration derivando `min_age` das 629 linhas já classificadas; `content_rating_policy.py` (novo) e `tmdb_response_mapper.py` (deixa de decidir); `_visibility_filter.py` (novo) e os ~20 sites de repositório; `profile_viewing_policy_port.py` nos três BCs consumidores; `profile.py`, `user.py`, `access_token_model.py` e `parental_gate.py`; `authenticated_admin` em `identity/presentation/public.py`.

## Emendas

Três correções levantadas durante a implementação, registradas aqui em vez de
reescritas silenciosamente no texto original.

### 1. `RatingSystem` não tem `MANUAL`, e ganha `UNKNOWN`

A decisão 2 listava `MANUAL` entre os membros de `RatingSystem`. Isso conflava
dois eixos: `MANUAL` é *quem forneceu* o valor — proveniência, que vira a coluna
`rating_source` — e não *em que escala o rótulo está escrito*. Mantidos no mesmo
enum, "um operador classificou este título, na escala brasileira" seria
irrepresentável.

`UNKNOWN` entrou porque `Certification.system` é obrigatório e um rótulo como
`NR` não pertence a escala nenhuma.

### 2. A cobertura é 544 de 644 filmes vivos, não 547 de 653

Os números originais contavam linhas soft-deleted, que nenhum perfil enxerga. O
back-fill escopa com `deleted_at IS NULL` — atualizar uma linha soft-deleted
dispararia os triggers de FTS5 para um documento que já saiu do índice,
enviesando `nDoc`/`avgdl` e portanto o `bm25()` de todo o catálogo.

Os degraus baixos não mudam: um perfil `12` continua vendo 173 filmes e 36
séries. O degrau `14` passa de 324 para 322.

### 3. A jurisdição deixa de seguir `supported_locales`

Consequência da decisão 10 que o texto original não tornou explícita. Antes,
quem configurasse `supported_locales = ("en", "es-ES")` ganhava `["ES", "US"]`
como ordem de preferência automaticamente. Agora a ordem vem do bucket
`CONTENT_RATING`, cujo default é `["BR", "US"]`.

Para a configuração padrão (`("en", "pt-BR")`) o resultado é idêntico e não há
mudança observável. Para uma instância com locale customizado fora de BR/US, o
comportamento muda sem que o operador tenha mexido em nada — é o preço de
separar idioma de UI de autoridade de classificação, que era exatamente a dívida
que esta decisão pagou, mas precisa estar escrito.

### 4. `classify` devolve `None` para rótulo que não cabe em `ContentRating`

Descoberto ao fazer o adapter reportar todos os países: `ContentRating` tem teto
de 20 caracteres e o TMDB serve texto livre de contribuidor — o rótulo turco
`Genel Izleyici Kitlesi` tem 22. Deixar o VO levantar abortaria o enriquecimento
inteiro do título por causa da redação de um órgão estrangeiro.

Isso é deliberadamente distinto de "sem classificação": `NR` é uma declaração que
um órgão fez e é preservada para o badge; uma frase de 44 caracteres não é um
rótulo que este catálogo consegue guardar, e uma cópia truncada seria um rótulo
errado na tela.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-09-12 | Lucas | Criação inicial (Aceito) |
| 2026-09-12 | Lucas | Emendas 1-4, levantadas na implementação das PRs #421, #422 e #423 |
