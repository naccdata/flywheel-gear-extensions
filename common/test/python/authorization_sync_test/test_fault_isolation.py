"""Property tests for fault isolation with event reporting.

Feature: authorization-user-sync, Property 8: Fault isolation with event reporting
"""

from dataclasses import dataclass, field

from authorization.exceptions import AuthorizationClientError
from authorization.models import (
    BatchError,
    BatchOperation,
    BatchResult,
    UserPermissions,
    UserProfile,
    UserProfileRequest,
)
from authorization_sync.sync_service import AuthorizationSyncService
from authorization_sync_test.conftest import (
    MockAuthorizationClient,
    authorization_client_errors_st,
    authorizations_st,
    center_group_ids_st,
    mapped_activities_st,
    registry_ids_st,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from users.authorizations import Authorizations
from users.event_models import (
    EventCategory,
    EventType,
    UserEventCollector,
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
        type_filter: str | None = None,
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
        center_group_id=st.one_of(st.none(), center_group_ids_st),
        num_errors=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_partial_batch_failure_reports_individual_error_events(
        self,
        registry_id: str,
        authorizations: Authorizations,
        center_group_id: str | None,
        num_errors: int,
    ) -> None:
        """Partial failures (BatchResult.failed > 0) are reported as individual
        error events."""
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
