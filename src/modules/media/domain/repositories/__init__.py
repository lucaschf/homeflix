"""Media domain repository interfaces."""

from src.modules.media.domain.repositories.artwork_mirror_repository import (
    MovieArtworkMirrorRepository,
    RemoteArtworkRow,
    SeriesArtworkMirrorRepository,
)
from src.modules.media.domain.repositories.credits_detection_repository import (
    CreditsStatusRow,
    MovieCreditsDetectionRepository,
    SeriesCreditsDetectionRepository,
)
from src.modules.media.domain.repositories.intro_detection_repository import (
    SeriesIntroDetectionRepository,
)
from src.modules.media.domain.repositories.intro_detection_run_repository import (
    IntroDetectionRunRepository,
)
from src.modules.media.domain.repositories.job_run_repository import JobRunRepository
from src.modules.media.domain.repositories.media_conflict_repository import (
    MediaConflictRepository,
)
from src.modules.media.domain.repositories.movie_repository import (
    GenreRow,
    MovieCatalogRepository,
    MovieRepository,
)
from src.modules.media.domain.repositories.scan_run_repository import ScanRunRepository
from src.modules.media.domain.repositories.scrub_preview_repository import (
    MovieScrubPreviewRepository,
    SeriesScrubPreviewRepository,
)
from src.modules.media.domain.repositories.series_repository import (
    SeriesCatalogRepository,
    SeriesRepository,
)
from src.modules.media.domain.repositories.subtitle_ocr_run_repository import (
    SubtitleOcrRunRepository,
)

__all__ = [
    "CreditsStatusRow",
    "GenreRow",
    "IntroDetectionRunRepository",
    "JobRunRepository",
    "MediaConflictRepository",
    "MovieArtworkMirrorRepository",
    "MovieCatalogRepository",
    "MovieCreditsDetectionRepository",
    "MovieRepository",
    "MovieScrubPreviewRepository",
    "RemoteArtworkRow",
    "ScanRunRepository",
    "SeriesArtworkMirrorRepository",
    "SeriesCatalogRepository",
    "SeriesCreditsDetectionRepository",
    "SeriesIntroDetectionRepository",
    "SeriesRepository",
    "SeriesScrubPreviewRepository",
    "SubtitleOcrRunRepository",
]
