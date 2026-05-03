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
    DeleteProfileUseCase,
    ListProfilesForUserUseCase,
    SwitchProfileUseCase,
    UpdateProfileUseCase,
)
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)


class IdentityContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for the identity bounded context.

    Provides the ``IdentityUnitOfWork`` factory and the five profile
    use cases. The FastAPI Users-backed authentication routes do not
    flow through this container (see module docstring).
    """

    # Wired from InfrastructureContainer via the application container.
    session_factory = providers.Dependency()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    identity_unit_of_work_factory = providers.Singleton(
        SqlAlchemyIdentityUnitOfWorkFactory,
        session_factory=session_factory,
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
    )

    switch_profile = providers.Factory(
        SwitchProfileUseCase,
        uow_factory=identity_unit_of_work_factory,
    )
