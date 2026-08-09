"""Mapper between ListFollow entity and ORM model."""

from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.value_objects import ListFollowId, ListId
from src.modules.collections.infrastructure.persistence.models import ListFollowModel
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListFollowMapper:
    """Bidirectional mapper between ``ListFollow`` entity and ORM model."""

    @staticmethod
    def to_model(entity: ListFollow) -> ListFollowModel:
        """Convert a ``ListFollow`` entity to an ORM model."""
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return ListFollowModel(
            external_id=str(entity.id),
            follower_profile_id=str(entity.follower_profile_id),
            list_id=str(entity.list_id),
        )

    @staticmethod
    def to_entity(model: ListFollowModel) -> ListFollow:
        """Convert an ORM model to a ``ListFollow`` entity."""
        return ListFollow(
            id=ListFollowId(model.external_id),
            follower_profile_id=ProfileId(model.follower_profile_id),
            list_id=ListId(model.list_id),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = ["ListFollowMapper"]
