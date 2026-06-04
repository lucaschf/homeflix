# ADR-017: Invariantes de domínio na camada de domínio

**Status:** Aceito
**Data:** 2026-06-04
**Deciders:** Lucas Cristovam
**Technical Story:** Revisão de code smells (Fase 3) — invariantes de negócio implementadas (e duplicadas) na application layer em vez do domínio.

---

## Contexto

Duas invariantes de negócio vivem hoje na application layer, fora do domínio:

**1. "Sempre ao menos um admin ativo" (Identity)**

O guard contra remover o último admin estava **duplicado** em dois use cases, com mensagens já divergentes entre si:

- `update_user_role.py` — `"Cannot demote the last active admin — promote another user first."`
- `delete_admin_user.py` — `"Cannot delete the last active admin — promote another user first."`

A entidade `User` já possui `deactivate()` (`user.py:90`), ainda sem use case correspondente. Quando o endpoint de desativação for criado, nada força o autor a lembrar do guard — um esquecimento produz **admin lockout**: o sistema fica sem nenhum usuário capaz de administrar (criar usuários, gerenciar bibliotecas, settings), exigindo correção manual no banco.

**2. "Máximo de 10 listas por profile" (Collections)**

O check de `MAX_LISTS` vivia no use case (`create_custom_list.py`), enquanto o limite irmão `MAX_ITEMS_PER_LIST` é imposto **dentro** do aggregate (`CustomList.increment_item_count`). A mesma classe de regra — limite numérico do aggregate — vivia em camadas diferentes, sem critério.

**Característica comum:** ambas são invariantes *set-level* — dependem de um fato **contado pelo repositório** (quantos admins ativos, quantas listas do profile), não do estado interno de uma única instância. Foi por isso que historicamente escorregaram para o use case: o domínio não tem acesso ao repositório.

## Decisão

Nós iremos **manter invariantes de negócio na camada de domínio**, mesmo quando dependem de um fato derivado do repositório. O padrão é **fato derivado como parâmetro**: a application layer busca a contagem; o domínio recebe o número e **decide**.

Dois mecanismos, conforme o escopo da invariante:

1. **Domain service** quando a invariante atravessa múltiplas operações. `AdminQuorum.ensure_can_remove_admin(user, active_admin_count)` (`identity/domain/services/admin_quorum.py`) é chamado por todo path que remove acesso admin — demote, delete e, futuramente, deactivate. É no-op para não-admins, então os callers o invocam incondicionalmente no path de remoção. Mensagem e `message_code` passam a ter fonte única.

2. **Factory do aggregate** quando a invariante guarda a criação. `CustomList.create(profile_id, name, *, existing_count)` recebe a contagem como **keyword-only obrigatório** — é impossível construir via factory sem fornecer o fato, eliminando o bypass por omissão. Alinha o aggregate ao seu próprio padrão (`MAX_ITEMS_PER_LIST` já era imposto internamente).

**O que permanece no use case:** orquestração, busca das contagens (`count_active_admins()`, `custom_lists.count(profile_id)`) e checks que exigem query além de contagem — a unicidade de nome de lista (`find_by_name`) continua na application por ora; movê-la exigiria o mesmo padrão (`name_taken: bool`) sem dano concreto hoje que o justifique.

## Consequências

### Positivas

- Cada invariante tem **fonte única**: uma mensagem, um `message_code`, um lugar para mudar a regra.
- Paths futuros ficam protegidos por construção: o deactivate use case chamará o mesmo `AdminQuorum`; nenhuma lista é criável via factory sem o check de limite.
- As invariantes viram **unit tests puros** (sem mock de repositório): `AdminQuorum` e o limite do `CustomList.create` testados direto no domínio.
- `CustomList` fica internamente consistente — os dois limites numéricos do aggregate vivem no aggregate.

### Negativas

