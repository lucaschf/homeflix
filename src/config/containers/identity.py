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
    GetActiveProfileForSessionUseCase,
    ListProfilesForUserUseCase,
    SwitchProfileUseCase,
    UpdateProfileUseCase,
    UploadProfileAvatarUseCase,
)
from src.modules.identity.application.use_cases.create_admin_user import (
    CreateAdminUserUseCase,
)
from src.modules.identity.application.use_cases.delete_admin_user import (
    DeleteAdminUserUseCase,
)
from src.modules.identity.application.use_cases.get_user_detail import (
    GetUserDetailUseCase,
)
from src.modules.identity.application.use_cases.list_users import ListUsersUseCase
from src.modules.identity.application.use_cases.update_user_role import (
    UpdateUserRoleUseCase,
)
from src.modules.identity.infrastructure.auth.password_hasher import (
    FastApiUsersPasswordHasher,
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
    event_bus = providers.Dependency()

    # Avatar storage configuration. ``thumbnails_directory`` stays a
    # filesystem path bootstrap-style. The bucket fields (subdir,
    # max_size, size_pixels) come from ``RuntimeSettings`` via ADR-013
    # phase 3.
    thumbnails_directory = providers.Dependency(default="./thumbnails")
    runtime_settings = providers.Dependency()

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
        runtime_settings=runtime_settings,
        root_directory=thumbnails_directory,
    )

    password_hasher = providers.Singleton(FastApiUsersPasswordHasher)

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

    get_active_profile_for_session = providers.Factory(
        GetActiveProfileForSessionUseCase,
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

    # ─── Admin user use cases ──────────────────────────────

    list_users = providers.Factory(
        ListUsersUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    get_user_detail = providers.Factory(
        GetUserDetailUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    create_admin_user = providers.Factory(
        CreateAdminUserUseCase,
        uow_factory=identity_unit_of_work_factory,
        password_hasher=password_hasher,
    )

    update_user_role = providers.Factory(
        UpdateUserRoleUseCase,
        uow_factory=identity_unit_of_work_factory,
    )

    delete_admin_user = providers.Factory(
        DeleteAdminUserUseCase,
        uow_factory=identity_unit_of_work_factory,
        event_bus=event_bus,
    )
