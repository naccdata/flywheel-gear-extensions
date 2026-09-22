"""Sync service for computing permission diffs and constructing batch
operations."""

import logging
from collections.abc import Iterable
from typing import Protocol

from authorization.exceptions import AuthorizationClientError
from authorization.models import (
    AuthorizationModelMetadata,
    BatchOperation,
    BatchResult,
    PermissionEntry,
    UserPermissions,
    UserProfile,
    UserProfileRequest,
)
from authorization_sync.models import DesiredGrant
from authorization_sync.translator import (
    ACTIVITY_RELATION_MAP,
    translate,
    validate_activity_relation_map,
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


def _entry_in_scope(
    entry: PermissionEntry,
    center_group_id: str | None,
) -> bool:
    """Report whether a permission entry belongs to the scope being synced.

    A sync call reconciles exactly one scope: a specific center (when
    ``center_group_id`` is set) or the general, non-center scope (when it
    is None). A center sync owns every study under that center — the
    caller aggregates all of the user's studies for the center into one
    call — so scope is keyed on the center, not the study. This is what
    lets a dropped study's grants be revoked while the studies the user
    still holds are preserved.

    The entry's scope is read from the structured ``resource`` the API
    returns, never parsed out of the flat resource id (per the
    Authorization API contract). An entry is in scope when its center
    matches the call's center **and** it carries no community parent —
    a community-scoped resource is a different scope even if it also
    names a center, and this gear never reconciles community grants.

    When the API does not return structured scope for the entry
    (``resource`` is None, e.g. a catalog gap), the scope cannot be
    confirmed and the entry is treated as out of scope so it is never
    revoked.

    Args:
        entry: The permission entry from the API.
        center_group_id: The center group id being reconciled, or None
            for the general scope.

    Returns:
        True if the entry belongs to the scope being reconciled.
    """
    if entry.resource is None:
        # Scope cannot be confirmed; never eligible for revocation.
        return False

    # A community-scoped resource is out of scope for center/general sync,
    # even when it also carries a center parent.
    if entry.resource.community is not None:
        return False

    return entry.resource.center == center_group_id


def _grants_in_scope(
    permissions: UserPermissions,
    center_group_id: str | None,
) -> set[DesiredGrant]:
    """Build the set of current grants that belong to the synced scope.

    Only entries whose scope matches ``center_group_id`` (per
    :func:`_entry_in_scope`) are included, so the returned grants are the
    revoke-eligible subset of the user's current grants for this call.

    Args:
        permissions: The user's current permissions for one resource
            type.
        center_group_id: The center group id being reconciled, or None
            for the general scope.

    Returns:
        Set of DesiredGrant objects for the in-scope current grants.
    """
    grants: set[DesiredGrant] = set()
    for resource_type, entries in permissions.permissions.items():
        for entry in entries:
            if not _entry_in_scope(entry, center_group_id):
                continue
            grants.add(
                DesiredGrant(
                    user_id=permissions.user_id,
                    resource_type=resource_type,
                    resource_id=entry.resource_id,
                    relation=entry.relation,
                )
            )
    return grants


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
        """Synchronize grants for a single set of user authorizations.

        Translates the authorizations to desired grants, queries current
        grants from the API, computes the diff, and applies changes via
        batch.

        Use this for a user's general (non-center) authorizations. For a
        user's center authorizations, which span multiple studies that
        share a center group, use ``sync_users`` so the desired set covers
        all studies at once. Syncing studies one at a time against the
        user's full current grant set causes each study to revoke the
        grants of the previously-synced studies.

        Catches all AuthorizationClientError exceptions and reports via
        the event collector without raising.

        Args:
            registry_id: The user's registry ID (ePPN).
            authorizations: The authorizations to sync.
            center_group_id: The Flywheel group ID for the center, or
                None for general authorizations.
        """
        self.sync_users(
            registry_id=registry_id,
            authorizations=[authorizations],
            center_group_id=center_group_id,
        )

    def sync_users(
        self,
        registry_id: str,
        authorizations: Iterable[Authorizations],
        center_group_id: str | None = None,
    ) -> None:
        """Synchronize grants for several authorization sets in one diff.

        Translates every authorization set to desired grants and unions
        them into a single desired set, queries the user's current grants
        once, computes a single diff, and applies all changes in one
        batch.

        All authorization sets must share the same ``center_group_id``,
        since the resource IDs of the desired grants are built relative to
        it. This is the case for a center user, whose studies all belong to
        one center group.

        Aggregating the studies before diffing is what prevents cross-study
        revocation: the current grant set returned by the API spans all of
        the user's studies, so it must be diffed against the desired grants
        for all studies, not one study at a time.

        Revocation is scoped to the center being reconciled (or the
        general, non-center scope when ``center_group_id`` is None). The
        current grant set returned by the API spans every scope the user
        holds, so revoke candidates are restricted to grants whose center
        matches this call's ``center_group_id`` and that carry no community
        parent. A center sync owns every study under that center — the
        studies are aggregated into one call — so a dropped study's grant
        is still revoked while the studies the user still holds are kept.
        This prevents a call for one scope from revoking another scope's
        grants: the general sync no longer revokes a user's center grants,
        and a center sync no longer revokes the user's general or
        other-center grants. Grants whose scope the API does not report are
        never revoked.

        Catches all AuthorizationClientError exceptions and reports via
        the event collector without raising.

        Args:
            registry_id: The user's registry ID (ePPN).
            authorizations: The authorization sets to sync together. All
                must share the given ``center_group_id``.
            center_group_id: The Flywheel group ID for the center, or
                None for general authorizations.
        """
        try:
            desired: set[DesiredGrant] = set()
            for authorization in authorizations:
                desired |= translate(
                    registry_id=registry_id,
                    authorizations=authorization,
                    center_group_id=center_group_id,
                )

            # Query current permissions per type (type is required per ADR-015)
            current: set[DesiredGrant] = set()
            in_scope_current: set[DesiredGrant] = set()
            for resource_type in _SYNC_RESOURCE_TYPES:
                permissions = self._client.get_user_permissions(
                    user_id=registry_id,
                    type_filter=resource_type,
                )
                current |= permissions.to_grants(DesiredGrant)
                in_scope_current |= _grants_in_scope(permissions, center_group_id)

            # Adds may target any scope this call knows about; a grant already
            # present anywhere is not re-added.
            grants_to_add = desired - current

            # Revokes are restricted to grants that belong to the scope being
            # reconciled by this call (the center, or general when
            # center_group_id is None). A center sync owns every study under
            # that center, so a stale study's grant is still revoked, but
            # grants in other scopes — a different center, the general scope,
            # a community resource — and grants whose scope cannot be
            # determined are never revoked here.
            grants_to_revoke = in_scope_current - desired

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
