"""Media bounded context dependency container.

Provides repositories and use cases for the Media module.
"""

from dependency_injector import containers, providers

from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)


class MediaContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Media bounded context dependencies.

    Provides:
    - Repository implementations (SQLAlchemy)
    - Use cases for movie, series, and file variant operations

    The ``session`` dependency must be wired from the parent container
    once the database provider is added to InfrastructureContainer.

    Example:
        >>> container = MediaContainer(session=session_provider)
        >>> use_case = container.get_movie_by_id()
    """

    # Must be wired from InfrastructureContainer.session
    session = providers.Dependency()

    # =========================================================================
    # Repositories
    # =========================================================================

    movie_repository = providers.Factory(
        SQLAlchemyMovieRepository,
        session=session,
    )

    series_repository = providers.Factory(
        SQLAlchemySeriesRepository,
        session=session,
    )

    # =========================================================================
    # Use Cases — Query
    # =========================================================================

    get_movie_by_id = providers.Factory(
        GetMovieByIdUseCase,
        movie_repository=movie_repository,
    )

    list_movies = providers.Factory(
        ListMoviesUseCase,
        movie_repository=movie_repository,
    )

    get_series_by_id = providers.Factory(
        GetSeriesByIdUseCase,
        series_repository=series_repository,
    )

    list_series = providers.Factory(
        ListSeriesUseCase,
        series_repository=series_repository,
    )

    # =========================================================================
    # Use Cases — File Variants
    # =========================================================================

    get_file_variants = providers.Factory(
        GetFileVariantsUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    add_file_variant = providers.Factory(
        AddFileVariantUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    remove_file_variant = providers.Factory(
        RemoveFileVariantUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    set_primary_file = providers.Factory(
        SetPrimaryFileUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    # =========================================================================
    # Infrastructure — File System
    # =========================================================================

    file_scanner = providers.Factory(LocalFileSystemScanner)

    variant_detector = providers.Factory(VariantDetector)

    # =========================================================================
    # Use Cases — Scan
    # =========================================================================

    scan_media_directories = providers.Factory(
        ScanMediaDirectoriesUseCase,
        file_scanner=file_scanner,
        variant_detector=variant_detector,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )
