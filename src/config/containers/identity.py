"""Identity bounded context dependency container.

Exposes only the application-level use cases via dependency-injector.
The FastAPI Users wiring (``UserManager``, ``auth_backend``,
``current_active_user``) lives in
``src.modules.identity.infrastructure.auth`` because FastAPI Users
expects FastAPI-native ``Depends(...)`` chains rather than the
provider/factory model used here. The two coexist: routes pull use
case factories from this container and the auth deps from the auth
package.
"""

from dependency_injector import containers, providers

from src.modules.identity.application.use_cases import (
    CreateProfileUseCase,
    DeleteProfileAvatarUseCase,
    DeleteProfileUseCase,
    ListProfilesForUserUseCase,
    SwitchProfileUseCase,
    UpdateProfileUseCase,
    UploadProfileAvatarUseCase,
)
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.modules.identity.infrastructure.storage import LocalAvatarStorage


class IdentityContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for the identity bounded context.

    Provides the ``IdentityUnitOfWork`` factory, the avatar storage
    adapter and the profile use cases. The FastAPI Users-backed
    authentication routes do not flow through this container (see
    module docstring).
    """

    # Wired from InfrastructureContainer via the application container.
    session_factory = providers.Dependency()

    # Avatar storage configuration — wired from ``Settings`` at the
    # composition root. Defaults are present so tests / standalone
    # usage stay cheap to instantiate, but the production path
    # always overrides them via ``providers.Container(...)``.
    thumbnails_directory = providers.Dependency(default="./thumbnails")
    avatar_storage_subdir = providers.Dependency(default=".homeflix/avatars")
    avatar_max_size_mb = providers.Dependency(default=2)
    avatar_size_pixels = providers.Dependency(default=256)

    # =========================================================================
    # Unit of Work
    # =========================================================================

    identity_unit_of_work_factory = providers.Singleton(
        SqlAlchemyIdentityUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Storage
    # =========================================================================

    avatar_storage = providers.Singleton(
        LocalAvatarStorage,
        root_directory=thumbnails_directory,
        subdirectory=avatar_storage_subdir,
        max_size_mb=avatar_max_size_mb,
        side_length=avatar_size_pixels,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    create_profile = providers.Factory(
        CreateProfileUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    list_profiles_for_user = providers.Factory(
        ListProfilesForUserUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    update_profile = providers.Factory(
        UpdateProfileUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    delete_profile = providers.Factory(
        DeleteProfileUseCase,
        uow_factory=identity_unit_of_work_factory,
        avatar_storage=avatar_storage,
    )

    switch_profile = providers.Factory(
        SwitchProfileUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    upload_profile_avatar = providers.Factory(
        UploadProfileAvatarUseCase,
        uow_factory=identity_unit_of_work_factory,
        avatar_storage=avatar_storage,
    )

    delete_profile_avatar = providers.Factory(
        DeleteProfileAvatarUseCase,
        uow_factory=identity_unit_of_work_factory,
        avatar_storage=avatar_storage,
    )
