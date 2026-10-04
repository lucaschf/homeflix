# ADR-038: Orçamento de Tempo, Retry-After e Retry nas Chamadas ao TMDB

**Status:** Aceito
**Data:** 2026-10-04
**Deciders:** Lucas Cristovam
**Technical Story:** Enriquecimento em massa contra um TMDB degradado (lento, com 5xx intermitente e `429`).

---

## Contexto

O enriquecimento em massa (`BulkEnrichMetadataUseCase`) percorre filmes e séries em sequência. Cada item dispara várias chamadas ao TMDB: busca, segunda busca com o título limpo, detalhes, traduções, logos. A ACL do TMDB (ADR-009) já traduzia bem cada falha: `429` vira `GatewayRateLimitException` com `retry_after_seconds`, timeout vira `GatewayTimeoutException`, e "não encontrado" volta como `None`. O problema estava em quem usava essa tradução:

1. **Nenhum orçamento de tempo, em nenhum nível.** O cliente usava `httpx.AsyncClient(timeout=30.0)`, mas no httpx esse valor limita cada fase separadamente. O limite de leitura conta o tempo *entre dois pedaços* da resposta, não o total. Uma resposta que pinga um byte a cada 29 segundos nunca estoura, e por isso uma chamada não tinha limite superior. Nem o item nem o lote tinham.
2. **O `429` era tratado como erro de item.** O laço do lote capturava `Exception`, registrava um erro e seguia. Depois do primeiro `429`, todos os itens seguintes recebiam `429` quase na hora. O lote queimava a biblioteca inteira em segundos e terminava como "sucesso", enquanto o `Retry-After` que a ACL tinha preservado era descartado. Uma pausa de poucos segundos teria salvado o lote.
3. **Falha transitória e resposta definitiva viravam a mesma coisa.** Para o lote, "o TMDB não respondeu" e "o TMDB não conhece este título" eram ambos "erro". Não havia como decidir parar.
4. **I/O remoto com a transação aberta.** `EnrichMovieMetadataUseCase` e `EnrichSeriesMetadataUseCase` chamavam o TMDB dentro do `async with uow`. Com o provider lento, o item segurava uma conexão do banco durante toda a chamada externa. Qualquer cancelamento por tempo cairia no meio de uma transação.

## Decisão

Nós iremos separar **quem conhece o protocolo do provider** de **quem decide quanto esperar**, seguindo o princípio da ACL: a borda traduz, a aplicação decide.

### 1. Orçamento declarado por quem chama (`building_blocks/application/deadline.py`)

Quem inicia o trabalho declara o orçamento: `async with deadline(60): ...`. O código de infraestrutura consulta `remaining_seconds()` para limitar cada espera, cada nova tentativa e cada chamada ao que sobrou. Escopos aninhados só podem encurtar o orçamento.

**O orçamento não cancela nada.** Ele limita quanto o *provider* pode segurar quem chama, não o trabalho local. Uma versão anterior deste desenho usava `asyncio.timeout`, e a revisão mostrou o problema: o cancelamento podia cair no segundo UoW ou no `publish` do `MediaEnrichedEvent`. O resultado seria um título com `tmdb_id` gravado e sem o evento publicado, que nenhuma execução sem `force` publicaria de novo.

**Fora de qualquer escopo não existe orçamento, e a infraestrutura não espera nem retenta.** Esse é o default seguro para requisições interativas: uma busca na tela de admin falha rápido em vez de ficar presa atrás do lote.

| Quem chama | Orçamento |
|---|---|
| `BulkEnrichMetadataUseCase`, por item | 60 s (`ITEM_BUDGET_SECONDS`) |
| `BulkEnrichMetadataUseCase`, lote inteiro | 2 h (`BATCH_BUDGET_SECONDS`) |
| `OnMediaCreatedHandler` (enriquecimento automático) | 60 s (`ENRICH_BUDGET_SECONDS`) |
| Rotas interativas | Nenhum: falha rápido |

### 2. O protocolo do TMDB na ACL (`TmdbClient._get`)

Toda requisição passa por `_get`, que agora:

