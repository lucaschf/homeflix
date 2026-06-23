# ADR-022: Subscriptions Multi-Usuário + Fanout em Catalog Requests

**Status:** Aceito
**Data:** 2026-06-23
**Deciders:** Lucas Cristovam
**Technical Story:** Feature "Catalog requests / Avisar quando chegar / Em breve" (handoff em `specs/design_handoff_catalog_requests/`). Habilitar página consumer "Em breve", contagem de inscritos, e o aviso "já disponível" para todos. Branch `feat/catalog-requests-subscriptions`.

---

## Contexto

O bounded context `catalog_requests` modela hoje **uma linha por título**: `CatalogRequest` é keyed por `(tmdb_id, media_type)` e carrega um **único** `requester_user_id` + um booleano `notify_on_arrival`. Quando o título entra no catálogo, o `OnMediaEnrichedHandler` reage ao `MediaEnrichedEvent`, casa o pedido pendente por `(tmdb_id, media_type)` exato, marca `fulfilled_at` e — **só** se `notify_on_arrival` e `requester_user_id` estiverem setados — publica **uma** notificação `catalog_request_fulfilled` para esse único usuário.

A regra `reconcile` é "first-owner-wins": se um segundo usuário pede o mesmo título, o pedido existente é reconciliado mas o `requester_user_id` **continua sendo o primeiro**. Consequência: num household multi-usuário, **apenas o primeiro solicitante é avisado quando o título chega** — os demais interessados ficam de fora silenciosamente. É um bug latente do modelo single-owner.

O redesign de UI (handoff) pressupõe um sistema multi-inscrito: contagem de "{N} pessoas aguardando", coluna "Inscritos" no admin, e a ação "Marcar como incluído" que "notifica todos os inscritos de uma vez". Nenhuma dessas três coisas é representável no modelo atual de 1-linha-com-1-dono.

## Decisão

Vamos **separar "o título está na fila" de "quem quer ser avisado"**, introduzindo subscriptions por-usuário com fanout.

1. **`CatalogSubscription` como agregado próprio** (id `csub_xxx`), referenciando `request_id` + `user_id`, com invariante de unicidade por `(request_id, user_id)`. **Não** é coleção dentro do `CatalogRequest` — manter o agregado-raiz pequeno e a relação um-para-muitos como query de repositório (`count_by_request`, `list_for_user`, `exists`, `add`, `remove`).

2. **`CatalogRequest` continua sendo "o título na fila"** (a peça que o admin gerencia). O campo `requester_user_id` muda de semântica: deixa de ser o alvo da notificação e passa a ser **atribuição de origem** (quem primeiro colocou na fila) — alimenta `source` e `requestedBy`.

3. **Fanout:** tanto o `OnMediaEnrichedHandler` (chegada automática) quanto o "Marcar como incluído" manual iteram as subscriptions do request e publicam **uma notificação por inscrito**.

4. **`source: user | household`** vira campo do `CatalogRequest`, derivado na criação: pedido iniciado por um membro = `user` (com `requester_user_id`); criado pelo sistema/flag da casa = `household`.

5. **Status honesto/fino:** o status exposto é **derivado de `fulfilled_at`** (`pendente` / `disponível`), não um enum de pipeline. Os estados `processing`/`waiting_file`/`matching` do handoff descrevem um pipeline que o sistema **não rastreia** — seriam fictícios e enganosos. Ficam de fora; há espaço para um `preso` derivado no futuro (pendente + título já no catálogo sob outro tmdb_id).

6. **Unsubscribe** passa a existir (remover a subscription). O `CatalogRequest` **persiste mesmo com zero subscriptions** — a fila é sobre títulos a caminho, independente de interesse de aviso. O booleano `notify_on_arrival` é aposentado: "estar inscrito" = existir uma subscription.

## Consequências

### Positivas

