"""Sync service for computing permission diffs and constructing batch
operations."""

import logging
from typing import Protocol

from authorization.exceptions import AuthorizationClientError
from authorization.models import (
    AuthorizationModelMetadata,
    BatchOperation,
    BatchResult,
    UserPermissions,
    UserProfile,
    UserProfileRequest,
)
from users.authorizations import Authorizations
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)
from users.user_entry import UserEntry

from authorization_sync.models import DesiredGrant
from authorization_sync.translator import (
    ACTIVITY_RELATION_MAP,
    translate,
    validate_activity_relation_map,
)

log = logging.getLogger(__name__)

# Resource types queried during sync — derived from ACTIVITY_RELATION_MAP values.
# The permissions endpoint requires one type per request (ADR-015).
_SYNC_RESOURCE_TYPES: frozenset[str] = frozenset(
    {
        resource_type
        for pairs in ACTIVITY_RELATION_MAP.values()
        for resource_type, _ in pairs
    }
)


class AuthorizationClientProtocol(Protocol):
    """Protocol defining the client interface needed by the sync service."""

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str,
        relation_filter: str | None = None,
    ) -> UserPermissions: ...

    def batch(
        self,
        operations: list[BatchOperation],
    ) -> BatchResult: ...

    def put_user_profile(
        self,
        profile_user_id: str,
        request: UserProfileRequest,
    ) -> UserProfile: ...

    def get_model(self) -> AuthorizationModelMetadata: ...


class AuthorizationSyncService:
    """Orchestrates the query-diff-apply cycle for user grant
    synchronization."""

    def __init__(
        self,
        client: AuthorizationClientProtocol,
        collector: UserEventCollector,
    ) -> None:
        """Initialize with an authorization client and event collector.

        Args:
            client: The authorization client for API calls.
            collector: Event collector for reporting sync outcomes.
        """
        self._client = client
        self._collector = collector

    def validate_model(self) -> None:
        """Validate the activity-relation map against the live model.

        Fetches the model from the API and logs warnings for any
        mappings that reference unknown types, unknown relations, or
        non-assignable relations. Does not raise — validation failures
        are informational only.
        """
        try:
            model = self._client.get_model()
        except AuthorizationClientError as error:
            log.warning(
                "Could not fetch authorization model for validation: %s. "
                "Sync operations for resource types %s may fail at runtime "
                "if the activity-relation map is stale.",
                error,
                sorted(_SYNC_RESOURCE_TYPES),
            )
            return

        warnings = validate_activity_relation_map(model)
        if warnings:
            affected_types = sorted(
                {w.split("-> (")[1].split(",")[0] for w in warnings if "-> (" in w}
            )
            log.warning(
                "ACTIVITY_RELATION_MAP has %d invalid mapping(s) affecting "
                "resource types %s. Grants to these types may be rejected "
                "by the API at sync time.",
                len(warnings),
                affected_types,
            )
            for warning in warnings:
                log.warning(warning)
        else:
            log.info("ACTIVITY_RELATION_MAP validated against live model: all OK")

    def sync_user(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str | None = None,
    ) -> None:
        """Synchronize grants for a user's authorizations.

        Translates the authorizations to desired grants, queries current
        grants from the API, computes the diff, and applies changes via
        batch.

        Catches all AuthorizationClientError exceptions and reports via
        the event collector without raising.

        Args:
            registry_id: The user's registry ID (ePPN).
            authorizations: The authorizations to sync.
            center_group_id: The Flywheel group ID for the center, or
                None for general authorizations.
        """
        try:
            desired = translate(
                registry_id=registry_id,
                authorizations=authorizations,
                center_group_id=center_group_id,
            )

            # Query current permissions per type (type is required per ADR-015)
            current: set[DesiredGrant] = set()
            for resource_type in _SYNC_RESOURCE_TYPES:
                permissions = self._client.get_user_permissions(
                    user_id=registry_id,
                    type_filter=resource_type,
                )
                current |= permissions.to_grants(DesiredGrant)

            grants_to_add = desired - current
            grants_to_revoke = current - desired

            if not grants_to_add and not grants_to_revoke:
                log.info(
                    "No grant changes needed for user %s",
                    registry_id,
                )
                return

            operations = [g.to_batch_op("grant") for g in grants_to_add] + [
                g.to_batch_op("revoke") for g in grants_to_revoke
            ]

            result = self._client.batch(operations)

            if result.failed > 0:
                self._report_partial_failure(registry_id, result)

            log.info(
                "Authorization sync for user %s: %d added, %d revoked, %d failed",
                registry_id,
                len(grants_to_add),
                len(grants_to_revoke),
                result.failed,
            )

        except AuthorizationClientError as error:
            log.error(
                "Authorization sync failed for user %s: %s",
                registry_id,
                error,
            )
            self._report_failure(registry_id, "sync", error)

    def sync_profile(
        self,
        registry_id: str,
        user_entry: UserEntry,
    ) -> None:
        """Push a user profile to the Authorization API.

        Constructs a UserProfileRequest from the user entry fields and
        calls put_user_profile. Catches AuthorizationClientError and
        reports via the event collector without raising.

        Skips sync if user_entry.auth_email is None (logs warning).

        Args:
            registry_id: The user's registry ID (used as Profile_User_ID).
            user_entry: The user entry containing profile data.
        """
        if user_entry.auth_email is None:
            log.warning(
                "Skipping profile sync for user %s: auth_email is None",
                user_entry.email,
            )
            return

        try:
            request = UserProfileRequest(
                first_name=user_entry.first_name,
                last_name=user_entry.last_name,
                email=user_entry.email,
                auth_email=user_entry.auth_email,
                active=user_entry.active,
            )
            self._client.put_user_profile(registry_id, request)
        except AuthorizationClientError as error:
            log.error(
                "Profile sync failed for user %s: %s",
                registry_id,
                error,
            )
            self._report_failure(registry_id, "profile_sync", error)

    def _report_failure(
        self,
        registry_id: str,
        operation: str,
        error: Exception,
    ) -> None:
        """Report a sync failure via the event collector.

        Args:
            registry_id: The user's registry ID.
            operation: The operation that failed.
            error: The exception that occurred.
        """
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.AUTHORIZATION_SYNC,
            user_context=UserContext(
                registry_id=registry_id,
                email="",
            ),
            message=f"Authorization sync {operation} failed: {error}",
        )
        self._collector.collect(event)

    def _report_partial_failure(
        self,
        registry_id: str,
        result: BatchResult,
    ) -> None:
        """Report individual batch errors via the event collector.

        Args:
            registry_id: The user's registry ID.
            result: The batch result containing error details.
        """
        for error in result.errors:
            event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.AUTHORIZATION_SYNC,
                user_context=UserContext(
                    registry_id=registry_id,
                    email="",
                ),
                message=(f"Authorization sync batch operation failed: {error.message}"),
            )
            self._collector.collect(event)
