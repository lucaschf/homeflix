# ADR-011: Authentication Strategy — Server-Side Session via HttpOnly Cookie

**Status:** Proposto
**Data:** 2026-05-03
**Deciders:** Lucas Cristovam
**Technical Story:** Descendente direto do ADR-010 — define a estratégia de transport e storage de sessão para o bounded context `identity` introduzido lá.

---

## Contexto

O ADR-010 introduz o bounded context `identity` e adota FastAPI Users como base de autenticação, mas deixa em aberto **como** as credenciais validadas se tornam contexto de request — qual transport (cookie vs header), qual storage de sessão (stateless JWT vs sessão server-side), e como o cliente persiste o estado de "logado".

A escolha não é trivial porque os trade-offs clássicos da literatura (JWT vs Session) assumem cenários que **não correspondem ao HomeFlix**. Argumentos pró-JWT como "stateless escala horizontalmente sem Redis" ou "BCs em microserviços diferentes podem validar a mesma chave" pressupõem um SaaS multi-tenant rodando em múltiplos pods — o oposto do HomeFlix, que é monólito self-hosted rodando em um único processo na rede doméstica do usuário.

Os fatores que efetivamente importam para esta decisão:

1. **Topologia de deploy**: single-server, single-process, banco local (SQLite em dev, possivelmente PostgreSQL em prod doméstica). Lookups de sessão em DB são sub-milissegundo e não criam pressão arquitetural.
2. **Cliente principal é uma SPA React** (`homeflix-web`). SPAs grandes têm superfície real para XSS — qualquer dependência npm comprometida pode tentar acessar `localStorage`. Tokens em `localStorage` são exfiltráveis; cookies `HttpOnly` não são acessíveis a JavaScript.
3. **Caso de uso doméstico cria demanda real por revogação imediata**. Cenários concretos: "deslogar a TV da sala que ficou com a sessão aberta", "remover acesso de um membro da casa que saiu", "kill switch via admin panel". Com JWT stateless, revogação só acontece na expiração do token (ou exige introduzir blacklist, o que recria stateful por baixo dos panos).
4. **API hoje é privada**, consumida exclusivamente pelo `homeflix-web`. Não há cliente mobile, integração de terceiros ou app desktop separado planejado para o curto prazo.
5. **Complexidade adicional sem benefício concreto é dívida**: refresh tokens, blacklists, rotação de signing key e gestão de exp/iat são custo real de manutenção. Se o ganho que justificaria esse custo (escala stateless, federação cross-service) não se materializa, o saldo é negativo.

Restrições: a decisão precisa ser compatível com o admin panel planejado (que vai expor "ver dispositivos logados" e "revogar sessão"), e não pode fechar a porta para a hipotética introdução futura de cliente mobile (caso em que bearer token em header passa a fazer sentido).

## Decisão

Nós iremos adotar **autenticação por sessão server-side em cookie HttpOnly**, implementada via FastAPI Users com `AuthenticationBackend` configurado como `DatabaseStrategy` + `CookieTransport`.

**Storage de sessão**: tabela `access_tokens` no mesmo banco do BC `identity`, com schema `(token: str primary key, user_id: UUID, created_at: datetime)`. O token é uma string opaca aleatória (32+ bytes, base64url-safe), não um JWT — não carrega claims, é apenas a chave para lookup. **Expiração fixa de 90 dias desde a criação do token**, sem rolling refresh — `DatabaseStrategy` do FastAPI Users não atualiza `created_at` automaticamente em cada acesso, então sessão "slidable" exigiria custom strategy. Para uso doméstico (família re-loga ~4x/ano), expiração fixa é suficiente.

**Transport**: cookie HTTP com nome `homeflix_session`, atributos:

- `HttpOnly` — invisível a JavaScript, mitiga roubo via XSS
- `Secure` — enviado apenas sobre HTTPS (no dev local, configurável via env var)
- `SameSite=Strict` — bloqueia envio em requests cross-site, mitiga CSRF
- `Max-Age` alinhado com a expiração do token (emitido a cada login bem-sucedido)

