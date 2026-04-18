"""Anti-corruption layer: adapters translating external BCs to local ports."""

from src.modules.media.infrastructure.acl.progress_lookup_adapter import (
    ProgressLookupAdapter,
)

__all__ = ["ProgressLookupAdapter"]