- O parâmetro obrigatório adiciona ruído nos testes: ~38 call sites de `CustomList.create` atualizados com `existing_count=0`.
- O domínio **confia** no fato passado pela application — um caller que informe contagem errada burla a regra (mitigado pelo keyword-only explícito e testes de contrato dos use cases).
- O fato derivado pode estar defasado no momento do commit (TOCTOU — ver Riscos).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| TOCTOU: duas requests concorrentes leem a mesma contagem e ambas passam (ex.: dois deletes simultâneos dos dois últimos admins) | Baixa | Médio | Janela **pré-existente** — o check no use case tinha exatamente a mesma corrida; app doméstico com pouquíssimos usuários concorrentes; correção definitiva (lock/constraint) só se o dano se materializar |
| Novo path que remove acesso admin esquece de chamar `AdminQuorum` | Média | Alto | Docstring do serviço enumera os paths (demote/delete/deactivate); revisão de PR cobra o guard em mudanças no Identity |
| Caller passa `existing_count` incorreto | Baixa | Médio | Keyword-only obrigatório torna o argumento consciente; testes do use case verificam que a contagem do repositório é a passada |

## Alternativas Consideradas

### 1. Manter os checks nos use cases (status quo)

**Rejeitado porque:** a duplicação já havia divergido (duas mensagens para a mesma regra) e o custo do esquecimento é alto e silencioso (admin lockout). O sintoma é Shotgun Surgery: mudar a regra exige caçar todos os use cases que a copiaram.

### 2. Passar o repositório para o domínio

Domain service recebendo `UserRepository` e contando internamente.

**Rejeitado porque:** o domínio é puro e síncrono; injetar uma interface async de repositório acopla o domínio à infraestrutura e quebra a regra de dependência (ADR-008). O fato derivado como parâmetro preserva a pureza com o mesmo poder de decisão.

### 3. Constraint no banco

Impor "count ≤ N por profile" / "ao menos 1 admin" no schema.

**Rejeitado porque:** nenhuma das duas é expressável como constraint declarativa portátil (SQLite e PostgreSQL); exigiria triggers — regra de negócio escondida na infraestrutura, invisível para o domínio e para os testes unitários.

## Referências

- ADR-008 — Screaming Architecture com Módulos (regra de dependência; domínio puro)
- ADR-010 — Identity Bounded Context (modelo two-tier ADMIN/MEMBER)
- PR #253 — `refactor(identity): extract AdminQuorum domain service`
- Revisão de code smells de maio/2026 (Fase 3 do plano de remediação)

---

## Notas de Implementação

O padrão "fato derivado como parâmetro", nos dois mecanismos:

```python
# Domain service — invariante atravessa operações (demote/delete/deactivate)
class AdminQuorum:
    @staticmethod
    def ensure_can_remove_admin(user: User, active_admin_count: int) -> None:
        if user.role is UserRole.ADMIN and active_admin_count <= 1:
            raise CannotDemoteLastAdminError(
                message="Cannot remove the last active admin — promote another user first.",
            )

# Use case: busca o fato, domínio decide
admin_count = await uow.users.count_active_admins()
AdminQuorum.ensure_can_remove_admin(user, admin_count)
```

```python
# Factory — invariante guarda a criação; keyword-only impede bypass por omissão
@classmethod
def create(
    cls, profile_id: ProfileId, name: str | ListName, *, existing_count: int
) -> CustomList:
    if existing_count >= MAX_LISTS:
        raise BusinessRuleViolationException(
            message=f"Cannot create more than {MAX_LISTS} custom lists",
            message_code="CUSTOM_LIST_LIMIT_EXCEEDED",
            rule_code="CUSTOM_LIST_LIMIT_EXCEEDED",
        )
    return cls(id=ListId.generate(), profile_id=profile_id, name=name, item_count=0)
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-04 | Lucas Cristovam | Criação inicial (Proposto) |
| 2026-06-04 | Lucas Cristovam | Aceito |
