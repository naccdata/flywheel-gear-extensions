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
    ResourceObject,
    UserPermissions,
)
from authorization_sync.sync_service import AuthorizationSyncService
from users.authorizations import (
    Activities,
    Activity,
    Authorizations,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)
from users.event_models import UserEventCollector


def _resource_object(
    resource_type: str,
    resource_id: str,
    community: str | None = None,
) -> ResourceObject:
    """Build the structured resource the real API returns for a grant.

    The API enriches each permission entry with the resource's parents
    from the catalog. This models the center parent the way ADR-016
    resource ids encode it: center-scoped ids are ``{center}_{label}``
    (center names never contain underscores), and general (non-center)
    ids have no such prefix. Study is left unset — a center sync owns
    every study under the center, so the scope filter keys on center,
    not study. A ``community`` parent is set only when explicitly
    requested, modeling a community-scoped resource the center sync must
    not revoke.
    """
    center: str | None = None
    if "_" in resource_id:
        center = resource_id.split("_", 1)[0]
    return ResourceObject(
        type=resource_type,
        id=resource_id,
        center=center,
        community=community,
    )


@dataclass
class StatefulAuthorizationClient:
    """In-memory client that persists grants across batch calls.

    Models the real API closely enough to expose cross-study revocation:
    ``get_user_permissions`` returns every grant the user currently
    holds of the requested type, regardless of which study it belongs
    to. Each entry is enriched with a structured ``resource`` carrying
    the grant's center parent, as the real API does, so the sync's scope
    filter can distinguish center scopes from the general scope.
    """

    # (user_id, resource_type, resource_id, relation)
    grants: set[tuple[str, str, str, str]] = field(default_factory=set)
    batch_calls: list[list[BatchOperation]] = field(default_factory=list)
    # resource ids for which the API returns no structured scope (catalog
    # gap): entries for these are returned with resource=None.
    scopeless_resource_ids: set[str] = field(default_factory=set)
    # resource id -> community parent: entries for these are returned with
    # a community-scoped resource, which a center/general sync must not
    # revoke.
    community_resource_ids: dict[str, str] = field(default_factory=dict)

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        entries: list[PermissionEntry] = [
            PermissionEntry(
                resource_id=resource_id,
                relation=relation,
                resource=(
                    None
                    if resource_id in self.scopeless_resource_ids
                    else _resource_object(
                        rtype,
                        resource_id,
                        community=self.community_resource_ids.get(resource_id),
                    )
                ),
            )
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


def _general_page_auth(page: str) -> Authorizations:
    """Build general (non-center) authorizations with one page view."""
    activities = Activities()
    resource = PageResource(page=page)
    activities.add(resource, Activity(resource=resource, action="view"))
    return Authorizations(activities=activities)


class TestCrossScopeSyncNoRevocation:
    """Revokes stay within the scope being reconciled by a sync call.

    The permissions endpoint returns every grant a user holds across all
    scopes. A sync call reconciles one scope — a specific center, or the
    general (non-center) scope. Revokes must be confined to that scope
    so a general sync never revokes center grants and a center sync
    never revokes general or other-center grants.
    """

    def test_general_sync_does_not_revoke_center_grants(self) -> None:
        """The general sync leaves a user's center grants untouched.

        Reproduces the production over-revoke: a user with an empty (or
        page-only) general authorization set but real center grants had
        those center grants revoked by the general sync.
        """
        client = StatefulAuthorizationClient()
        # Pre-seed a center grant the general sync must not touch.
        client.grants.add(
            (
                "user@institution.edu",
                "data_pipeline",
                "washington_ingest-form-study-1",
                "submitter",
            )
        )
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        # General sync (center_group_id=None) with only a page grant.
        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=_general_page_auth("community-resources"),
        )

        revoked_ids = {op.resource_id for op in _revoke_ops(client)}
        assert "washington_ingest-form-study-1" not in revoked_ids
        # The center grant survives in API state.
        surviving = {resource_id for (_, _, resource_id, _) in client.grants}
        assert "washington_ingest-form-study-1" in surviving

    def test_general_sync_with_empty_desired_revokes_nothing_out_of_scope(
        self,
    ) -> None:
        """An empty general desired set revokes no center grants.

        This is the Registry100821 case: general activities are empty,
        so the desired set is empty, but the user holds center grants.
        The general sync must not revoke them (previously it revoked
        all).
        """
        client = StatefulAuthorizationClient()
        for datatype in ("form", "enrollment", "dicom"):
            client.grants.add(
                (
                    "user@institution.edu",
                    "data_pipeline",
                    f"washington_ingest-{datatype}-study-1",
                    "submitter",
                )
            )
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        # Empty general authorizations -> empty desired set.
        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=Authorizations(),
        )

        assert _revoke_ops(client) == []
        assert len(client.grants) == 3

    def test_center_sync_does_not_revoke_general_grants(self) -> None:
        """A center sync leaves the user's general grants untouched."""
        client = StatefulAuthorizationClient()
        # Pre-seed a general (non-center) page grant.
        client.grants.add(
            (
                "user@institution.edu",
                "page",
                "page-community-resources",
                "viewer",
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
        assert "page-community-resources" not in revoked_ids
        surviving = {resource_id for (_, _, resource_id, _) in client.grants}
        assert "page-community-resources" in surviving

    def test_center_sync_does_not_revoke_other_center_grants(self) -> None:
        """A sync for center A leaves center B's grants untouched."""
        client = StatefulAuthorizationClient()
        # Pre-seed a grant belonging to a different center.
        client.grants.add(
            (
                "user@institution.edu",
                "data_pipeline",
                "columbia_ingest-form-study-1",
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
        assert "columbia_ingest-form-study-1" not in revoked_ids
        surviving = {resource_id for (_, _, resource_id, _) in client.grants}
        assert "columbia_ingest-form-study-1" in surviving

    def test_grant_with_unknown_scope_is_never_revoked(self) -> None:
        """A current grant with no API-reported scope is never revoked.

        Models a catalog gap: the permissions endpoint returns the grant
        with resource=None. Scope cannot be confirmed, so the grant must
        be left alone even when it is absent from the desired set and
        would otherwise look in-scope.
        """
        client = StatefulAuthorizationClient()
        client.grants.add(
            (
                "user@institution.edu",
                "data_pipeline",
                "washington_ingest-form-orphan",
                "submitter",
            )
        )
        # The API cannot report scope for this resource.
        client.scopeless_resource_ids.add("washington_ingest-form-orphan")
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
        assert "washington_ingest-form-orphan" not in revoked_ids
        surviving = {resource_id for (_, _, resource_id, _) in client.grants}
        assert "washington_ingest-form-orphan" in surviving

    def test_center_sync_does_not_revoke_community_scoped_grant(self) -> None:
        """A community-scoped grant is never revoked by a center sync.

        The API can return a resource that carries both a center and a
        community parent. Such a resource belongs to the community
        scope, which this gear does not reconcile, so a center sync must
        leave it alone even though its center matches the call's center
        and it is absent from the desired set.
        """
        client = StatefulAuthorizationClient()
        client.grants.add(
            (
                "user@institution.edu",
                "page",
                "washington_page-shared-community",
                "viewer",
            )
        )
        # The API reports this resource under a community parent.
        client.community_resource_ids["washington_page-shared-community"] = "nacc"
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
        assert "washington_page-shared-community" not in revoked_ids
        surviving = {resource_id for (_, _, resource_id, _) in client.grants}
        assert "washington_page-shared-community" in surviving
