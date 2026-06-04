# ADR-019: Invariantes de contagem/limite moram no domínio

**Status:** Proposto
**Data:** 2026-05-31
**Deciders:** Lucas Cristovam
**Technical Story:** Revisão de code smells (Fase 3) — regras de invariante (quórum de admin, limite de listas) implementadas como `if` espalhados em use cases, já divergindo entre si.

---

## Contexto

Várias regras de negócio do tipo "não ultrapasse N" ou "não fique abaixo de N" estão implementadas diretamente nos use cases, fora do domínio:

- **Quórum de admin** — "o sistema sempre mantém ≥ 1 admin ativo". A guarda está copiada em dois use cases:
  - `UpdateUserRoleUseCase`: dispara quando `user.role != new_role and user.role == ADMIN` e `count_active_admins() <= 1`.
  - `DeleteAdminUserUseCase`: dispara quando `user.role == ADMIN` e `count_active_admins() <= 1`.

  As duas levantam o mesmo `CannotDemoteLastAdminError`, mas com **condições e mensagens diferentes** ("Cannot demote…" vs "Cannot delete…"). A entidade `User.deactivated()` existe e **não tem a guarda** — no dia em que um use case de desativação for criado, o autor quase certamente esquecerá de re-implementá-la, abrindo lockout por um terceiro caminho.

- **Limite de listas** — "no máximo 10 listas customizadas por profile". A checagem mora em `CreateCustomListUseCase` (`if current_count >= MAX_LISTS: raise`), enquanto o limite *irmão* (itens por lista, `MAX_ITEMS_PER_LIST`) é protegido **dentro** do agregado em `CustomList.increment_item_count`. Tratamento inconsistente de duas invariantes da mesma agregação: qualquer novo caminho de criação (import em lote, seed, migração) ignora o teto silenciosamente.

### Dano concreto

O quórum de admin é uma regra cujo furo causa **lockout administrativo** (ninguém consegue administrar o sistema). Tê-la duplicada e já divergida, com um caminho (`deactivate`) sem cobertura, é o pior eixo de dano deste subsistema. O limite de listas é mais brando (overflow silencioso de uma coleção), mas o padrão é o mesmo: invariante de agregação decidida fora do agregado.

## Decisão

Nós iremos **mover invariantes de contagem/limite para o domínio**, num **domain service** ou numa **factory/método do agregado** que recebe a contagem como entrada — nunca num `if` solto no use case.

1. **A contagem é responsabilidade do repositório; a regra é do domínio.** O use case busca o número (`count_active_admins()`, `count_lists_for_profile()`) e o passa para o ponto de domínio que decide. O domínio não acessa o repositório (mantém a regra de dependência), mas é o dono único da regra.

2. **Quórum de admin → domain service `AdminQuorum`.** Um service stateless com `ensure_can_remove_admin(user, active_admin_count)` que levanta `CannotDemoteLastAdminError` quando `user` é o último admin ativo. Chamado por **todo** caminho que retira acesso de admin: demote-para-member, delete e (quando existir) deactivate. Mensagem e código únicos.

3. **Limite de listas → factory de domínio `CustomList.create(profile_id, name, existing_count)`.** Espelha `increment_item_count`: a factory recebe a contagem atual e recusa a criação além de `MAX_LISTS`. O use case continua buscando o count, mas a regra mora no agregado.

4. **Diretriz geral.** Toda regra "não passe de N / não fique abaixo de N" sobre um agregado mora numa factory/método do agregado ou num domain service que recebe a contagem — nunca replicada em use case. Um segundo call-site herda a regra automaticamente, em vez de re-implementá-la (e divergir).

## Consequências

### Positivas

- Fonte única para cada invariante; a divergência atual de mensagem/condição desaparece.
- Um novo caminho (deactivate, import em lote) que esqueça a regra é um bug óbvio de "não chamou o guard", não uma regra silenciosamente ausente.
- A regra fica testável isoladamente (sem mocks de UoW) ao receber a contagem como parâmetro.

### Negativas

- O use case ainda precisa buscar a contagem antes de chamar o guard — a regra não é 100% auto-contida no domínio (o domínio não pode contar sozinho sem violar a direção de dependência). É um trade-off consciente: a *decisão* é do domínio, a *consulta* é da aplicação.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Use case esquece de chamar o guard de domínio | Média | Alto (lockout) | Guard único e nomeado; teste por use case que cobre o caminho; revisão checa "toda remoção de admin chama AdminQuorum" |
| Condição de corrida no count (TOCTOU) entre `count_active_admins()` e o write | Baixa | Médio | Já existente hoje; fora do escopo desta ADR (resolvível com constraint/serialização no banco se virar problema) |

## Alternativas Consideradas

### 1. Manter a guarda no use case, só extrair um helper de aplicação

Função utilitária na camada de aplicação chamada pelos dois use cases.

**Rejeitado porque:** a regra é de domínio (quórum de admin é invariante de negócio), não de orquestração. Um helper de aplicação não é descoberto por quem trabalha no domínio e repete o erro de "regra longe do conceito".

### 2. Colocar o count dentro do agregado

`User.demote()` consultaria o repositório para contar admins.

**Rejeitado porque:** viola a direção de dependência (domínio → infra). O agregado não deve conhecer o repositório. Passar a contagem como argumento preserva a regra no domínio sem o acoplamento.

## Referências

- ADR-008 — Screaming Architecture (direção de dependência)
- ADR-010 — Identity Bounded Context (User/quórum de admin)

---

## Notas de Implementação

```python
class AdminQuorum:
    @staticmethod
    def ensure_can_remove_admin(user: User, active_admin_count: int) -> None:
        if user.role is UserRole.ADMIN and active_admin_count <= 1:
            raise CannotDemoteLastAdminError(
                message="Cannot remove the last active admin — promote another user first.",
            )

# Use case (delete / demote / future deactivate) — a regra é a mesma:
admin_count = await uow.users.count_active_admins()
AdminQuorum.ensure_can_remove_admin(user, admin_count)
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-05-31 | Lucas Cristovam | Criação inicial (Proposto) |
