# ADR-037: Fronteiras entre Bounded Contexts Verificadas por import-linter

**Status:** Aceito
**Data:** 2026-10-04
**Deciders:** Lucas Cristovam
**Technical Story:** Auditoria de acoplamento (out/2026): a regra do ADR-009 existia só em texto e em revisão manual.

---

## Contexto

O ADR-008 define a direção de dependência dentro de um módulo (`presentation → application → domain ← infrastructure`), e o ADR-009 proíbe import entre bounded contexts fora de uma ACL no consumidor. O ADR-024 abre uma única exceção na camada de presentation (`identity/presentation/public.py`).

Nenhuma dessas regras era verificada por máquina. Os testes em `tests/architecture/` cobrem outras regras (autenticação declarada, fonte única de checagem de admin), mas não a fronteira entre módulos. A auditoria de outubro de 2026 mediu o efeito disso:

- `media/infrastructure/{audio,video}` importava 4 vezes `streaming.infrastructure.streaming._subprocess`, um módulo privado de outro BC. Nenhum ADR registrava isso, e a dependência entrou sem que ninguém percebesse.
- 11 use cases do `media` importam a porta `MetadataProvider`, que pertence ao `metadata` desde a extração do ADR-032. A regra 1 do ADR-009 diz que os tipos da porta pertencem ao consumidor.
- 18 diretórios dentro de `src/modules/` (todo o `preferences` e boa parte do `library`) não tinham `__init__.py`. Ferramentas de análise de imports baseadas em pacote não enxergam esses arquivos.

Uma regra que depende de alguém lembrar dela na revisão volta a ser quebrada.

## Decisão

Nós iremos verificar as fronteiras com o [import-linter](https://import-linter.readthedocs.io/) em três lugares: `make lint`, pre-commit e CI. Uma quebra reprova o build.

São dois contratos, declarados em `pyproject.toml`:

1. **Independência entre bounded contexts** (`independence`). Nenhum módulo importa outro, direta ou indiretamente. As exceções são explícitas:
    - `src.modules.*.infrastructure.acl.**` → qualquer módulo: a ACL do ADR-009.
    - `src.modules.*.presentation.**` → `src.modules.identity.presentation.public`: o contrato publicado do ADR-024.
    - `src.modules.*.presentation.**` → `src.config.containers`: a rota resolve o use case no composition root. Sem essa exceção, toda rota "importaria" todos os módulos através do container.
    - Os 9 imports atuais de `media.application` para a porta do `metadata`, **listados um a um**. É dívida congelada: o conjunto só pode diminuir, e um use case novo que importe a porta reprova.
2. **Camadas dentro de cada módulo** (`layers`): `presentation` > `infrastructure` > `application` > `domain`. Cada camada só importa as de baixo.

Imports sob `TYPE_CHECKING` ficam fora da análise (`exclude_type_checking_imports`). É o que torna a variante "Protocol port" do ADR-009 compatível com o contrato: os VOs de `settings` aparecem só para o verificador de tipos.

Um teste em `tests/architecture/test_import_contracts_cover_all_modules.py` fecha as duas formas de o contrato falhar em silêncio:

- a lista de módulos de cada contrato precisa ser igual aos diretórios de `src/modules/`, então um BC novo não fica de fora;
- todo diretório com código Python em `src/modules/` precisa ter `__init__.py`, então o grimp, o motor do import-linter, enxerga todos os arquivos.

Junto com esta decisão, os helpers genéricos de subprocess do ffmpeg (`SUBPROCESS_TEXT_KWARGS`, `with_ffmpeg_threads`) saem de `streaming/.../_subprocess.py` e vão para `src/building_blocks/infrastructure/ffmpeg_subprocess.py`. Eles não têm nada de streaming: são base técnica sem domínio (ADR-008), usada por dois módulos. As constantes de aceleração por hardware continuam no `streaming`, que é o único módulo que as usa.

## Consequências

### Positivas

- A regra do ADR-009 vira teste: um import novo entre módulos reprova no pre-commit, antes do PR.
- A dívida `media → metadata` fica visível no lugar onde a regra é aplicada, com contagem exata, em vez de só num documento de auditoria.
- O ADR-024 já previa um lint "se recorrer"; agora ele existe para todo o projeto, não só para `identity.presentation`.
- O ciclo `media ↔ streaming` causado pelo `_subprocess` deixa de existir.

### Negativas

- Toda mudança de fronteira legítima — um BC novo, uma exceção nova — passa a exigir edição de `pyproject.toml`. Isso é intencional, mas é atrito.
- O contrato de camadas permite `presentation → infrastructure`, porque as `dependencies.py` de todos os módulos fazem wiring por lá. Separar as duas camadas em irmãs independentes quebra 11 módulos e fica fora do escopo deste ADR.
- A exceção da ACL é ampla: o adapter pode importar qualquer camada do provedor, inclusive `infrastructure`. O ADR-009 aceita isso como compromisso de wiring, e o contrato não é mais estrito que o ADR.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Lógica de negócio migrar para `acl/` para escapar do contrato | Baixa | Médio | Revisão de PR; o ADR-009 restringe a ACL a tradução de leitura |
| Exceção nova ser adicionada sem justificativa | Média | Médio | Toda linha em `ignore_imports` cita o ADR que a autoriza |
| Diretório novo sem `__init__.py` esconder imports | Média | Alto | `test_every_module_directory_is_a_regular_package` |

## Alternativas Consideradas

### 1. Teste de arquitetura próprio com `ast`

Seguir o padrão de `tests/architecture/` e escrever o parser de imports à mão.

**Rejeitado porque:** imports indiretos (A → container → B) e a semântica de `TYPE_CHECKING` são exatamente o que o import-linter já resolve. Reescrever isso é código de infraestrutura sem valor de domínio.

### 2. Um contrato `forbidden` por par de módulos

Listar, para cada módulo, os outros que ele não pode importar.

**Rejeitado porque:** com 11 módulos são 110 pares, e um módulo novo exige atualizar todos. O contrato `independence` expressa a regra do ADR-009 diretamente.

### 3. Resolver a dívida `media → metadata` antes de ligar o contrato

**Rejeitado porque:** a correção (porta própria no `media` ou declarar o `metadata` como Open Host Service) é uma decisão de modelagem que merece ADR próprio. Ligar o contrato agora, com a dívida congelada, impede que ela cresça enquanto a decisão não sai.

## Referências

- [ADR-008](./ADR-008-screaming-architecture.md), [ADR-009](./ADR-009-cross-bc-read-ports.md), [ADR-024](./ADR-024-published-presentation-contracts-cross-bc.md), [ADR-032](./ADR-032-decompose-media-into-subdomains.md)
- [import-linter — contract types](https://import-linter.readthedocs.io/en/stable/contract_types.html)

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-10-04 | Lucas Cristovam | Criação inicial |
