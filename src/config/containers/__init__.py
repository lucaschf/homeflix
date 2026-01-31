"""Dependency injection containers.

This package organizes DI containers by responsibility:
- infrastructure: Database, external clients
- repositories: Data access implementations
- use_cases/: Application use cases by bounded context

The main ApplicationContainer composes all sub-containers.
"""

from src.config.containers.main import ApplicationContainer

__all__ = ["ApplicationContainer"]