**Fluxo de revogação**: logout deleta a row de `access_tokens`. Não há janela entre "usuário pediu logout" e "token deixa de ser válido" — é instantâneo. Admin panel futuro consulta a tabela para listar sessões ativas por usuário e oferece operação "revogar dispositivo", que também é apenas `DELETE WHERE token = ?`.

**Fluxo de profile switch** (referente ao ADR-010): a troca de profile **não invalida a sessão** — a sessão pertence ao `User`. O `profile_id` ativo é armazenado em uma segunda coluna `current_profile_id` em `access_tokens`, atualizada via `POST /profiles/{id}/switch` (após validação de ownership). O cookie em si não muda. Cada request resolve `(user, current_profile)` em um único lookup pela `token`.

**CSRF**: a combinação `SameSite=Strict` + CORS configurado com origin allowlist específica do `homeflix-web` é suficiente para o threat model atual. Se no futuro forem adicionados origins múltiplos (ex: app desktop com origem `tauri://`) que exijam relaxar `SameSite`, será necessário introduzir double-submit token CSRF — registrado como decisão diferida.

**Compatibilidade com clientes não-browser** (cenário hipotético: app mobile no futuro): adicionar um segundo `AuthenticationBackend` em paralelo com `BearerTransport` + `JWTStrategy` na biblioteca FastAPI Users, sem alterar nem migrar o backend de cookie atual. Browsers continuam usando cookie, mobile usa bearer. **Esta decisão não fecha essa porta.**

## Consequências

### Positivas

- **Revogação imediata é primitiva, não feature** — `DELETE FROM access_tokens WHERE token = ?` é a operação. Logout, kill switch via admin panel, "deslogar todos os dispositivos" e "remover acesso de membro" são todos a mesma operação SQL com WHERE diferente. Zero complexidade adicional para suportar cada um.
- **Mitigação nativa de XSS** — cookie `HttpOnly` é invisível a JavaScript. Mesmo cenário pessimista de dependência npm comprometida não consegue exfiltrar a sessão.
- **Sem complexidade de JWT** — sem refresh tokens, sem blacklist para revogação, sem rotação de signing key, sem gestão de exp/iat no cliente. O cliente não tem nenhuma responsabilidade sobre o token; o navegador cuida do cookie automaticamente.
- **Multi-device com profiles independentes por device** — armazenar `current_profile_id` na própria sessão permite TV exibir perfil A enquanto celular exibe perfil B, simultaneamente, sem conflito.
- **Lookup barato e atômico** — uma única query resolve `(token → user_id, current_profile_id)` por request. Em DB local, sub-milissegundo.
- **Porta aberta para evolução** — `RedisStrategy` (multi-pod) e `BearerTransport`+`JWTStrategy` (cliente mobile) são adições paralelas, não substituições. Decisão atual não fecha caminhos futuros.

### Negativas

