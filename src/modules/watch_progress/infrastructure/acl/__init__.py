"""Anti-corruption layer: adapters translating external BCs to local ports."""

from src.modules.watch_progress.infrastructure.acl.media_lookup_adapter import (
    MediaLookupAdapter,
)

__all__ = ["MediaLookupAdapter"]
