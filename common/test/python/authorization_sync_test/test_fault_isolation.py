"""Property tests for fault isolation with event reporting.

Feature: authorization-user-sync, Property 8: Fault isolation with event reporting
"""

from dataclasses import dataclass, field

from authorization.exceptions import AuthorizationClientError, ServiceUnavailableError
from authorization.models import (
    AuthorizationModelMetadata,
    BatchError,
    BatchOperation,
    BatchResult,
    UserPermissions,
    UserProfile,
    UserProfileRequest,
)
from authorization_sync.sync_service import (
    _SYNC_RESOURCE_TYPES,
    AuthorizationSyncService,
)
from authorization_sync.translator import ACTIVITY_RELATION_MAP
from hypothesis import given, settings
from hypothesis import strategies as st
from users.authorizations import Authorizations
from users.event_models import (
    EventCategory,
    EventType,
    UserEventCollector,
)

from authorization_sync_test.conftest import (
    MockAuthorizationClient,
    authorization_client_errors_st,
    authorizations_st,
    center_group_ids_st,
    mapped_activities_st,
    registry_ids_st,
)


@dataclass
class PartialFailureClient:
    """Mock client that returns a partial failure on batch calls.

    Succeeds on get_user_permissions (returns empty permissions) but
    returns a configured BatchResult with failures on batch calls.
    """

    batch_result: BatchResult
    batch_calls: list[list[BatchOperation]] = field(default_factory=list)

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        """Return empty permissions so diff produces operations."""
        return UserPermissions(user_id=user_id, permissions={})

    def batch(self, operations: list[BatchOperation]) -> BatchResult:
        """Return the configured partial failure result."""
        self.batch_calls.append(operations)
        return self.batch_result

    def put_user_profile(
        self,
        profile_user_id: str,
        request: UserProfileRequest,
    ) -> UserProfile:
        """Mock put_user_profile that returns a default profile."""
        return UserProfile(
            user_id=profile_user_id,
            first_name="Test",
            last_name="User",
            email=None,
            auth_email="test@example.com",
            active=True,
        )

    def get_model(self) -> AuthorizationModelMetadata:
        """Mock get_model that returns minimal metadata."""
        return AuthorizationModelMetadata(version="1.0.0", types={})


@st.composite
def non_empty_authorizations_st(draw: st.DrawFn) -> Authorizations:
    """Generate Authorizations with at least one mapped activity."""
    activities_list = draw(st.lists(mapped_activities_st, min_size=1, max_size=5))
    auth = Authorizations()
    for activity in activities_list:
        auth.activities.add(resource=activity.resource, activity=activity)
    return auth


