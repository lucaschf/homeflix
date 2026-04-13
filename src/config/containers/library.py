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
from src.modules.library.infrastructure.persistence.repositories.sqlalchemy_library_repository import (
    SqlAlchemyLibraryRepository,
)


class LibraryContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Library bounded context dependencies.

    Provides:
    - Repository implementation (SQLAlchemy)
    - CRUD use cases
    - Domain services
    """

    # Wired from InfrastructureContainer via main container.
    session = providers.Dependency()

    # =========================================================================
    # Repositories
    # =========================================================================

    library_repository = providers.Factory(
        SqlAlchemyLibraryRepository,
        session=session,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    create_library = providers.Factory(
        CreateLibraryUseCase,
        library_repository=library_repository,
    )

    list_libraries = providers.Factory(
        ListLibrariesUseCase,
        library_repository=library_repository,
    )

    get_library_by_id = providers.Factory(
        GetLibraryByIdUseCase,
        library_repository=library_repository,
    )

    update_library = providers.Factory(
        UpdateLibraryUseCase,
        library_repository=library_repository,
    )

    delete_library = providers.Factory(
        DeleteLibraryUseCase,
        library_repository=library_repository,
    )

    # =========================================================================
    # Domain Services
    # =========================================================================

    track_selector = providers.Factory(TrackSelector)
