"""Media module SQLAlchemy repository implementations."""

from src.modules.media.infrastructure.persistence.repositories.intro_detection_run_repository import (
    SqlAlchemyIntroDetectionRunRepository,
)
from src.modules.media.infrastructure.persistence.repositories.media_conflict_repository import (
    SqlAlchemyMediaConflictRepository,
)
from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.scan_run_repository import (
    SqlAlchemyScanRunRepository,
)
from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.repositories.subtitle_ocr_run_repository import (
    SqlAlchemySubtitleOcrRunRepository,
)

__all__ = [
    "SQLAlchemyMovieRepository",
    "SQLAlchemySeriesRepository",
    "SqlAlchemyIntroDetectionRunRepository",
    "SqlAlchemyMediaConflictRepository",
    "SqlAlchemyScanRunRepository",
    "SqlAlchemySubtitleOcrRunRepository",
]