class TestFaultIsolationWithEventReporting:
    """Property 8: Fault isolation with event reporting.

    **Validates: Requirements 4.3, 7.1, 7.3, 7.4, 9.2**

    For any exception raised by the AuthorizationClient during sync
    (query, batch, or any other call), the sync SHALL catch the exception
    without re-raising, and SHALL report it via UserEventCollector as a
    UserProcessEvent with EventType ERROR, EventCategory
    AUTHORIZATION_SYNC, a UserContext containing the user's Registry_ID,
    and a message describing the failure.
    """

    @given(
        registry_id=registry_ids_st,
        error=authorization_client_errors_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=100, deadline=None)
    def test_client_error_does_not_propagate(
        self,
        registry_id: str,
        error: AuthorizationClientError,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """AuthorizationClientError exceptions are caught without re-
        raising."""
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        # Should not raise
        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

    @given(
        registry_id=registry_ids_st,
        error=authorization_client_errors_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=100, deadline=None)
    def test_client_error_reports_via_event_collector(
        self,
        registry_id: str,
        error: AuthorizationClientError,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """Errors are reported via UserEventCollector with correct event
        structure."""
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        # At least one error event should be collected
        events = collector.get_errors()
        assert len(events) >= 1

        # Verify the event structure
        event = events[0]
        assert event.event_type == EventType.ERROR.value
        assert event.category == EventCategory.AUTHORIZATION_SYNC.value
        assert event.user_context.registry_id == registry_id

    @given(
        registry_id=registry_ids_st,
        error=authorization_client_errors_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=100, deadline=None)
    def test_client_error_event_uses_authorization_sync_category(
        self,
        registry_id: str,
        error: AuthorizationClientError,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """Error events use EventCategory.AUTHORIZATION_SYNC."""
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        # All events should be in the AUTHORIZATION_SYNC category
        events_by_category = collector.get_events_by_category()
        assert EventCategory.AUTHORIZATION_SYNC in events_by_category
        assert len(events_by_category[EventCategory.AUTHORIZATION_SYNC]) >= 1

    @given(
        registry_id=registry_ids_st,
        error=authorization_client_errors_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=100, deadline=None)
    def test_client_error_event_message_describes_failure(
        self,
        registry_id: str,
        error: AuthorizationClientError,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """Error event message describes the failure."""
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        events = collector.get_errors()
        assert len(events) >= 1
        # Message should be non-empty and describe the failure
        event = events[0]
        assert event.message
        assert len(event.message) > 0

    @given(
        registry_id=registry_ids_st,
        authorizations=non_empty_authorizations_st(),
        center_group_id=center_group_ids_st,
        num_errors=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_partial_batch_failure_reports_individual_error_events(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str,
        num_errors: int,
    ) -> None:
        """Partial failures (BatchResult.failed > 0) are reported as individual
        error events.

        Uses a center scope (``center_group_id`` always set) so every
        mapped activity yields a buildable grant and the batch call
        always fires. In the general scope a parentless resource-type
        grant is skipped by the translator, so a non-empty authorization
        would not guarantee a batch call; that path is covered
        separately in the translator tests.
        """
        # Create batch errors for the partial failure
        batch_errors = [
            BatchError(
                index=i,
                error="conflict",
                message=f"Operation {i} failed",
            )
            for i in range(num_errors)
        ]
        batch_result = BatchResult(
            total=num_errors + 2,
            succeeded=2,
            failed=num_errors,
            errors=batch_errors,
        )

        # Use PartialFailureClient that returns empty permissions on
        # query (so diff produces operations) and the configured
        # partial failure on batch
        client = PartialFailureClient(batch_result=batch_result)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        # Since authorizations are non-empty and permissions are empty,
        # there will always be grants to add, triggering a batch call
        assert len(client.batch_calls) == 1

        # Each batch error should produce an individual error event
        events = collector.get_events_for_category(EventCategory.AUTHORIZATION_SYNC)
        assert len(events) == num_errors
        for event in events:
            assert event.event_type == EventType.ERROR.value
            assert event.category == EventCategory.AUTHORIZATION_SYNC.value
            assert event.user_context.registry_id == registry_id


class TestPerTypeQuerying:
    """One permissions request per resource type, each with a type filter.

    The permissions endpoint requires a ``type`` query parameter per
    request (ADR-015), and the sync must issue exactly one request per
    synced resource type. Because the diff keys on the Structured Identity
    Tuple returned in each response, the request-side contract that feeds
    that diff — one call per type, each carrying its type — is what these
    tests hold constant.

    Validates: Requirements 8.5, 8.6
    """

    @given(
        registry_id=registry_ids_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=50, deadline=None)
    def test_one_permissions_request_per_resource_type(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """sync_user issues exactly one permissions request per synced type.

        The set of types queried is exactly ``_SYNC_RESOURCE_TYPES`` and
        each is queried once, regardless of how many authorizations are
        translated into the desired set.

        Validates: Requirement 8.5
        """
        client = MockAuthorizationClient()
        service = AuthorizationSyncService(
            client=client, collector=UserEventCollector()
        )

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        queried_types = [
            call["type_filter"] for call in client.get_user_permissions_calls
        ]
        # Exactly one request per resource type (no type queried twice, none
        # skipped) — and the queried set is exactly the synced set.
        assert sorted(queried_types) == sorted(_SYNC_RESOURCE_TYPES)
        assert len(queried_types) == len(_SYNC_RESOURCE_TYPES)

    @given(
        registry_id=registry_ids_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=50, deadline=None)
    def test_every_permissions_request_carries_a_type_filter(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """Every permissions request includes a non-empty ``type`` filter.

        A request without a resource type is never issued (Req 8.6); every
        request the sync makes carries its resource type.

        Validates: Requirements 8.5, 8.6
        """
        client = MockAuthorizationClient()
        service = AuthorizationSyncService(
            client=client, collector=UserEventCollector()
        )

        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        assert client.get_user_permissions_calls  # at least one request made
        for call in client.get_user_permissions_calls:
            assert call["type_filter"]  # non-empty type identifier
            assert call["type_filter"] in _SYNC_RESOURCE_TYPES
            assert call["user_id"] == registry_id


class TestPreservedBehaviorHeldConstant:
    """Constants and 503 handling unchanged by the structured migration.

    Validates: Requirements 9.1, 9.2, 9.3
    """

    def test_sync_resource_types_derived_from_activity_relation_map(self) -> None:
        """``_SYNC_RESOURCE_TYPES`` is exactly the types in the relation map.

        The set of synced resource types is derived from
        ``ACTIVITY_RELATION_MAP`` values, with none added or removed by the
        migration.

        Validates: Requirement 9.1
        """
        expected = {
            resource_type
            for pairs in ACTIVITY_RELATION_MAP.values()
            for resource_type, _ in pairs
        }
        assert frozenset(expected) == _SYNC_RESOURCE_TYPES

    def test_activity_relation_map_association_is_constant(self) -> None:
        """``ACTIVITY_RELATION_MAP`` keys, values, and associations are held.

        Pins the exact key set, value set, and each key-to-value
        association so the migration cannot silently change what is synced.

        Validates: Requirement 9.2
        """
        expected: dict[tuple[str, str], list[tuple[str, str]]] = {
            ("submit-audit", "datatype"): [
                ("data_pipeline", "submitter"),
                ("data_pipeline", "viewer"),
            ],
            ("view", "datatype"): [("data_pipeline", "viewer")],
            ("view", "dashboard"): [("dashboard", "viewer")],
            ("view", "page"): [("page", "viewer")],
        }
        # Key set unchanged.
        assert set(ACTIVITY_RELATION_MAP.keys()) == set(expected.keys())
        # Each key-to-value association unchanged (order included).
        for key, pairs in expected.items():
            assert ACTIVITY_RELATION_MAP[key] == pairs

    @given(
        registry_id=registry_ids_st,
        authorizations=authorizations_st(),
        center_group_id=st.one_of(st.none(), center_group_ids_st),
    )
    @settings(max_examples=50, deadline=None)
    def test_service_unavailable_after_retries_is_caught_not_propagated(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str | None,
    ) -> None:
        """A 503 that survives client retries is reported, not raised.

        The retry-on-503 behavior lives in the client; when it is exhausted
        the client surfaces ``ServiceUnavailableError``. The sync must catch
        it and report via the event collector without propagating, leaving
        that retry behavior unchanged.

        Validates: Requirement 9.3
        """
        error = ServiceUnavailableError("Service unavailable after retries")
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        # Must not raise even though the client exhausts its 503 retries.
        service.sync_user(
            registry_id=registry_id,
            authorizations=authorizations,
            center_group_id=center_group_id,
        )

        errors = collector.get_errors()
        assert len(errors) >= 1
        assert errors[0].user_context.registry_id == registry_id