- usa limites por fase (`connect=5`, `read=10`, `write=5`, `pool=5`) **e** um teto total por chamada: 15 s ou o que sobrou do orçamento, o que for menor. É o teto que pega a resposta que pinga devagar. Com o orçamento esgotado, nada é enviado. Se ele acaba com a chamada em andamento, a chamada é cortada. Nos dois casos o erro é `_BudgetSpentError`, um `GatewayTimeoutException`, e ele **atravessa** os helpers best-effort de tradução e temporada. Pular um idioma porque o TMDB falhou é aceitável; pular porque o tempo acabou gravaria um enriquecimento parcial que nunca mais seria revisto;
- **respeita `Retry-After` com um gate compartilhado** (`building_blocks/infrastructure/retry_after_gate.py`). O primeiro `429` fecha o gate para todos que usam o cliente: o lote, o handler e as rotas. Quem chega com o gate fechado espera, se a espera **mais uma chamada inteira** cabem no orçamento, ou recebe `GatewayRateLimitException` sem enviar nada. Dormir 55 s de um orçamento de 60 só para a chamada seguinte ser cortada seria gastar o orçamento à toa;
- **retenta** timeout, erro de transporte e `5xx`, com jitter de 0,5 a 1,5 s, e só se o orçamento restante comporta o backoff mais uma chamada inteira. `4xx` é definitivo e nunca é retentado. O reenvio depois de um `429` acontece pelo gate, não pelo backoff. Em qualquer combinação, uma chamada envia **no máximo duas vezes**: `429` e falha transitória dividem o mesmo contador.

Respeitar `Retry-After` é falar o protocolo do provider, por isso mora na ACL. Quanto tempo vale a pena esperar é uma decisão de quem chama, e chega à ACL como orçamento, não como regra embutida no cliente.

### 3. Provider fora da transação (`enrich_*_metadata.py`)

O `enrich` agora lê, fecha o UoW, consulta o TMDB e abre um segundo UoW para gravar. Como a linha pode ter mudado no meio do caminho, o segundo UoW **relê** o registro e aplica o resultado sobre a versão fresca. É uma checagem otimista, sem lock: se outra execução já resolveu o título (`tmdb_id` preenchido) e esta não é forçada, o resultado é descartado. O mesmo vale para o caminho de "nenhum resultado", que só marca `needs_enrichment_review` se ninguém resolveu o título antes.

### 4. Disjuntor no lote (`BulkEnrichMetadataUseCase`)

| Falha | Natureza | O lote |
|---|---|---|
| `enrich` devolve `error` (nenhum match, match de outro tipo) | Resposta definitiva sobre o item | Registra e segue |
| `GatewayRateLimitException` chegando ao lote | O provider pediu para parar por mais tempo do que o orçamento do item | **Aborta** |
| Outra `GatewayException` do item (timeout, indisponível, 4xx) | Falha do provider | Registra; **5 seguidas abortam** |
| Qualquer outra exceção | Não é do provider (um timeout do banco, um bug) | Registra e segue, sem contar para o disjuntor |
| Item pulado (já tem `tmdb_id`) | Não consultou o provider | Não zera a sequência de falhas |
| Orçamento do lote esgotado | — | **Aborta** |

Ao abortar, o motivo vai para `BulkEnrichOutput.aborted_reason` e para a lista de erros do `scan_run`. Os itens não tocados continuam sem `tmdb_id`, e a próxima execução sem `force` os retoma. O reprocessamento idempotente já existia (o `enrich` pula quem tem `tmdb_id`) e não precisou de lista de falhas.

## Consequências

### Positivas

- Um TMDB degradado não queima mais o lote: o `429` pausa ou aborta, e a execução seguinte retoma de onde parou.
- Toda chamada ao TMDB tem limite superior, e cada item tem orçamento.
- O handler e as rotas respeitam o mesmo `Retry-After` que o lote, porque o gate é do cliente, não do lote.
- Nenhuma conexão do banco fica presa esperando o provider. Como o orçamento não cancela, uma escrita ou um `publish` nunca é interrompido no meio.

### Negativas

