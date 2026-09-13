"""End-to-end scaffolding for the app-wide presentation building blocks.

Reuses the collections e2e fixtures instead of copying them: that
scaffolding already registers the identity, media, watch progress and
collections tables, builds the app through ``create_app`` and logs in
with an active profile carrying a library ACL — everything a request to
the catalog, Continue Watching and the lists needs.
"""

from tests.modules.collections.e2e.conftest import (  # noqa: F401 — re-exported fixtures
    app,
    client,
    login_with_active_profile,
    seed_user_with_profile,
    session_factory,
)