- Corrige o bug latente: **todos** os interessados num household são avisados quando o título chega.
- Habilita contagem de inscritos, social proof e "notificar todos" — base para a página "Em breve" e a página admin redesenhada.
- Unsubscribe possível (o modelo one-way atual não permitia desligar o aviso).
- Separação limpa título-vs-interesse: agregados pequenos, queries diretas por `user_id`/`request_id`, sem agregado ilimitado.
- Status derivado é honesto — a UI não promete granularidade de pipeline que o backend não tem.

### Negativas

- Nova tabela `catalog_subscriptions` + migration **com backfill** (cada request existente com `notify_on_arrival=true` + `requester_user_id` vira 1 subscription).
- Fanout gera N notificações por chegada (N pequeno no contexto doméstico — custo desprezível, mas é mais trabalho que 1).
- Mais superfície: novos use cases (subscribe/unsubscribe/include/contagens), novos endpoints, novo agregado e repositório.
- A coluna "Status" do admin fica de baixo valor no v1 (quase tudo "pendente") — aceito conscientemente em troca de honestidade.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Backfill perder/duplicar subscriptions na migração | Média | Médio | Migration idempotente derivando 1 sub por request elegível; teste de integração do backfill |
| Pedido órfão (tmdb_id diferente no enrich) nunca casa → inscritos nunca avisados | Média | Médio | Ação manual "Marcar como incluído" como resgate; futuro: re-tentar casar pendências no relink |
| Volume de notificações no fanout | Baixa | Baixo | Contexto doméstico (poucos usuários); publish já é fire-and-forget |

## Alternativas Consideradas

### 1. Manter single-owner (não fazer nada)

Continuar com 1 `requester_user_id` por título.

**Rejeitado porque:** mantém o bug multi-usuário e não suporta contagens/fanout/"notificar todos" que o redesign exige.

### 2. Subscriptions como coleção dentro do agregado `CatalogRequest`

Carregar todas as subscriptions junto com o request.

**Rejeitado porque:** vira agregado **ilimitado** — um título popular força carregar todas as subscriptions só pra adicionar/remover uma, e contagem exige materializar a coleção inteira. Viola "agregados pequenos".

### 3. Reshape em linhas por-`(user, título)` (sem entidade de request separada)

Cada (usuário, título) é uma linha; a fila é o group-by.

**Rejeitado porque:** os metadados do título (`source`, `fulfilled_at`, status) ficam duplicados/ambíguos entre linhas, e a fila admin é inerentemente por-título — o group-by complica leitura e arquivamento.

### 4. Status de pipeline completo (`processing`/`waiting_file`/`matching`)

**Rejeitado porque:** nada no backend rastreia esses estados; exporiam granularidade fictícia. Status derivado de `fulfilled_at` é o que o sistema honestamente sabe.

## Referências

- Handoff de design: `specs/design_handoff_catalog_requests/README.md`
- ADR-009 Cross-BC Read Ports + ACL (padrão do `NotificationPublisherPort` usado no fanout)
- ADR-018 Identificadores de Domínio como Value Objects nas Fronteiras (id do novo agregado)
- ADR-002 Prefixed External IDs (`csub_xxx`)

---

## Notas de Implementação

```
Tabela catalog_subscriptions:
  id            INTEGER PK
  external_id   VARCHAR  ("csub_xxx")
  request_id    VARCHAR  FK → catalog_requests.external_id  (index)
  user_id       VARCHAR  (index)
  created_at    DateTime(tz)
  deleted_at    DateTime(tz) NULL
  UNIQUE(request_id, user_id) WHERE deleted_at IS NULL   -- parcial (convenção do projeto)

Fanout (OnMediaEnrichedHandler + IncludeCatalogRequestUseCase):
  subs = subscription_repo.list_for_request(request_id)
  for sub in subs:
      publisher.publish(CatalogArrivalNotification(recipient_user_id=sub.user_id, ...))

Backfill (migration):
  para cada catalog_request com notify_on_arrival = TRUE e requester_user_id IS NOT NULL:
      INSERT catalog_subscriptions(request_id, user_id=requester_user_id, ...)
```

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-23 | Lucas Cristovam | Criação inicial |
