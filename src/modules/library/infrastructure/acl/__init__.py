"""Anti-corruption layer: adapters translating external BCs to local ports."""

from src.modules.library.infrastructure.acl.media_count_query_adapter import (
    MediaCountQueryAdapter,
)

__all__ = ["MediaCountQueryAdapter"]
