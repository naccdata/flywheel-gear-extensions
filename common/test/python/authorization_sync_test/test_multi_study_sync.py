"""Sync-service diff tests keyed on the Structured Identity Tuple.

A center user holds authorizations for several studies that all belong to
the same center group. The Authorization API's permissions endpoint returns
every grant a user holds of a given type, across all studies. If the studies
are synced one at a time, each per-study diff sees the previous study's grants
as "not desired" and revokes them, so only the last study's grants survive.

These tests drive the sync service against a stateful in-memory client that
persists grants across batch calls (like the real API) so that any cross-study
revocation shows up as revoke operations.

The regression tests below exercise concrete scenarios; the property tests at
the end verify the universal correctness properties (design Properties 2, 3, 5,
6) that the structured-identity diff must satisfy. All matching is keyed on the
Structured Identity Tuple ``(resource_type, relation, resource_label, center,
study, community)`` — the server-owned ``flat_id`` is never part of the key.
"""

import json
from dataclasses import dataclass, field
from unittest.mock import patch

from authorization.client import AuthorizationClient
from authorization.models import (
    BatchOperation,
    BatchResult,
    PermissionEntry,
    ResourceObject,
    UserPermissions,
)
from authorization_sync.models import DesiredGrant
from authorization_sync.sync_service import (
    AuthorizationSyncService,
    _grants_in_scope,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from users.authorizations import (
    Activities,
    Activity,
    Authorizations,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)
from users.event_models import UserEventCollector

from .conftest import (
    api_relations_st,
    community_ids_st,
    desired_grants_st,
    flat_ids_st,
    permission_entries_st,
    registry_ids_st,
)

# The structured identity of a stored grant, plus the user it belongs to:
# (user_id, resource_type, resource_label, relation, center, study, community).
GrantKey = tuple[str, str, str, str, str | None, str | None, str | None]


@dataclass
class StatefulAuthorizationClient:
    """In-memory client that persists grants across batch calls.

    Models the real API closely enough to expose cross-study revocation:
    ``get_user_permissions`` returns every grant the user currently holds
    of the requested type, regardless of which study it belongs to. Each
    entry is enriched with a structured ``resource`` carrying the grant's
    label and parent fields, as the real API does, so the sync's diff and
    scope filter operate on the Structured Identity Tuple.

    Grants are keyed on the structured identity; the server-owned
    ``flat_id`` is assigned independently and never affects matching.
    """

    grants: set[GrantKey] = field(default_factory=set)
    batch_calls: list[list[BatchOperation]] = field(default_factory=list)
    # Structured keys for which the API returns no structured scope (catalog
    # gap): entries for these are returned with resource=None.
    scopeless_keys: set[GrantKey] = field(default_factory=set)
    # Structured key -> flat_id handle the API reports for that grant. When a
    # key is absent, the entry's resource carries flat_id=None.
    flat_ids: dict[GrantKey, str] = field(default_factory=dict)

    def _entry_for(self, key: GrantKey) -> PermissionEntry:
        (_uid, rtype, label, relation, center, study, community) = key
        if key in self.scopeless_keys:
            return PermissionEntry(resource=None, relation=relation)
        return PermissionEntry(
            resource=ResourceObject(
                type=rtype,
                label=label,
                flat_id=self.flat_ids.get(key),
                center=center,
                study=study,
                community=community,
            ),
            relation=relation,
        )

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        entries: list[PermissionEntry] = [
            self._entry_for(key)
            for key in self.grants
            if key[0] == user_id and key[1] == type_filter
        ]
        permissions = {type_filter: entries} if entries else {}
        return UserPermissions(user_id=user_id, permissions=permissions)

    def batch(self, operations: list[BatchOperation]) -> BatchResult:
        self.batch_calls.append(operations)
        for op in operations:
            key: GrantKey = (
                op.user_id,
                op.resource_type,
                op.resource_label,
                op.relation,
                op.center,
                op.study,
                op.community,
            )
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


def _grant_key(
    resource_type: str,
    resource_label: str,
    relation: str,
    *,
    center: str | None = None,
    study: str | None = None,
    community: str | None = None,
    user_id: str = "user@institution.edu",
) -> GrantKey:
    """Build a stored-grant key with explicit structured identity."""
    return (user_id, resource_type, resource_label, relation, center, study, community)


def _revoke_ops(client: StatefulAuthorizationClient) -> list[BatchOperation]:
    return [
        op
        for operations in client.batch_calls
        for op in operations
        if op.action == "revoke"
    ]


def _grant_ops(client: StatefulAuthorizationClient) -> list[BatchOperation]:
    return [
        op
        for operations in client.batch_calls
        for op in operations
        if op.action == "grant"
    ]


def _labels(client: StatefulAuthorizationClient) -> set[str]:
    return {label for (_, _, label, _, _, _, _) in client.grants}


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

        # Both studies' grants end up present in the API, distinguished by
        # their study parent (not by a flat resource id).
        studies = {study for (_, _, _, _, _, study, _) in client.grants}
        assert "study-1" in studies
        assert "study-2" in studies

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

        study_parents = {study for (_, _, _, _, _, study, _) in client.grants}
        assert {"study-1", "study-2", "study-3"} <= study_parents

    def test_stale_grant_is_revoked_when_no_longer_desired(self) -> None:
        """A grant present in the API but absent from the desired set is
        revoked.

        Confirms the aggregated diff still revokes genuinely stale
        grants rather than never revoking anything.
        """
        client = StatefulAuthorizationClient()
        # Pre-seed a grant for a study the user no longer has.
        stale = _grant_key(
            "data_pipeline",
            "ingest-form",
            "submitter",
            center="washington",
            study="old-study",
        )
        client.grants.add(stale)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        revoked = {
            (op.resource_type, op.resource_label, op.center, op.study)
            for op in _revoke_ops(client)
        }
        assert ("data_pipeline", "ingest-form", "washington", "old-study") in revoked

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
        center_grant = _grant_key(
            "data_pipeline",
            "ingest-form",
            "submitter",
            center="washington",
            study="study-1",
        )
        client.grants.add(center_grant)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        # General sync (center_group_id=None) with only a page grant.
        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=_general_page_auth("community-resources"),
        )

        assert center_grant not in {_key_from_op(op) for op in _revoke_ops(client)}
        # The center grant survives in API state.
        assert center_grant in client.grants

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
                _grant_key(
                    "data_pipeline",
                    f"ingest-{datatype}",
                    "submitter",
                    center="washington",
                    study="study-1",
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
        # Pre-seed a general (non-center) page grant. A page scoped to a study
        # but no center is the non-center scope: its center is None, so a
        # center sync (center="washington") must not revoke it.
        general_grant = _grant_key(
            "page",
            "page-community-resources",
            "viewer",
            study="study-1",
        )
        client.grants.add(general_grant)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        assert general_grant not in {_key_from_op(op) for op in _revoke_ops(client)}
        assert general_grant in client.grants

    def test_center_sync_does_not_revoke_other_center_grants(self) -> None:
        """A sync for center A leaves center B's grants untouched."""
        client = StatefulAuthorizationClient()
        # Pre-seed a grant belonging to a different center.
        other_center_grant = _grant_key(
            "data_pipeline",
            "ingest-form",
            "submitter",
            center="columbia",
            study="study-1",
        )
        client.grants.add(other_center_grant)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        assert other_center_grant not in {
            _key_from_op(op) for op in _revoke_ops(client)
        }
        assert other_center_grant in client.grants

    def test_grant_with_unknown_scope_is_never_revoked(self) -> None:
        """A current grant with no API-reported scope is never revoked.

        Models a catalog gap: the permissions endpoint returns the grant
        with resource=None. Scope cannot be confirmed, so the grant must
        be left alone even when it is absent from the desired set and
        would otherwise look in-scope.
        """
        client = StatefulAuthorizationClient()
        orphan = _grant_key(
            "data_pipeline",
            "ingest-form",
            "submitter",
            center="washington",
            study="orphan",
        )
        client.grants.add(orphan)
        # The API cannot report scope for this resource.
        client.scopeless_keys.add(orphan)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        assert orphan not in {_key_from_op(op) for op in _revoke_ops(client)}
        assert orphan in client.grants

    def test_center_sync_does_not_revoke_community_scoped_grant(self) -> None:
        """A community-scoped grant is never revoked by a center sync.

        The API can return a resource that carries a community parent.
        Such a resource belongs to the community scope, which this gear
        does not reconcile, so a center sync must leave it alone even
        though it is absent from the desired set.
        """
        client = StatefulAuthorizationClient()
        community_grant = _grant_key(
            "page",
            "page-shared",
            "viewer",
            community="nacc",
        )
        client.grants.add(community_grant)
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        service.sync_users(
            registry_id="user@institution.edu",
            authorizations=[_study_auth("study-1", "form")],
            center_group_id="washington",
        )

        assert community_grant not in {_key_from_op(op) for op in _revoke_ops(client)}
        assert community_grant in client.grants


@dataclass
class _MockResponse:
    """Minimal HTTP response for driving the real AuthorizationClient."""

    status_code: int
    body: bytes


@dataclass
class _RecordingTransport:
    """Transport that returns empty permissions and records batch bodies.

    GET /permissions returns an empty permission set (a fresh user), so
    the sync's desired grants become adds. POST /grants/batch records
    the request body and reports every operation as succeeded, as the
    real API would for a valid request.
    """

    batch_bodies: list[bytes] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> _MockResponse:
        if path == "/grants/batch":
            assert body is not None
            self.batch_bodies.append(body)
            payload = json.loads(body)
            count = len(payload["operations"])
            return _MockResponse(
                status_code=200,
                body=json.dumps(
                    {"total": count, "succeeded": count, "failed": 0, "errors": []}
                ).encode(),
            )
        # GET permissions: empty set for a fresh user.
        return _MockResponse(
            status_code=200,
            body=json.dumps(
                {"userId": "user@institution.edu", "permissions": {}}
            ).encode(),
        )


class TestGeneralPageGrantEndToEnd:
    """A general page grant syncs through the real client without rejection.

    Exercises the actual ``AuthorizationClient`` (whose
    ``_build_resource`` validates the structured identity before any
    HTTP call), not the in-memory stateful stub, so a parentless page
    grant — which the API requires a parent for — would surface as a
    swallowed client-side ``ValidationError`` and no batch body. The fix
    scopes a general page grant to the NACC community so the request is
    built and sent.
    """

    def test_general_page_grant_is_built_and_sent_community_scoped(self) -> None:
        """sync_user emits a community-scoped page grant, not a swallowed
        error.

        Regression guard: before the fix, ``translate`` produced a
        parentless ``page`` grant, ``_build_resource`` raised
        ``ValidationError`` while assembling the batch, ``sync_users``
        swallowed it, and no batch request was ever sent. The collector
        would hold an error and ``batch_bodies`` would be empty.
        """
        transport = _RecordingTransport()
        client = AuthorizationClient(transport=transport)  # type: ignore[arg-type]
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id="user@institution.edu",
            authorizations=_general_page_auth("community-resources"),
        )

        # A batch request was actually built and sent (not swallowed).
        assert transport.batch_bodies, "no batch request was sent"

        # The single operation is a community-scoped page grant.
        operations = json.loads(transport.batch_bodies[0])["operations"]
        assert len(operations) == 1
        operation = operations[0]
        assert operation["action"] == "grant"
        resource = operation["resource"]
        assert resource["type"] == "page"
        assert resource["label"] == "page-community-resources"
        assert resource["community"] == "nacc"
        # A parentless page (the old bug) would carry no scoping parent.
        assert "center" not in resource
        assert "study" not in resource
        # No client-side identity-build error was reported.
        assert collector.error_count() == 0


