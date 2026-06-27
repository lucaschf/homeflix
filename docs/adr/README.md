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
| [ADR-005](./ADR-005-library-as-configuration-entity.md) | Library como Entidade de Configuração | ✅ Aceito | 2026-02-03 |
| [ADR-006](./ADR-006-media-file-variants.md) | Variantes de Arquivo de Mídia | ✅ Aceito | 2026-02-03 |
| [ADR-007](./ADR-007-immutable-entities-with-convention.md) | Entidades Imutáveis com Convenção `with_*` | ✅ Aceito | 2026-02-17 |
| [ADR-008](./ADR-008-screaming-architecture.md) | Screaming Architecture com Módulos | ✅ Aceito | 2026-04-02 |
| [ADR-009](./ADR-009-cross-bc-read-ports.md) | Cross-BC Read Ports + ACL | ✅ Aceito | 2026-04-18 |
| [ADR-010](./ADR-010-identity-bounded-context.md) | Identity Bounded Context | ✅ Aceito | 2026-05-03 |
| [ADR-011](./ADR-011-authentication-strategy.md) | Authentication Strategy | ✅ Aceito | 2026-05-03 |
| [ADR-012](./ADR-012-decentralized-error-http-mapping.md) | Registry Descentralizado de Error HTTP Mapping | ✅ Aceito | 2026-05-06 |
| [ADR-013](./ADR-013-runtime-settings-db-backed.md) | Runtime Settings Persistidos em Banco para Tunables Operacionais | ✅ Aceito | 2026-05-21 |
| [ADR-014](./ADR-014-settings-per-bucket-aggregate.md) | Settings — Aggregate por Bucket (não Mega-Aggregate) | ✅ Aceito | 2026-05-21 |
| [ADR-015](./ADR-015-scanner-deduplication-by-content-identity.md) | Scanner Deduplication by Content Identity | 🟡 Proposto | 2026-05-23 |
| [ADR-016](./ADR-016-media-type-value-object.md) | MediaType como Value Object compartilhado | ✅ Aceito | 2026-05-31 |
| [ADR-017](./ADR-017-domain-invariants-in-domain-layer.md) | Invariantes de domínio na camada de domínio | ✅ Aceito | 2026-06-04 |
| [ADR-018](./ADR-018-domain-identifiers-as-vos-at-boundaries.md) | Identificadores de domínio como Value Objects nas fronteiras | ✅ Aceito | 2026-06-04 |
| [ADR-019](./ADR-019-hardware-accelerated-transcoding.md) | Transcodificação por Hardware (NVENC/NVDEC) com Seleção de Encoder Configurável | ✅ Aceito | 2026-06-14 |
| [ADR-020](./ADR-020-pluggable-intro-detector-frame-hash.md) | Detector de Intro Plugável + Algoritmo por Frame-Hash de Vídeo | ✅ Aceito | 2026-06-15 |
| [ADR-021](./ADR-021-credits-detector-per-file-visual.md) | Detector de Créditos Per-Arquivo por Sinais Visuais (Borda + Movimento) | ✅ Aceito | 2026-06-19 |
| [ADR-022](./ADR-022-catalog-requests-subscriptions-fanout.md) | Subscriptions Multi-Usuário + Fanout em Catalog Requests | ✅ Aceito | 2026-06-23 |
| [ADR-023](./ADR-023-localized-metadata-value-object.md) | Metadados Localizados como Value Object | ✅ Aceito | 2026-06-27 |

## Como Criar um Novo ADR

1. Copie o arquivo `TEMPLATE.md`
2. Renomeie para `ADR-XXX-titulo-curto.md`
3. Preencha todas as seções
4. Atualize este índice
5. Submeta para revisão

## Referências

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions - Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
