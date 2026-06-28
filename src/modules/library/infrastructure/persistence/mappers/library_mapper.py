"""Mapper between Library domain entity and LibraryModel ORM model."""

import json
from datetime import UTC, datetime
from typing import Any

from src.building_blocks.domain.errors import DomainValidationException
from src.config.logging import get_logger
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.cron_expression import CronExpression
from src.modules.library.domain.value_objects.library_name import LibraryName
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)
from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.modules.library.infrastructure.persistence.models.library_model import LibraryModel
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.library_id import LibraryId

_logger = get_logger()


def _safe_cron(raw: str | None) -> CronExpression | None:
    """Coerce a persisted cron string, degrading invalid values to None.

    The write path (API/use cases) rejects invalid crons via
    ``CronExpression``, but a row persisted before that invariant existed
    (or hand-edited) must not make a whole ``find_all`` blow up. A bad
    value is logged and dropped to ``None`` — equivalent to the legacy
    behaviour where the scheduler simply skipped an unparseable cron.
    """
    if not raw:
        return None
    try:
        return CronExpression(raw)
    except DomainValidationException:
        _logger.warning("Dropping invalid persisted scan_schedule", scan_schedule=raw)
        return None


def _ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to naive datetimes loaded from the DB.

    SQLite stores datetimes without timezone info even when the column
    is declared ``DateTime(timezone=True)``. Without this normalisation
    the entity would round-trip a naive datetime, and JSON serialisers
    would emit an ISO string with no offset — which JS clients then
    interpret as local time, shifting the displayed timestamp by the
    user's UTC offset.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class LibraryMapper:
    """Bidirectional mapper between Library entity and LibraryModel.

    Complex nested value objects (paths, settings, metadata providers)
    are serialized to JSON for the Text columns and reconstructed on
    the way back.  All other fields map 1:1 through their VO's
    ``.value`` property.
    """

    @staticmethod
    def to_model(entity: Library) -> LibraryModel:
        """Convert Library entity to LibraryModel for persistence.

        Args:
            entity: The domain Library entity (must have an id).

        Returns:
            SQLAlchemy LibraryModel ready for ``session.add()``.
        """
        if entity.id is None:
            raise ValueError("Cannot map entity without ID to model")

        return LibraryModel(
            external_id=str(entity.id),
            name=entity.name.value,
            library_type=entity.library_type.value,
            paths=json.dumps([p.value for p in entity.paths], ensure_ascii=False),
            language=entity.language.value,
            metadata_providers=json.dumps(
                [
                    {
                        "provider": p.provider.value,
                        "priority": p.priority,
                        "enabled": p.enabled,
                    }
                    for p in entity.metadata_providers
                ],
                ensure_ascii=False,
            ),
            scan_schedule=entity.scan_schedule.value if entity.scan_schedule else None,
            last_scan_at=entity.last_scan_at,
            settings=json.dumps(
                {
                    "preferred_audio_language": entity.settings.preferred_audio_language.value,
                    "preferred_subtitle_language": (
                        entity.settings.preferred_subtitle_language.value
                        if entity.settings.preferred_subtitle_language
                        else None
                    ),
                    "subtitle_mode": entity.settings.subtitle_mode.value,
                    "generate_thumbnails": entity.settings.generate_thumbnails,
                    "detect_intros": entity.settings.detect_intros,
                    "auto_refresh_metadata": entity.settings.auto_refresh_metadata,
                },
                ensure_ascii=False,
            ),
        )

    @staticmethod
    def to_entity(model: LibraryModel) -> Library:
        """Convert LibraryModel to Library domain entity.

        Args:
            model: The SQLAlchemy LibraryModel.

        Returns:
            Domain Library entity with reconstructed value objects.
        """
        paths_raw: list[str] = json.loads(model.paths)
        providers_raw: list[dict[str, Any]] = json.loads(model.metadata_providers)
        settings_raw: dict[str, Any] = json.loads(model.settings)

        return Library(
            id=LibraryId(model.external_id),
            name=LibraryName(model.name),
            library_type=LibraryType(model.library_type),
            paths=[FilePath(p) for p in paths_raw],
            language=LanguageCode(model.language),
            metadata_providers=[
                MetadataProviderConfig(
                    provider=MetadataProvider(p["provider"]),
                    priority=p["priority"],
                    enabled=p.get("enabled", True),
                )
                for p in providers_raw
            ],
            scan_schedule=_safe_cron(model.scan_schedule),
            last_scan_at=_ensure_utc(model.last_scan_at),
            settings=LibrarySettings(
                preferred_audio_language=LanguageCode(
                    settings_raw.get("preferred_audio_language", "en"),
                ),
                preferred_subtitle_language=(
                    LanguageCode(settings_raw["preferred_subtitle_language"])
                    if settings_raw.get("preferred_subtitle_language")
                    else None
                ),
                subtitle_mode=SubtitleMode(
                    settings_raw.get("subtitle_mode", SubtitleMode.FOREIGN_AUDIO_ONLY.value),
                ),
                generate_thumbnails=settings_raw.get("generate_thumbnails", True),
                detect_intros=settings_raw.get("detect_intros", False),
                auto_refresh_metadata=settings_raw.get("auto_refresh_metadata", False),
            ),
        )

    @staticmethod
    def update_model(model: LibraryModel, entity: Library) -> LibraryModel:
        """Apply entity field values onto an existing model.

        Used by ``save()`` when the library already exists in the DB
        (update path). Only domain-owned fields are touched — the
        base columns (id, created_at, etc.) stay unchanged.

        Args:
            model: The existing SQLAlchemy model to update in-place.
            entity: The domain entity carrying the new state.

        Returns:
            The same ``model`` reference, mutated.
        """
        fresh = LibraryMapper.to_model(entity)
        model.name = fresh.name
        model.library_type = fresh.library_type
        model.paths = fresh.paths
        model.language = fresh.language
        model.metadata_providers = fresh.metadata_providers
        model.scan_schedule = fresh.scan_schedule
        model.last_scan_at = fresh.last_scan_at
        model.settings = fresh.settings
        return model


__all__ = ["LibraryMapper"]
