"""Library bounded context dependency container.

Provides repositories, use cases, and domain services for the
Library module.
"""

from typing import Any

from dependency_injector import containers, providers

from src.modules.library.application.use_cases.create_library import CreateLibraryUseCase
from src.modules.library.application.use_cases.delete_library import DeleteLibraryUseCase
from src.modules.library.application.use_cases.get_library_by_id import GetLibraryByIdUseCase
from src.modules.library.application.use_cases.list_libraries import ListLibrariesUseCase
from src.modules.library.application.use_cases.update_library import UpdateLibraryUseCase
from src.modules.library.infrastructure.acl import MediaCountQueryAdapter
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)


class LibraryContainer(containers.DeclarativeContainer):
    """Container for Library bounded context dependencies.

    Provides:
    - Unit of Work factory (reads and writes both go through it)
    - ACL adapter for the Media BC read port
    - CRUD use cases
    - Domain services
    """

    # Wired from InfrastructureContainer via main container.
    session_factory = providers.Dependency[Any]()
    # Media UoW factory comes in so the ACL adapter can open short-lived
    # transactions against the Media catalog for count queries. Use
    # cases themselves only know ``MediaCountQueryPort``.
    media_uow_factory = providers.Dependency[Any]()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    library_unit_of_work_factory = providers.Singleton(
        SqlAlchemyLibraryUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read ports)
    # =========================================================================

    media_count_query = providers.Factory(
        MediaCountQueryAdapter,
        media_uow_factory=media_uow_factory,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    create_library = providers.Factory(
        CreateLibraryUseCase,
        uow_factory=library_unit_of_work_factory,
        media_count_query=media_count_query,
    )

    list_libraries = providers.Factory(
        ListLibrariesUseCase,
        uow_factory=library_unit_of_work_factory,
        media_count_query=media_count_query,
    )

    get_library_by_id = providers.Factory(
        GetLibraryByIdUseCase,
        uow_factory=library_unit_of_work_factory,
        media_count_query=media_count_query,
    )

    update_library = providers.Factory(
        UpdateLibraryUseCase,
        uow_factory=library_unit_of_work_factory,
        media_count_query=media_count_query,
    )

    delete_library = providers.Factory(
        DeleteLibraryUseCase,
        uow_factory=library_unit_of_work_factory,
    )
