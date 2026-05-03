# ADR-010: Identity Bounded Context — User, Profile and Context Passing

**Status:** Proposto
**Data:** 2026-05-03
**Deciders:** Lucas Cristovam
**Technical Story:** Introdução de autenticação e personalização ao HomeFlix — habilitar múltiplos usuários com login próprio, perfis de personalização (estilo Netflix) e isolamento de dados de uso (`watch_progress`, `collections`, `preferences`) por perfil.

---

## Contexto

O HomeFlix opera hoje sem qualquer conceito de usuário ou perfil: agregados como `WatchProgress`, `CustomList` e `PlaybackPreferences` são globais (singletons de fato). À medida que o produto evolui para uso doméstico real (múltiplos membros da casa) e potencialmente extra-doméstico (compartilhamento controlado com família/amigos), torna-se necessário introduzir identidade.

A introdução de identidade é uma decisão atípica em sistemas brownfield porque o estado atual ("nada") permite desenho limpo, sem migração legada complexa. Isso aumenta a barra de qualidade: não há desculpa de "não dá pra fazer certo agora".

A decisão precisa equilibrar três forças:

1. **Aproveitar bibliotecas maduras** (FastAPI Users) para não reimplementar autenticação, signup, reset de senha e JWT do zero — economia de semanas de trabalho e redução de superfície de bug em código de segurança.
2. **Preservar princípios já estabelecidos** — em particular ADR-002 (prefixed external IDs), ADR-008 (screaming architecture / módulos isolados) e ADR-009 (cross-BC reads via port + ACL). Bibliotecas externas frequentemente assumem padrões (UUIDs, ID inteiro auto-increment) que conflitam com convenções do projeto.
3. **Não fechar portas para crescimento** — o HomeFlix é simultaneamente lab de arquitetura e ferramenta funcional. A modelagem de identidade precisa servir tanto ao caso de uso doméstico imediato quanto à eventual evolução para multi-tenant ou serviço separado, sem refactor cross-cutting.

Restrições relevantes: o frontend (`homeflix-web`) precisa de mudança coordenada (tela de login, seletor de perfil); três bounded contexts existentes (`watch_progress`, `collections`, `preferences`) precisam ganhar `profile_id` em seus agregados; e o admin panel já planejado depende do conceito de role/permissão que esta decisão estabelece.

## Decisão

Nós iremos introduzir um novo bounded context **`identity`** (em `src/modules/identity/`) responsável por autenticação de usuários e gestão de perfis de personalização, com os seguintes contornos:

### (1) Modelagem — User e Profile como agregados separados

- `User` é o **aggregate root de autenticação e ciclo de vida**. Possui credenciais (email, senha hasheada), role (`admin` | `member`), flags de ativação e verificação, e referência aos seus perfis.
- `Profile` é a **entidade de contexto de personalização**, filha de `User`. Carrega nome, avatar, flag `is_kids`, e (futuramente) `allowed_library_ids`.
- Outros bounded contexts (`watch_progress`, `collections`, `preferences`) referenciam **apenas `ProfileId`** — nunca `UserId`. `User` controla CRUD de profiles, `Profile` é o ponto de ancoragem de toda telemetria de uso.

### (2) Identificação — UUID interno + prefixed external_id

- O banco armazena `User.id` como `UUID` (mantendo compatibilidade nativa com FastAPI Users) e adiciona uma coluna `external_id VARCHAR` indexada no formato `usr_xxxxxxxxxxxx`.
- O domínio expõe somente o prefixed ID via Value Object `UserId` (e `ProfileId` análogo, com prefixo `prf`). FastAPI Users opera no UUID interno; nenhum código de domínio ou API vê UUID.
- O mapeamento UUID↔prefixed acontece exclusivamente no SQLAlchemy mapper do BC `identity`. Os prefixos `usr` e `prf` são adicionados ao registro `ExternalId.VALID_PREFIXES`.

### (3) Propagação de contexto — explicit profile_id

- O `profile_id` da request é resolvido **uma única vez** na presentation layer via FastAPI dependency `get_current_profile` (que valida o JWT, carrega o profile e checa que pertence ao usuário autenticado).
- O `profile_id` é então **passado explicitamente** como campo de Input dataclass para todo use case que dele depende. Use cases repassam para repositories quando necessário.
- **Está proibido** armazenar `profile_id` em `contextvars.ContextVar`, em atributo de middleware, ou em qualquer state global acessível de baixo. Toda dependência de contexto é declarada na assinatura.

A implementação se dá em uma sequência de PRs sequenciais começando pelo foundation do BC `identity` (entidades, repos, FastAPI Users wiring, rotas `/auth/*` e `/profiles/*`), seguida pela introdução de `profile_id` em cada um dos três BCs consumidores via migrations Alembic com backfill (NULLABLE → seed → NOT NULL).

## Consequências

### Positivas

