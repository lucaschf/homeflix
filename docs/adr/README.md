# Architecture Decision Records (ADRs)

Este diretório contém os registros de decisões arquiteturais do projeto HomeFlix.

## O que é um ADR?

Um ADR (Architecture Decision Record) documenta uma decisão arquitetural significativa, incluindo o contexto, a decisão tomada, e suas consequências.

## Índice de ADRs

| ID | Título | Status | Data |
|----|--------|--------|------|
| [ADR-001](./ADR-001-pydantic-domain-models.md) | Uso de Pydantic para Modelos de Domínio | ✅ Aceito | 2025-01-28 |
| [ADR-002](./ADR-002-prefixed-external-ids.md) | Prefixed External IDs para Recursos da API | ✅ Aceito | 2025-01-28 |
| [ADR-003](./ADR-003-package-structure.md) | Estrutura de Pacotes e Organização | ✅ Aceito | 2025-01-28 |
| [ADR-004](./ADR-004-dependency-injection.md) | Injeção de Dependências com dependency-injector | ✅ Aceito | 2025-01-28 |

## ADRs Planejados

Os seguintes ADRs serão criados conforme o projeto avança:

- **ADR-003**: Estrutura de Pastas e Organização do Projeto
- **ADR-004**: Estratégia de Testes (Unit, Integration, E2E)
- **ADR-005**: Padrão de Repositórios e Unit of Work
- **ADR-006**: Injeção de Dependências
- **ADR-007**: Streaming de Vídeo (HTTP Range Requests vs HLS)
- **ADR-008**: Cache Strategy
- **ADR-009**: Background Jobs (Scan, Metadata Fetch)
- **ADR-010**: Error Handling e Exception Hierarchy

## Como Criar um Novo ADR

1. Copie o arquivo `TEMPLATE.md`
2. Renomeie para `ADR-XXX-titulo-curto.md`
3. Preencha todas as seções
4. Atualize este índice
5. Submeta para revisão

## Referências

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions - Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
