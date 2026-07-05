# HomeFlix — Documentação Técnica

Plataforma de streaming pessoal para gerenciar e reproduzir filmes/séries
armazenados em HD local. Serve como lab de Clean Architecture / DDD e como
ferramenta funcional de gerenciamento de mídia.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **APIs externas:** TMDB, OMDb (metadados)

## Como navegar

- **[Requisitos](homeflix-requirements.md)** — features e regras de negócio.
- **[Roadmap](roadmap.md)** — priorização e próximos passos.
- **Standards** — convenções transversais: formato de respostas da API,
  hierarquia de exceções, i18n, logging, observabilidade e testes.
- **ADRs** — decisões de arquitetura registradas. O
  [índice](adr/README.md) lista todas; ADRs são a **fonte da verdade** para
  decisões estruturais.

## Bounded Contexts

São 9 bounded contexts em `src/modules/`: Media Catalog, Library Management,
Watch Progress, Collections, Catalog Requests, Identity, Notifications,
Preferences e Settings. A regra de dependência é
`modules → shared_kernel → building_blocks`; módulos não se importam entre si —
comunicação via Read Port + ACL (ADR-009).

!!! note "Documentação viva"
    Esta doc é derivada do código, não uma fonte independente de verdade.
    Mudanças em `src/` que alteram comportamento ou contrato devem ser
    refletidas aqui na mesma sessão (skill `docs-maintainer` / `/sync-docs`),
    e `mkdocs build --strict` precisa passar.
