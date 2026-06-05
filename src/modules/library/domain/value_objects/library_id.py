"""Library external ID value object.

``LibraryId`` moved to the shared_kernel (ADR-018) because it is
consumed by ``identity`` (profile library ACL) and ``media`` (catalog
filtering port) in addition to this module. This re-export keeps the
historical import path working while callers migrate incrementally.
"""

from src.shared_kernel.value_objects.library_id import LibraryId

__all__ = ["LibraryId"]