class TestDiffParityBetweenTranslatorAndApi:
    """The diff reconciles a real desired grant against the API's echo.

    ``sync_users`` diffs the desired grants ``translate`` produces
    against the current grants the API reports. The two are matched on
    the Structured Identity Tuple (type, relation, label, center, study,
    community), never on a replayed value. These tests build the
    current-side resource independently of the desired side — through
    the stateful client's own ``ResourceObject`` construction — so they
    prove the parity the migration relies on rather than assuming it:

    - When the API echoes the same structured identity the translator
      generates, the grant is recognized as already held: no add, no
      revoke.
    - When the API echoes a *different* ``study`` or ``label`` for what
      is logically the same grant, the mismatch is visible in the diff
      (the desired grant is added and the divergently-keyed current
      grant is revoked) rather than silently reconciled. This is the
      contract that would flag a real translator/API drift instead of
      hiding it.
    """

    def test_matching_api_echo_produces_no_change(self) -> None:
        """A current grant matching the translator's identity is left alone.

        The desired set comes from the real ``translate`` (not a stub).
        The current grant is seeded independently with the same
        structured identity the translator produces, so the diff must
        recognize it as already held and issue neither a grant nor a
        revoke.
        """
        client = StatefulAuthorizationClient()
        # Seed the current side independently, matching what translate()
        # produces for _study_auth("study-1", "form") under center
        # "washington": data_pipeline submitter + viewer, label
        # "ingest-form", study "study-1".
        for relation in ("submitter", "viewer"):
            client.grants.add(
                _grant_key(
                    "data_pipeline",
                    "ingest-form",
                    relation,
                    center="washington",
                    study="study-1",
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

        assert _grant_ops(client) == []
        assert _revoke_ops(client) == []

    def test_divergent_api_study_surfaces_in_diff(self) -> None:
        """A study mismatch is not silently reconciled.

        The API echoes the same logical grant but under a different
        ``study`` than the translator generates. Because the diff keys
        on the full structured identity, the two are distinct: the
        desired grant (study "study-1") is added and the divergently-
        keyed current grant (study "study-1-legacy") is revoked. This
        makes a real translator/API drift observable rather than hidden.
        """
        client = StatefulAuthorizationClient()
        # The API reports the grant under a study the translator never
        # produces for this authorization.
        for relation in ("submitter", "viewer"):
            client.grants.add(
                _grant_key(
                    "data_pipeline",
                    "ingest-form",
                    relation,
                    center="washington",
                    study="study-1-legacy",
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

        added = {_key_from_op(op) for op in _grant_ops(client)}
        revoked = {_key_from_op(op) for op in _revoke_ops(client)}

        # The desired grants (study-1) are added.
        assert added == {
            _grant_key(
                "data_pipeline",
                "ingest-form",
                relation,
                center="washington",
                study="study-1",
            )
            for relation in ("submitter", "viewer")
        }
        # The divergently-keyed current grants (study-1-legacy) are revoked,
        # because they are in scope (same center, no community) but absent
        # from the desired set.
        assert revoked == {
            _grant_key(
                "data_pipeline",
                "ingest-form",
                relation,
                center="washington",
                study="study-1-legacy",
            )
            for relation in ("submitter", "viewer")
        }


def _key_from_op(op: BatchOperation) -> GrantKey:
    """Recover the structured grant key from a batch operation."""
    return (
        op.user_id,
        op.resource_type,
        op.resource_label,
        op.relation,
        op.center,
        op.study,
        op.community,
    )


# --- Property tests (design Properties 2, 3, 5, 6) ---


@st.composite
def _desired_sets_st(draw: st.DrawFn) -> tuple[str, str | None, set[DesiredGrant]]:
    """Generate a user id, a center scope, and a desired grant set for it.

    Every grant in the set shares the drawn ``user_id`` (as
    ``translate`` produces for a single user). The grants otherwise vary
    in type, relation, label, and parent fields; each carries a parent-
    field combination valid for its type (guaranteed by
    ``desired_grants_st``), so the current-side ``ResourceObject`` built
    from it is always constructible. The ``center_group_id`` reconciled
    by the call is chosen independently — the round-trip must hold for
    any scope, since the current set is built from the same structured
    identities as the desired set.
    """
    user_id = draw(registry_ids_st)
    center_group_id = draw(st.one_of(st.none(), st.just("washington"), st.just("nyc")))
    base = draw(st.lists(desired_grants_st(), min_size=0, max_size=8))
    grants = {
        DesiredGrant(
            user_id=user_id,
            resource_type=g.resource_type,
            relation=g.relation,
            resource_label=g.resource_label,
            center=g.center,
            study=g.study,
            community=g.community,
        )
        for g in base
    }
    return user_id, center_group_id, grants


class TestDiffProperties:
    """Universal correctness properties for the structured-identity diff."""

    @settings(max_examples=100)
    @given(data=_desired_sets_st(), flats=st.lists(flat_ids_st, min_size=1, max_size=8))
    def test_diff_round_trips_independent_of_flat_id(
        self,
        data: tuple[str, str | None, set[DesiredGrant]],
        flats: list[str],
    ) -> None:
        """Property 2: the diff round-trips on structured identity.

        Build the current set from the desired set but assign arbitrary,
        differing ``flat_id`` handles to the current-side resources, then drive
        the real ``sync_users`` diff with a desired set equal (by structured
        identity) to the current set. Matching is by the Structured Identity
        Tuple, so nothing is added and nothing is revoked regardless of
        flat_id.

        # Feature: authorization-api-structured-resource-migration, Property 2:
        # The diff round-trips on structured identity, independent of flat_id.

        Validates: Requirements 4.1, 4.2, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.6
        """
        user_id, center_group_id, desired = data

        # Seed the client's current state from the desired grants, assigning
        # server-owned flat_ids that the client could never reproduce.
        client = StatefulAuthorizationClient()
        for index, grant in enumerate(desired):
            key = (
                grant.user_id,
                grant.resource_type,
                grant.resource_label,
                grant.relation,
                grant.center,
                grant.study,
                grant.community,
            )
            client.grants.add(key)
            client.flat_ids[key] = f"{flats[index % len(flats)]}-server-{index}"

        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )

        # Drive the real diff through sync_users. The desired set is injected
        # via translate so it is identical (by structured identity) to the
        # current set; the current set differs only in its server-owned
        # flat_ids.
        with patch(
            "authorization_sync.sync_service.translate",
            return_value=set(desired),
        ):
            # One authorization set so the (stubbed) translate is invoked once
            # and returns the full desired set; its contents are ignored.
            service.sync_users(
                registry_id=user_id,
                authorizations=[Authorizations()],
                center_group_id=center_group_id,
            )

        # grants_to_add and grants_to_revoke were both empty: no batch call was
        # issued (the service returns early when there are no changes), and the
        # persisted grant set is unchanged.
        assert _grant_ops(client) == []
        assert _revoke_ops(client) == []

    @settings(max_examples=100)
    @given(
        user_id=registry_ids_st,
        center_group_id=st.one_of(st.none(), st.just("washington")),
        relations=st.lists(api_relations_st, min_size=1, max_size=4),
    )
    def test_none_resource_entry_never_revoked(
        self,
        user_id: str,
        center_group_id: str | None,
        relations: list[str],
    ) -> None:
        """Property 3: a None-resource entry is never revoked.

        Entries whose ``resource`` is None (catalog gap) participate in
        neither add nor revoke, and ``_grants_in_scope`` completes without
        raising.

        # Feature: authorization-api-structured-resource-migration, Property 3:
        # An entry with no structured resource is never revoked.

        Validates: Requirements 4.3, 6.1, 6.2, 6.3, 6.4, 7.5
        """
        entries = [
            PermissionEntry(resource=None, relation=relation) for relation in relations
        ]
        permissions = UserPermissions(
            user_id=user_id, permissions={"data_pipeline": entries}
        )

        # The catalog-gap path must not raise and yields no in-scope grants.
        in_scope = _grants_in_scope(permissions, center_group_id)
        assert in_scope == set()

        # Full diff via sync_users: with an empty desired set, a revoke would
        # appear if any None-resource entry were treated as in scope.
        client = StatefulAuthorizationClient()
        service = AuthorizationSyncService(
            client=client,  # type: ignore[arg-type]
            collector=UserEventCollector(),
        )
        client.get_user_permissions = lambda **_: permissions  # type: ignore[method-assign]
        service.sync_users(
            registry_id=user_id,
            authorizations=[],
            center_group_id=center_group_id,
        )
        assert _revoke_ops(client) == []
        assert _grant_ops(client) == []

    @settings(max_examples=100)
    @given(
        user_id=registry_ids_st,
        center_group_id=st.one_of(st.none(), st.just("washington")),
        community=community_ids_st,
        entries=st.lists(
            permission_entries_st(resource_type="page"), min_size=1, max_size=5
        ),
    )
    def test_community_scoped_entries_never_revoked(
        self,
        user_id: str,
        center_group_id: str | None,
        community: str,
        entries: list[PermissionEntry],
    ) -> None:
        """Property 5: community-scoped entries are never revoked.

        Any entry whose structured resource carries a non-null ``community``
        is out of scope for a center/general sync, so it never appears among
        the in-scope (revoke-candidate) grants.

        # Feature: authorization-api-structured-resource-migration, Property 5:
        # Community-scoped entries are never revoked.

        Validates: Requirements 7.3
        """
        # Force a community parent on every entry's resource (page permits
        # community-alone), overriding whatever the strategy generated.
        community_entries = [
            PermissionEntry(
                resource=ResourceObject(
                    type="page",
                    label=entry.resource.label if entry.resource else "page-x",
                    community=community,
                ),
                relation=entry.relation,
            )
            for entry in entries
        ]
        permissions = UserPermissions(
            user_id=user_id, permissions={"page": community_entries}
        )

        # No community-scoped grant is a revoke candidate (empty desired set is
        # the worst case: every in-scope grant would otherwise be revoked).
        in_scope = _grants_in_scope(permissions, center_group_id)
        assert all(g.community is None for g in in_scope)
        assert in_scope == set()

    @settings(max_examples=100)
    @given(
        user_id=registry_ids_st,
        reconciled_center=st.one_of(st.none(), st.just("washington"), st.just("nyc")),
        entries=st.lists(
            permission_entries_st(resource_type="page"), min_size=1, max_size=6
        ),
    )
    def test_revoke_candidacy_is_center_keyed(
        self,
        user_id: str,
        reconciled_center: str | None,
        entries: list[PermissionEntry],
    ) -> None:
        """Property 6: revoke candidacy is center-keyed.

        For entries with a non-null resource and no community parent, an entry
        is a revoke candidate (i.e. in scope) iff its ``resource.center``
        equals — exactly, case-sensitively — the reconciled center group id.

        # Feature: authorization-api-structured-resource-migration, Property 6:
        # Revoke candidacy is center-keyed.

        Validates: Requirements 7.1, 7.2, 7.4
        """
        # Restrict to entries with a resource and no community parent.
        candidate_entries = [
            entry
            for entry in entries
            if entry.resource is not None and entry.resource.community is None
        ]
        permissions = UserPermissions(
            user_id=user_id, permissions={"page": candidate_entries}
        )

        in_scope = _grants_in_scope(permissions, reconciled_center)
        in_scope_labels = {(g.resource_label, g.relation, g.center) for g in in_scope}

        for entry in candidate_entries:
            assert entry.resource is not None
            key = (entry.resource.label, entry.relation, entry.resource.center)
            expected_in_scope = entry.resource.center == reconciled_center
            assert (key in in_scope_labels) == expected_in_scope