- **Aproveitamento de biblioteca madura** — FastAPI Users entrega signup, login, JWT, reset de senha, verificação por email com código de produção testado por terceiros. Reduz semanas de implementação e elimina superfície de bug em código de segurança crítico.
- **Preservação dos princípios já estabelecidos** — ADR-002 (prefixed IDs), ADR-007 (imutabilidade `with_*`), ADR-008 (módulos isolados), ADR-009 (cross-BC via port + ACL) continuam válidos sem exceção. Identity entra como cidadão de primeira classe da arquitetura.
- **Boundary alinhado a DDD** — separar `User` (auth identity, ciclo de vida) de `Profile` (contexto de personalização referenciado cross-BC) reflete uma distinção real e impede a conflagração de duas responsabilidades distintas em um único agregado.
- **Habilita admin panel sem refactor** — `role` no `User` já fornece a base de autorização que o admin panel planejado precisa, sem revisitar a modelagem.
- **Migration limpa** — como nenhum BC consumidor tem `profile_id` hoje, a introdução é um refactor *forward-only*, sem dívida técnica de coexistência entre dados antigos sem profile e dados novos com profile.
- **Explicit context preserva qualidade arquitetural** — use cases continuam testáveis sem fixtures globais, cada chamada é rastreável via log estruturado, e bugs sob async ficam impossíveis por construção.

### Negativas

- **Refactor cross-cutting em 3 BCs existentes** — `watch_progress`, `collections` e `preferences` precisam adicionar `profile_id` em agregado, repo, use case input e route. PRs sequenciais com dependência explícita.
- **Coordenação obrigatória com `homeflix-web`** — frontend precisa ganhar tela de login, seletor de perfil e propagação de `profile_id` em todas as chamadas. Lançamento backend não pode preceder frontend sem feature flag.
- **Custo de manutenção do mapper UUID↔prefixed** — qualquer mudança em assinaturas internas do FastAPI Users que envolva ID type pode demandar ajuste no mapper. Custo localizado, mas existe.
- **Boilerplate de `ProfileLookupPort` em 3 BCs** — cada BC consumidor adiciona port + DTO + adapter ACL (padrão ADR-009). Repetitivo, mas isso é o preço do isolamento entre bounded contexts.
- **Carga de implementação inicial alta** — sequência completa de PRs (foundation + 3 refactors + ACL + frontend) é trabalho de várias semanas antes de funcionalidade nova ser entregue ao usuário final.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Esquecer `profile_id` em algum use case durante refactor cross-BC, gerando vazamento de dados entre perfis | Média | Alto | `profile_id` como campo obrigatório (não-opcional) em Input dataclass; testes de integração por BC validando isolamento antes do merge; review manual de cada PR de refactor |
| Upgrade breaking de FastAPI Users que altere o contrato interno de ID type | Baixa | Médio | Mapper UUID↔prefixed isolado em uma única classe no SQLAlchemy mapper do BC `identity`; pinned version no Poetry; ajuste pontual quando upgrade ocorrer |
| Frontend desincronizado com backend durante a transição (uma versão merge antes da outra) | Média | Alto | Backend mantém endpoints legados sem profile durante fase de transição via feature flag; release notes de cada PR documenta dependência com versão correspondente do `homeflix-web` |
| Decisão de role binário (`admin` \| `member`) ficar insuficiente conforme produto evolui (ex: `viewer`, `kids-only`) | Média | Baixo | `UserRole` modelado como enum VO, refactorable para RBAC mais granular sem mudar boundary do BC |
| Performance degradada por carregar/validar profile a cada request | Baixa | Baixo | Profile resolvido uma vez por request via FastAPI dependency `Depends(get_current_profile)`, cache implícito do framework no escopo da request |

## Alternativas Consideradas

### 1. Caminho A — Single-Account + Profiles (estilo Netflix puro)

Modelar uma única conta da casa (`Account`) com N perfis aninhados, sem conceito de múltiplos usuários distintos com login próprio.

**Rejeitado porque:** não comporta o caso de uso de compartilhamento extra-doméstico com isolamento real (família/amigos com bibliotecas separadas), não oferece granularidade de role/permissão necessária para o admin panel já planejado, e não fecha portas que o caminho adotado fecha — qualquer evolução futura exigiria refactor cross-cutting do BC inteiro.

### 2. Implementar autenticação do zero (sem FastAPI Users)

Construir signup, login, JWT, reset de senha e verificação de email manualmente.

**Rejeitado porque:** semanas de trabalho para reimplementar capacidades amplamente disponíveis em biblioteca madura, superfície grande para bugs em código de segurança crítico, e zero ganho funcional. Lab de arquitetura não justifica reinventar primitivas resolvidas.

### 3. Pure UUID para User (exceção ao ADR-002)

Aceitar que `User`/`Profile` usem UUID v4 nativo do FastAPI Users, abrindo exceção formal ao ADR-002 só para o BC `identity`.

**Rejeitado porque:** quebra consistência da linguagem ubíqua — clientes da API precisariam saber que IDs de identity são UUIDs e os demais são prefixed, criando carga cognitiva permanente. Exceções a princípios fundamentais de design pagam juros para sempre.

