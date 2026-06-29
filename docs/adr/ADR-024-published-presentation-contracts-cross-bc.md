# ADR-024: Contratos de Presentation Publicados para Imports Cross-BC

**Status:** Aceito
**Data:** 2026-06-29
**Deciders:** Lucas
**Technical Story:** Backlog 6.11 (`docs/audits/07-phase6-backlog.md`) — achado clean-arch B-9/B-10 + coupling F9: `resolve_profile_id` reusado por import direto cross-BC em 4 módulos.

---

## Contexto

ADR-008 estabelece que **módulos não importam uns aos outros**; leituras cross-BC passam por Read Port + ACL (ADR-009). ADR-010 reafirma que esses princípios valem para o `identity` **"sem exceção"**.

Há, porém, uma dependência cross-BC que não se encaixa nesse mecanismo: a resolução de **"quem é o caller"** na borda HTTP. `identity.presentation.dependencies.resolve_profile_id` é uma dependency do FastAPI que lê o cookie de sessão, consulta `access_tokens` e devolve o `profile_id` ativo (ADR-010/011). Toda rota autenticada de `media`, `collections`, `watch_progress` e `preferences` precisa dela.

Essa dependência **não pode** ser expressa pelo padrão do ADR-009: port + ACL governa leitura de **domínio/aplicação**, e não existe port de domínio capaz de carregar um `Request` do FastAPI. Também **não pode** descer para `building_blocks`/`shared_kernel`: ela depende de infra e domain do `identity` (settings, repo de `access_tokens`, erros de domínio), o que inverteria a regra de dependência (`modules → shared_kernel → building_blocks`).

Na prática os 4 BCs já importavam `resolve_profile_id` cross-BC — mas de `identity.presentation.dependencies`, um módulo cuja superfície **mistura** o contrato com símbolos internos do `identity` (`get_current_profile`, `ProfileContext`, o resolver de UoW). Consumir um módulo de superfície mista acopla mais do que o necessário e expõe os 4 BCs a churn interno do `identity`.

## Decisão

Nós permitiremos imports cross-BC de presentation **exclusivamente através de um módulo de contrato publicado** `<módulo>/presentation/public.py`. Esse módulo declara, via `__all__`, a única superfície que outros bounded contexts podem importar; todo o resto de `presentation/` é interno e não deve ser importado cross-BC.

O `identity` publica `resolve_profile_id` em `identity/presentation/public.py`. Os 4 BCs consumidores importam dele (através do seu shim local `presentation/dependencies.py`), nunca de `identity.presentation.dependencies`.

Isto é uma **exceção estreita e documentada** ao ADR-008, restrita a **primitivas de presentation/auth que não podem ser expressas como port de domínio** (ADR-009). Não abre exceção para reads de domínio cross-BC — esses continuam via port + ACL, sem mudança.

## Consequências

### Positivas

- A superfície de acoplamento cross-BC fica explícita e mínima (um símbolo nomeado), em vez de reaproveitar um módulo de superfície mista.
- O contrato funciona como *firewall de volatilidade*: o `identity` refatora `presentation/dependencies.py` livremente sem ripple nos 4 consumidores, desde que `public.py` permaneça estável.
- A exceção a "ADR-008 sem exceção" (ADR-010) passa a ser *discoverable* na base de ADRs, não escondida num docstring.

### Negativas

- Existe um import cross-BC sancionado (presentation → presentation de outro módulo) — uma exceção que precisa ser conhecida ao ler ADR-008/010.
- A cadeia de re-export tem hops (`dependencies.py → public.py → shim do BC → routes`); o shim por BC permanece um re-export puro até que algum override por BC se materialize.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Um BC importar `identity.presentation.dependencies` direto, furando o contrato | Média | Baixo | Convenção documentada + `__all__` em `public.py`; teste de contrato fixa a identidade do símbolo; regra de import-linter pode ser adicionada se recorrer |
| O padrão `public.py` ser usado para vazar lógica de domínio entre BCs | Baixa | Médio | Escopo explícito: só primitivas de presentation/auth sem port de domínio possível; reads de domínio continuam ADR-009 |

## Alternativas Consideradas

### 1. Read Port + ACL (ADR-009)

Cada BC define um port e um adapter para resolver o profile.

**Rejeitado porque:** ADR-009 governa reads de domínio/aplicação; `resolve_profile_id` é uma dependency de request-context na borda HTTP — não há port de domínio capaz de carregar um `Request`.

### 2. Mover para `building_blocks`/`shared_kernel`

Tornar a dependency um utilitário de presentation compartilhado.

**Rejeitado porque:** ela depende de infra e domain do `identity`; movê-la inverteria a regra de dependência (`building_blocks` não pode importar um módulo).

### 3. Cada BC reimplementar a resolução

Cada consumidor lê o cookie e consulta `access_tokens` por conta própria.

**Rejeitado porque:** duplica conhecimento de auth do `identity` em 4 lugares (Shotgun Surgery a cada mudança de cookie/sessão).

### 4. Apenas docstring (sem ADR)

Documentar a exceção só no `public.py`.

**Rejeitado porque:** ADR-010 afirma "ADR-008/009 sem exceção"; uma exceção real precisa ser visível a quem trata ADRs como fonte da verdade. Há precedente (revisão do ADR-009 em 2026-06-27 para a variante "Protocol port sem adapter").

## Referências

- ADR-008 (Screaming Architecture — módulos isolados) — qualificado por esta decisão
- ADR-009 (Cross-BC Read Ports) — continua para reads de domínio
- ADR-010 (Identity Bounded Context) — a afirmação "sem exceção" passa a ter esta exceção estreita
- ADR-011 (Authentication Strategy) — origem de `resolve_profile_id`
- `docs/audits/07-phase6-backlog.md` (item 6.11)

---

## Notas de Implementação

```python
# src/modules/identity/presentation/public.py — o contrato publicado
from src.modules.identity.presentation.dependencies import resolve_profile_id

__all__ = ["resolve_profile_id"]

# src/modules/<bc>/presentation/dependencies.py — shim local do consumidor
from src.modules.identity.presentation.public import resolve_profile_id

__all__ = ["resolve_profile_id"]
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-29 | Lucas | Criação inicial |
