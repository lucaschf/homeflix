# ADR Index — HomeFlix

Roteador "sintoma/pergunta → qual ADR ler".

> **O índice autoritativo é `docs/adr/README.md` no repo**, com todos os ADRs,
> título, status e data. Este arquivo não replica a lista — ele roteia a partir
> do que você está vendo no código. Sempre abra o ADR completo no repo antes de
> propor mudança que conflita com a decisão.

## Por sintoma no código

| Sintoma | ADR |
|---|---|
| `from pydantic import BaseModel` em domain | ADR-001 |
| `id: UUID` ou `id: int` em entidade | ADR-002 |
| Identificador como `str` cru cruzando camada ou BC | ADR-018 |
| `from src.domain...` / `from src.application...` (estrutura antiga) | ADR-008 |
| `from src.modules.X` em código de `src/modules/Y/` | ADR-009 |
| `from src.config.containers` em código de módulo | ADR-004 + ADR-008 |
| `@inject` ou `Provide` fora de route | ADR-004 |
| Método `add_X`, `mark_X`, `set_X`, `remove_X` em agregado | ADR-007 |
| Use case abrindo sessão, ou recebendo repo solto com UoW disponível | ADR-004 |
| Status HTTP decidido na rota em vez de `error_mapping.py` | ADR-012 |
| `raise DomainException` genérica sem código de regra | ADR-028 |
| Handler checando `user.role` no corpo em vez de `Depends` | ADR-010 + ADR-035 |
| `AudioTrack` direto em `Movie` (em vez de em `MediaFile`) | ADR-006 |
| Use case com lógica de scan/biblioteca embutida sem usar `Library` | ADR-005 |
| Adapter de port externo retornando VO de domínio | ADR-009 (filosofia ACL) |
| Título/sinopse guardados num campo por idioma | ADR-023 |
| Repositório com interface inchada ("faz tudo") | ADR-033 |

## Por pergunta comum

| Pergunta | ADR |
|---|---|
| "Onde coloco essa classe nova?" | ADR-008 |
| "Como faço o ID desse novo agregado?" | ADR-002 (subclasse de `ExternalId` com `EXPECTED_PREFIX`) |
| "Esse ID pode trafegar como string?" | ADR-018 |
| "Como esse use case acessa dados de outro BC?" | ADR-009, e ADR-024 se for contrato de presentation |
| "Como mockar essa dependência no teste?" | ADR-004 (injetar no construtor, sem container) |
| "Posso modificar este agregado in-place?" | Não. ADR-007 |
| "Posso usar `BaseModel` direto aqui?" | Não. ADR-001 |
| "Preciso de bounded context novo?" | ADR-008 (critérios) |
| "Onde valido essa invariante?" | ADR-017 |
| "Que exceção eu levanto aqui?" | ADR-028 |
| "Quem pode ver esse item do catálogo?" | ADR-010, ADR-011, ADR-035 |
| "Onde guardo esse tunable operacional?" | ADR-013, ADR-014 |

## Notas de leitura

**ADR-003 está marcado como Substituído.** Ele ainda existe no repo; sempre
referencie **ADR-008** para estrutura de pacotes.

**ADR-009 argumenta contra domain events para integração cross-BC.** Isso não
significa que o projeto não tem eventos: `AggregateRoot` acumula eventos de
domínio e use cases os drenam com `pull_events()`. O que o ADR rejeita é usar
evento como mecanismo de *leitura* entre contextos — para isso, port + ACL.

**Alguns ADRs têm emendas.** Amendments aparecem no corpo do próprio ADR e
mudam a decisão original — leia o arquivo inteiro, não só a seção "Decisão".

**ADR em status `Proposto` não é regra ainda.** Confira o status na tabela de
`docs/adr/README.md` antes de citar como obrigatório.

## Adicionando novo ADR

1. Use `docs/adr/TEMPLATE.md` como base.
2. Numere sequencialmente — o próximo número é o que vier depois do último em
   `docs/adr/README.md`. **Não chute**, consulte.
3. Status inicial `Proposto`; após implementar e validar, `Aceito`.
4. Atualize a tabela de `docs/adr/README.md`.
5. Se substitui um ADR existente, marque o antigo como `Substituído` e
   referencie o novo nos dois sentidos.
6. Se a decisão muda convenção do dia a dia, atualize no mesmo PR o `CLAUDE.md`
   da raiz — que todo agente lê por padrão — e, se for o caso, esta skill em
   `.claude/skills/homeflix-arch/`.

Bom indicador de "isso merece ADR": a decisão impacta múltiplos módulos, **ou**
envolve trade-off não-óbvio que outro dev questionaria daqui a seis meses.
