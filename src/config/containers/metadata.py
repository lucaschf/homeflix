"""Dependency-injection container for the Metadata bounded context.

Owns the Metadata / Enrichment provider subdomain's providers: the TMDB
gateway (``MetadataProvider``), artwork mirror storage + download
(ADR-029), and the pure person-bio lookup. The Media catalog consumes
the published ``tmdb_client`` provider for its enrichment / relink /
suggestion use cases via cross-container wiring at the composition root
(the Core-depends-on-Supporting provider-contract dependency, ADR-032).
"""

from dependency_injector import containers, providers

from src.modules.metadata.application.use_cases.get_person_bio import GetPersonBioUseCase
from src.modules.metadata.infrastructure.artwork_downloader import HttpxArtworkDownloader
from src.modules.metadata.infrastructure.local_artwork_storage import LocalArtworkStorage
from src.modules.metadata.infrastructure.tmdb_client import TmdbClient


class MetadataContainer(containers.DeclarativeContainer):
    """Container for Metadata bounded context dependencies.

    The ``tmdb_api_key``, ``supported_locales``, and
    ``artwork_storage_directory`` config values must be wired from the
    parent :class:`ApplicationContainer`.
    """

    # -- Wired from the composition root --------------------------------------

    # Must be wired from parent container (Settings.tmdb_api_key)
    tmdb_api_key = providers.Dependency[str](default="")

    # Wired from parent container (Settings.supported_locales). Drives
    # which non-English translations the TMDB client overlays during
    # enrichment — adding a language is a config change, not a code edit.
    supported_locales = providers.Dependency[list[str]](default=["en", "pt-BR"])

    # Artwork mirror directory (ADR-029), wired from
    # ``Settings.artwork_storage_directory`` at the composition root.
    # Bootstrap filesystem path, same style as ``hls_cache_directory``.
    artwork_storage_directory = providers.Dependency[str](default="./artwork")

    # -- Infrastructure — Metadata Providers ----------------------------------

    tmdb_client = providers.Singleton(
        TmdbClient,
        api_key=tmdb_api_key,
        supported_locales=supported_locales,
    )

    # Local-disk storage for mirrored catalog artwork (ADR-029).
    # Singleton so the proxy route and the mirror job share one
    # instance (it is stateless apart from the root path).
    artwork_storage = providers.Singleton(
        LocalArtworkStorage,
        root_directory=artwork_storage_directory,
    )

    # Downloads still-remote provider artwork for the mirror job (ADR-029).
    # Singleton so one pooled httpx client is shared across ticks.
    artwork_downloader = providers.Singleton(HttpxArtworkDownloader)

    # -- Use Cases ------------------------------------------------------------

    get_person_bio = providers.Factory(
        GetPersonBioUseCase,
        metadata_provider=tmdb_client,
    )