- **Stateful por design** — todo request bate na tabela `access_tokens`. Em DB local single-process é sub-milissegundo, mas é uma operação que JWT stateless não precisaria fazer. Custo aceito conscientemente em troca dos benefícios acima.
- **CSRF precisa atenção contínua** — qualquer mudança futura nas configurações de CORS ou origin allowlist precisa reavaliar se `SameSite=Strict` ainda é suficiente. Se um dia for relaxado, double-submit token CSRF vira obrigatório.
- **Sessão fixa de 90 dias força re-login trimestral** — usuário ativo é deslogado independentemente de uso recente. UX inferior a slidable expiration, mas tolerável para uso doméstico. Slidable foi rejeitada por exigir custom strategy não-nativa do FastAPI Users.
- **Cliente não-browser exige trabalho adicional** — quando/se app mobile entrar no roadmap, é necessário adicionar segundo `AuthenticationBackend` (bearer) em paralelo. Não é refactor, mas é trabalho futuro identificado.
- **DB bloat se cleanup falhar** — `access_tokens` cresce a cada login e só encolhe em logout/revogação/expiração. Sem job de limpeza, sessões expiradas acumulam.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Cookie de sessão interceptado em conexão HTTP não-criptografada | Baixa | Alto | Atributo `Secure` obrigatório em produção (env var); deploy doméstico atrás de TLS (Caddy/Traefik com Let's Encrypt ou self-signed); documentar no setup |
| `access_tokens` cresce indefinidamente por falta de cleanup de sessões expiradas | Média | Baixo | Background job (APScheduler — já em uso) com cleanup periódico de tokens com `created_at + lifetime < now()`; também cleanup oportunístico durante validação de token |
| Token comprometido permanece válido até 90 dias se usuário não fizer logout explícito | Baixa | Médio | Admin panel oferece "revogar todas as sessões do usuário" como mitigação reativa; documentar logout explícito em dispositivos não confiáveis (kiosks, dispositivos compartilhados) como prática recomendada |
| Mudança futura de configuração CORS/origin relaxando `SameSite` reintroduz exposição CSRF | Baixa | Alto | Registrar nas Notas de Implementação que `SameSite=Strict` é load-bearing; checklist de revisão de PRs que tocam config de CORS deve revalidar exposição CSRF |
| `current_profile_id` na sessão fica orfão se profile for deletado pelo user | Média | Baixo | `FOREIGN KEY ... ON DELETE SET NULL` na coluna; `get_current_profile` trata `None` como "precisa selecionar profile" e redireciona para `/profiles` |

## Alternativas Consideradas

### 1. Stateless JWT em header `Authorization: Bearer`

Modelo "JWT puro": servidor assina token com claims (`sub`, `exp`, `iat`, `profile_id`), cliente armazena em `localStorage` (ou memória) e envia em header `Authorization`. Backend valida só pela assinatura, sem hit no DB.

**Rejeitado porque:**

- Tokens em `localStorage` são acessíveis a qualquer script no contexto da SPA — uma dependência npm comprometida (cenário não-hipotético: incidentes recentes de supply chain attack em pacotes JS) consegue exfiltrar a sessão. HttpOnly cookies eliminam essa classe inteira de ataque.
- Revogação imediata, que é requisito real do produto (kill switch, "deslogar TV", remoção de membro da casa), exige introduzir blacklist server-side — o que reintroduz statefulness pelos fundos sem dar nenhum dos benefícios reais de "ser stateful por design" (controle, simplicidade, observabilidade).
- A vantagem central de JWT (validação stateless, sem DB lookup) só se materializa em arquiteturas multi-instância ou multi-serviço. HomeFlix é monólito single-process — o "ganho" não existe na topologia real.

### 2. JWT em HttpOnly cookie

Variação do anterior onde o JWT é entregue via cookie `HttpOnly` em vez de exposto ao JavaScript. Resolve o problema de XSS mantendo a validação por assinatura.

**Rejeitado porque:**

- Mantém todo o overhead operacional do JWT (refresh tokens, rotação de signing key, gestão de exp/iat, blacklist para revogação imediata) sem usar a vantagem que justifica esse overhead. Como sempre vai haver hit no DB (para revogação ou para validar `is_active` do user), não há economia real de I/O.
- Em um BC monolítico onde "validar sessão" e "carregar user" acontecem na mesma transação, a diferença de custo entre `SELECT FROM access_tokens WHERE token = ?` e `verify_signature(jwt) + SELECT FROM users WHERE id = ?` é nula. O JWT só adiciona complexidade.
- Trade-off entre complexidade adicional e benefício concreto é claramente negativo na topologia atual.

### 3. Sessão server-side em Redis + HttpOnly cookie

Mesma estratégia escolhida (`DatabaseStrategy` + `CookieTransport`) mas com Redis como storage do token de sessão em vez de tabela em DB relacional.

**Rejeitado porque:**

- Adiciona uma dependência de infraestrutura nova ao stack (Redis), sem benefício correspondente na topologia atual. Lookup em SQLite/PostgreSQL local com PK indexada já é sub-milissegundo — Redis não move a agulha em latência percebida.
- Custo de operação: usuário doméstico passa a precisar manter Redis rodando, configurar persistência (ou aceitar perda de sessões em restart), monitorar duas instâncias de armazenamento. Para zero ganho prático.
- Migração futura é trivial: FastAPI Users tem `RedisStrategy` com a mesma interface de `DatabaseStrategy` — se um dia HomeFlix rodar em múltiplos processos ou demandar throughput maior, troca-se a strategy em uma linha. Não há razão para pré-otimizar agora.

## Referências

- **ADRs relacionados**:
  - ADR-010 (Identity Bounded Context) — esta decisão complementa ADR-010 definindo o transport e storage de sessão para o BC `identity` introduzido lá
  - ADR-002 (Prefixed External IDs) — `access_tokens.token` é secret opaco, não identificador de domínio; não segue o padrão `prefix_xxx` (e nunca deve ser exposto em logs ou rotas)
- **Documentação externa**:
  - [FastAPI Users — Authentication Backends](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/) — documentação de `Strategy` e `Transport`
  - [FastAPI Users — DatabaseStrategy](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/database/) — strategy adotada
  - [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — boas práticas de cookies de sessão (HttpOnly, Secure, SameSite)
- **Padrões aplicados**:
  - Server-side session storage (clássico, anterior ao JWT)
  - Defense in depth — `HttpOnly` + `Secure` + `SameSite=Strict` em camadas

---

## Notas de Implementação

**Schema da tabela `access_tokens`** (BC `identity`):

```python
# src/modules/identity/infrastructure/persistence/access_token_model.py
class AccessTokenModel(Base):
    __tablename__ = "access_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    current_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

**Configuração do `AuthenticationBackend`**:

```python
# src/modules/identity/infrastructure/auth/backend.py
cookie_transport = CookieTransport(
    cookie_name="homeflix_session",
    cookie_max_age=60 * 60 * 24 * 90,    # 90 dias fixos desde a emissão
    cookie_secure=settings.is_production,  # True em prod, configurável em dev
    cookie_httponly=True,
    cookie_samesite="strict",
)

def get_database_strategy(
    access_token_db: AccessTokenDatabase = Depends(get_access_token_db),
) -> DatabaseStrategy:
    return DatabaseStrategy(
        database=access_token_db,
        lifetime_seconds=60 * 60 * 24 * 90,  # alinhado com cookie
    )

auth_backend = AuthenticationBackend(
    name="cookie-session",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)
```

**Profile switch** (atualiza `current_profile_id` na sessão atual sem reemitir cookie):

```python
# src/modules/identity/application/use_cases/switch_profile.py
@dataclass(frozen=True)
class SwitchProfileInput:
    user_id: UserId
    target_profile_id: ProfileId
    session_token: str

class SwitchProfileUseCase:
    async def execute(self, input: SwitchProfileInput) -> None:
        profile = await self._profile_repo.get(input.target_profile_id)
        if profile.user_id != input.user_id:
            raise ProfileOwnershipViolation(input.user_id, input.target_profile_id)
        await self._access_token_repo.update_current_profile(
            input.session_token, input.target_profile_id,
        )
```

**Cleanup de sessões expiradas** (job APScheduler em `src/infrastructure/scheduling/`):

```python
# Roda diariamente às 3am
async def cleanup_expired_sessions(repo: AccessTokenRepository) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=settings.session_lifetime_seconds)
    return await repo.delete_older_than(cutoff)
```

**Compatibilidade futura com OAuth providers** (Google, GitHub, etc.): o schema do `User` permite `hashed_password` opcional, e FastAPI Users suporta nativamente vincular `User` a `OAuthAccount`. Adicionar provider externo no futuro **não exige nenhuma mudança neste ADR** — a sessão emitida no callback OAuth usa exatamente o mesmo `auth_backend` (`DatabaseStrategy` + `CookieTransport`).

**Compatibilidade futura com cliente não-browser** (mobile, desktop): adicionar segundo backend em paralelo, ambos ativos:

```python
fastapi_users = FastAPIUsers[User, UUID](
    user_manager_dependency,
    [auth_backend, bearer_jwt_backend],  # cookie e bearer coexistem
)
```

Browsers continuam autenticando via cookie; clients que não suportam cookies (ex: mobile nativo) usam bearer JWT. Decisão diferida para o momento em que primeiro cliente não-browser aparecer.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-03 | Lucas Cristovam | Criação inicial |