- **Orçamento ambiente.** O prazo viaja num `ContextVar`, não num parâmetro. É implícito: quem lê `TmdbClient._get` precisa saber que o comportamento depende de quem chamou. A alternativa explícita está registrada abaixo.
- **O gate vive na memória do processo.** Com mais de um worker, cada um tem o seu. Hoje o HomeFlix roda um processo só.
- **O gate é reativo**: espera o primeiro `429` em vez de limitar a vazão antes. Um token bucket evitaria o `429`, mas exigiria conhecer e acompanhar o limite do TMDB, que muda sem aviso.
- **Os números são escolhas, não medições.** O orçamento de 60 s por item, o de 2 h por lote e o limite de 5 falhas seguidas foram calibrados pelo cenário, não por dados de produção. Precisam ser revistos quando houver observação real.
- O `enrich` passou de um UoW para dois, e a releitura custa uma consulta a mais por item.
- O orçamento limita o tempo de **espera pelo provider**, não o tempo total do item. Trabalho local lento (o banco, um handler) não é cortado por ele.
- Um lote abortado ainda fecha o `scan_run` como concluído, com o motivo na lista de erros. Um status próprio exigiria mudar o agregado `ScanRun`, e ficou fora deste ADR.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Vários chamadores acordam juntos quando o gate reabre (thundering herd) | Baixa | Baixo | O lote processa um item por vez. Cada item ainda dispara algumas chamadas concorrentes (as traduções de temporada usam `gather`), e esse pico é pequeno |
| Overlays de tradução engolem `GatewayException` e devolvem `None`: com o TMDB falhando numa tradução, o título é enriquecido sem ela e, sem `force`, não é refeito | Média | Baixo | Pré-existente, e fora deste ADR. O orçamento **não** agrava isso: "orçamento esgotado" é um subtipo próprio (`_BudgetSpentError`) que atravessa os helpers best-effort e falha o item inteiro, que a próxima execução refaz |
| `force=True` concorrente com outra execução forçada: a última gravação vence | Baixa | Baixo | Aceito: `force` é um gesto manual do admin |

## Alternativas Consideradas

### 1. Transação longa (buscar dentro do UoW)

Manter ler, buscar e gravar num bloco atômico só.

**Rejeitado porque:** prende uma conexão durante toda a espera pelo provider, que agora inclui esperar um `Retry-After` de dezenas de segundos. Na escala atual o pool quase não sofre, mas a espera deliberada transforma uma transação curta numa longa por desenho.

### 2. Pausar só no lote

Tratar `GatewayRateLimitException` apenas no `BulkEnrich`, dormindo `retry_after_seconds` e retentando o item.

**Rejeitado porque:** o handler de mídia criada continuaria batendo no TMDB enquanto o lote dorme, renovando o `429`. O limite é propriedade do provider, não do lote.

### 3. Retry no item (2 a 3 tentativas do `enrich` inteiro)

**Rejeitado porque:** repete as chamadas que deram certo, multiplica com a pausa do lote (retry storm) e não cabe no orçamento. Com 5 chamadas por item, 10 s de leitura e 3 tentativas, o pior caso é 150 s contra um orçamento de 60.

### 4. Prazo como parâmetro explícito em cada método da porta

Passar um `Deadline` em todos os métodos de `MetadataProvider`.

**Rejeitado porque:** são 13 métodos na porta, mais as implementações e todos os chamadores, só para transportar um valor que só a infraestrutura lê. O `ContextVar` segue o mesmo modelo do `asyncio.timeout`, que também é ambiente.

### 5. Orçamento que cancela (`asyncio.timeout` em volta do item)

Foi a primeira versão deste desenho: o item inteiro rodava dentro de um `asyncio.timeout`.

**Rejeitado porque:** o cancelamento não escolhe onde cai. Ele podia interromper o `commit` do segundo UoW ou o `publish` do evento, deixando o título enriquecido sem o evento que o `catalog_requests` espera. Também transformava um timeout do banco em "falha do provider" no disjuntor. Limitar só o tempo de espera pelo provider evita os dois problemas. O custo é que o tempo total do item deixa de ter teto: só a parte gasta com o provider é limitada, e trabalho local lento não é cortado.

### 6. Biblioteca de resiliência (tenacity, aiobreaker)

**Rejeitado porque:** o retry aqui é uma tentativa, condicionada ao orçamento, e o disjuntor é um contador no laço do lote. Uma dependência a mais não paga esse tamanho.

## Referências

- [ADR-009](./ADR-009-cross-bc-read-ports.md) — a ACL do TMDB e a tradução de erros
- [ADR-025](./ADR-025-provider-metadata-reconciliation-in-application.md) — a reconciliação na aplicação
- Michael Nygard, *Release It!* (2ª ed.) — timeouts, circuit breaker, integration points
- AWS Builders' Library — *Timeouts, retries, and backoff with jitter*

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-10-04 | Lucas Cristovam | Criação inicial |
