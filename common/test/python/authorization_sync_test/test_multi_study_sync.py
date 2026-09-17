"""Regression tests for cross-study grant revocation in the sync service.

A center user holds authorizations for several studies that all belong to
the same center group. The Authorization API's permissions endpoint returns
every grant a user holds of a given type, across all studies. If the studies
are synced one at a time, each per-study diff sees the previous study's grants
as "not desired" and revokes them, so only the last study's grants survive.

These tests drive the sync service against a stateful in-memory client that
persists grants across batch calls (like the real API) so that any cross-study
revocation shows up as revoke operations.
"""

from dataclasses import dataclass, field

from authorization.models import (
    BatchOperation,
    BatchResult,
    PermissionEntry,
    UserPermissions,
)
from authorization_sync.sync_service import AuthorizationSyncService
from users.authorizations import (
    Activities,
    Activity,
    DatatypeResource,
    StudyAuthorizations,
)
from users.event_models import UserEventCollector


@dataclass
class StatefulAuthorizationClient:
    """In-memory client that persists grants across batch calls.

    Models the real API closely enough to expose cross-study revocation:
    ``get_user_permissions`` returns every grant the user currently
    holds of the requested type, regardless of which study it belongs
    to.
    """

    # (user_id, resource_type, resource_id, relation)
    grants: set[tuple[str, str, str, str]] = field(default_factory=set)
    batch_calls: list[list[BatchOperation]] = field(default_factory=list)

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        entries: list[PermissionEntry] = [
            PermissionEntry(resource_id=resource_id, relation=relation)
            for (uid, rtype, resource_id, relation) in self.grants
            if uid == user_id and rtype == type_filter
        ]
        permissions = {type_filter: entries} if entries else {}
        return UserPermissions(user_id=user_id, permissions=permissions)

    def batch(self, operations: list[BatchOperation]) -> BatchResult:
        self.batch_calls.append(operations)
        for op in operations:
            key = (op.user_id, op.resource_type, op.resource_id, op.relation)
            if op.action == "grant":
                self.grants.add(key)
            else:
                self.grants.discard(key)
        return BatchResult(
            total=len(operations),
            succeeded=len(operations),
            failed=0,
            errors=[],
        )


def _study_auth(study_id: str, datatype: str) -> StudyAuthorizations:
    """Build a StudyAuthorizations with one submit-audit datatype activity."""
    activities = Activities()
    resource = DatatypeResource(datatype=datatype)
    activities.add(resource, Activity(resource=resource, action="submit-audit"))
    return StudyAuthorizations(study_id=study_id, activities=activities)


def _revoke_ops(client: StatefulAuthorizationClient) -> list[BatchOperation]:
    return [
        op
        for operations in client.batch_calls
        for op in operations
        if op.action == "revoke"
    ]


class TestMultiStudySyncNoRevocation:
    """sync_users must reconcile all studies against current grants at once."""

    def test_two_studies_synced_together_revokes_nothing(self) -> None:
        """Two studies with distinct grants produce only grant operations.

        With per-study syncing this would revoke study 1's grants while
        adding study 2's. Syncing them together must revoke nothing,
        since both studies' grants are desired.
        """
        client = StatefulAuthorizationClient()
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        study_1 = _study_auth("study-1", "form")
        study_2 = _study_auth("study-2", "enrollment")

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[study_1, study_2],
            center_group_id="washington",
        )

        # No grant should be revoked: both studies are desired.
        assert _revoke_ops(client) == []

        # Both studies' grants end up present in the API. Resource IDs embed
        # the study id as a suffix (e.g. "washington_ingest-form-study-1").
        resource_ids = {resource_id for (_, _, resource_id, _) in client.grants}
        assert any(rid.endswith("-study-1") for rid in resource_ids)
        assert any(rid.endswith("-study-2") for rid in resource_ids)

    def test_grants_persist_for_all_studies_after_sync(self) -> None:
        """After syncing, every study's grant survives in the API state.

        This is the user-visible symptom of the bug: with per-study
        sync, only the last study retains access.
        """
        client = StatefulAuthorizationClient()
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        studies = [
            _study_auth("study-1", "form"),
            _study_auth("study-2", "enrollment"),
            _study_auth("study-3", "dicom"),
        ]

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=studies,
            center_group_id="washington",
        )

        resource_ids = {resource_id for (_, _, resource_id, _) in client.grants}
        assert any(rid.endswith("-study-1") for rid in resource_ids)
        assert any(rid.endswith("-study-2") for rid in resource_ids)
        assert any(rid.endswith("-study-3") for rid in resource_ids)

    def test_stale_grant_is_revoked_when_no_longer_desired(self) -> None:
        """A grant present in the API but absent from the desired set is
        revoked.

        Confirms the aggregated diff still revokes genuinely stale
        grants rather than never revoking anything.
        """
        client = StatefulAuthorizationClient()
        # Pre-seed a grant for a study the user no longer has.
        client.grants.add(
            (
                "user@institution.edu",
                "data_pipeline",
                "washington_ingest-form-old-study",
                "submitter",
            )
        )
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        revoked_ids = {op.resource_id for op in _revoke_ops(client)}
        assert "washington_ingest-form-old-study" in revoked_ids

    def test_sync_user_delegates_to_single_study_diff(self) -> None:
        """sync_user (single authorization) still works via the shared path.

        The general (non-center) path uses sync_user; it should grant
        the single authorization's grants and revoke nothing on a clean
        state.
        """
        client = StatefulAuthorizationClient()
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=_study_auth("study-1", "form"),
            center_group_id="washington",
        )

        assert _revoke_ops(client) == []
        assert len(client.grants) > 0