### 4. Pure prefixed ID com custom ID type no FastAPI Users

Configurar FastAPI Users com `ID = str` e usar o prefixed `usr_xxx` direto como PK do banco.

**Rejeitado porque:** tecnicamente viável, mas exige customizar partes internas da lib (transformers, dependency factories) que esperam UUID em assinaturas. Aumenta custo de manutenção em cada upgrade da lib. Wrapper UUID↔prefixed mantém a lib idiomática e isola a tradução em uma camada bem definida.

### 5. SecurityContext via ContextVars / middleware

Armazenar `profile_id` da request em `contextvars.ContextVar` setado por middleware, acessível de qualquer ponto sem propagação explícita.

**Rejeitado porque:** viola o princípio "explicit > implicit" listado como anti-padrão no núcleo de Clean Architecture do projeto. Quebra testabilidade (use cases precisariam de fixture global de contexto), quebra rastreabilidade (`profile_id` deixa de aparecer no log estruturado de cada use case), e introduz bugs sutis sob concorrência async (propagação inconsistente em background tasks e event handlers). O ganho — evitar passar `profile_id` em Input dataclasses — é cosmético; use cases têm 1 ponto de entrada, não há prop drilling real.

### 6. Domain Events + mirror tables para reads cross-BC

Cada BC consumidor (`watch_progress`, `collections`, `preferences`) manteria sua própria tabela de profiles, alimentada via eventos de domínio (`ProfileCreated`, `ProfileUpdated`).

**Rejeitado porque:** over-engineering para MVP. `ProfileLookupPort` (port + ACL síncrona via repository) atende ao requisito atual com complexidade muito menor. Revisitar quando/se `identity` for extraído para serviço separado, que é cenário hipotético sem demanda concreta hoje.

### 7. Serviços de autenticação gerenciados ou SSO self-hosted

Usar Auth0, Clerk, Supabase Auth (managed) ou Keycloak, Authentik (SSO self-hosted) como provedor de identidade.

**Rejeitado porque:** desproporcional ao escopo. Managed services adicionam dependência externa, custo recorrente e latência de rede para um produto que roda em rede doméstica. SSO self-hosted (Keycloak) é mais robusto que necessário — voltado a federar identidade entre múltiplas aplicações corporativas, não a servir uma aplicação única. Ambos contradizem o princípio de auto-hospedagem leve da arquitetura HomeFlix e desviam o foco do propósito de lab arquitetural (não há aprendizado em terceirizar a modelagem de identidade).

## Referências

- **ADRs relacionados**:
  - ADR-002 (Prefixed External IDs) — esta decisão preserva o padrão via mapper UUID↔prefixed
  - ADR-007 (Entidades Imutáveis) — `User` e `Profile` seguem convenção `with_*`
  - ADR-008 (Screaming Architecture) — `identity` entra como novo módulo em `src/modules/`
  - ADR-009 (Cross-BC Read Ports) — `ProfileLookupPort` em `watch_progress`, `collections`, `preferences`
- **Documentação externa**:
  - [FastAPI Users](https://fastapi-users.github.io/fastapi-users/) — biblioteca de autenticação adotada
  - [DDD Reference — Bounded Context](https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf) — Eric Evans, base conceitual da separação User/Profile
- **Padrões aplicados**:
  - Anti-Corruption Layer (ACL) — para reads cross-BC do `Profile`
  - Mapper Pattern — para tradução UUID↔prefixed ID na infra layer

---

## Notas de Implementação

```python
# src/modules/identity/domain/value_objects/user_id.py
class UserId(ExternalId):
    EXPECTED_PREFIX = "usr"

class ProfileId(ExternalId):
    EXPECTED_PREFIX = "prf"


# src/modules/identity/infrastructure/persistence/user_mapper.py
# Mapeia UUID interno (FastAPI Users) <-> external_id prefixed (domain).
# UUID nunca cruza para o domain.
def to_domain(row: UserRow) -> User:
    return User(
        id=UserId(row.external_id),  # usr_xxx
        email=Email(row.email),
        role=UserRole(row.role),
        ...
    )


# src/modules/watch_progress/presentation/dependencies.py
async def get_current_profile(
    token: str = Depends(oauth2_scheme),
    profile_repo: ProfileLookupPort = Depends(Provide[...]),
) -> ProfileContext:
    # 1. Decode JWT -> user_id, profile_id
    # 2. Verify profile.user_id == user_id (ownership check)
    # 3. Return ProfileContext(profile_id=...)
    ...


# Use case recebe profile_id explícito (proibido contextvar).
@dataclass(frozen=True)
class GetContinueWatchingInput:
    profile_id: ProfileId  # campo obrigatório, não-opcional
    limit: int = 20
```

A sequência de PRs implementando esta decisão (foundation do BC `identity` → `ProfileLookupPort` → refactor dos 3 BCs consumidores → library ACL → frontend) é planejada na conversa que motivou este ADR e será detalhada em plan mode antes de cada PR.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-03 | Lucas Cristovam | Criação inicial |
