"""Library bounded context dependency container.

Provides repositories, use cases, and domain services for the
Library module.
"""

from dependency_injector import containers, providers

from src.modules.library.application.use_cases.create_library import CreateLibraryUseCase
from src.modules.library.application.use_cases.delete_library import DeleteLibraryUseCase
from src.modules.library.application.use_cases.get_library_by_id import GetLibraryByIdUseCase
from src.modules.library.application.use_cases.list_libraries import ListLibrariesUseCase
from src.modules.library.application.use_cases.update_library import UpdateLibraryUseCase
from src.modules.library.domain.services.track_selector import TrackSelector
from src.modules.library.infrastructure.acl import MediaCountQueryAdapter
from src.modules.library.infrastructure.persistence.repositories.sqlalchemy_library_repository import (
    SqlAlchemyLibraryRepository,
)
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)


class LibraryContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Library bounded context dependencies.

    Provides:
    - Repository implementation (SQLAlchemy) for read use cases
    - Unit of Work factory for write use cases
    - ACL adapter for the Media BC read port
    - CRUD use cases
    - Domain services
    """

    # Wired from InfrastructureContainer via main container.
    session = providers.Dependency()
    session_factory = providers.Dependency()
    # Media repositories come in so the ACL adapter can delegate
    # count queries. The use cases themselves only know the
    # ``MediaCountQueryPort`` — they never see these concretes.
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    # =========================================================================
    # Repositories (read-only) and Unit of Work (writes)
    # =========================================================================

    library_repository = providers.Factory(
        SqlAlchemyLibraryRepository,
        session=session,
    )

    library_unit_of_work_factory = providers.Singleton(
        SqlAlchemyLibraryUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read ports)
    # =========================================================================

    media_count_query = providers.Factory(
        MediaCountQueryAdapter,
        movie_repository=movie_repository,
        series_repository=series_repository,
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
        library_repository=library_repository,
        media_count_query=media_count_query,
    )

    get_library_by_id = providers.Factory(
        GetLibraryByIdUseCase,
        library_repository=library_repository,
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

    # =========================================================================
    # Domain Services
    # =========================================================================

    track_selector = providers.Factory(TrackSelector)
