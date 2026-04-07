"""Mapper between WatchProgress entity and WatchProgressModel."""

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import ProgressId
from src.modules.watch_progress.infrastructure.persistence.models import (
    WatchProgressModel,
)


class WatchProgressMapper:
    """Bidirectional mapper between WatchProgress entity and ORM model.

    Example:
        >>> model = WatchProgressMapper.to_model(entity)
        >>> entity = WatchProgressMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: WatchProgress) -> WatchProgressModel:
        """Convert WatchProgress entity to ORM model.

        Args:
            entity: The domain entity.

        Returns:
            SQLAlchemy model ready for persistence.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return WatchProgressModel(
            external_id=str(entity.id),
            media_id=entity.media_id,
            media_type=entity.media_type,
            position_seconds=entity.position_seconds,
            duration_seconds=entity.duration_seconds,
            status=entity.status,
            audio_track=entity.audio_track,
            subtitle_track=entity.subtitle_track,
            last_watched_at=entity.last_watched_at,
            completed_at=entity.completed_at,
        )

    @staticmethod
    def to_entity(model: WatchProgressModel) -> WatchProgress:
        """Convert ORM model to WatchProgress entity.

        Args:
            model: The SQLAlchemy model.

        Returns:
            Domain WatchProgress entity.
        """
        return WatchProgress(
            id=ProgressId(model.external_id),
            media_id=model.media_id,
            media_type=model.media_type,
            position_seconds=model.position_seconds,
            duration_seconds=model.duration_seconds,
            status=model.status,
            audio_track=model.audio_track,
            subtitle_track=model.subtitle_track,
            last_watched_at=model.last_watched_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: WatchProgressModel, entity: WatchProgress) -> WatchProgressModel:
        """Update existing ORM model with entity data.

        Args:
            model: The existing model.
            entity: The updated entity.

        Returns:
            The updated model.
        """
        model.position_seconds = entity.position_seconds
        model.duration_seconds = entity.duration_seconds
        model.status = entity.status
        model.audio_track = entity.audio_track
        model.subtitle_track = entity.subtitle_track
        model.last_watched_at = entity.last_watched_at
        model.completed_at = entity.completed_at
        return model


__all__ = ["WatchProgressMapper"]
