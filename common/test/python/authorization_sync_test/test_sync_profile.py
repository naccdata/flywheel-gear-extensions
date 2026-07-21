"""Unit tests for AuthorizationSyncService.sync_profile.

Tests cover:
- Skipping sync when auth_email is None (with warning log)
- Reporting errors via event collector on AuthorizationClientError
- Completing successfully when API returns 200

Requirements: 3.4, 3.5, 6.3
"""

import logging

import pytest
from authorization.exceptions import ServiceUnavailableError
from authorization_sync.sync_service import AuthorizationSyncService
from users.event_models import (
    EventCategory,
    EventType,
    UserEventCollector,
)
from users.user_entry import PersonName, UserEntry

from authorization_sync_test.conftest import MockAuthorizationClient


class TestSyncProfileSkipsWhenAuthEmailIsNone:
    """Test that sync_profile skips when auth_email is None.

    Validates: Requirement 3.4
    """

    def test_no_put_user_profile_call_when_auth_email_is_none(self) -> None:
        """sync_profile does not call put_user_profile when auth_email is
        None."""
        client = MockAuthorizationClient()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="Jane", last_name="Doe"),
            email="jane@example.com",
            auth_email=None,
            active=True,
            approved=True,
        )

        service.sync_profile(
            registry_id="Registry000001@naccdata.org",
            user_entry=entry,
        )

        # put_user_profile should not have been called
        assert len(client.put_user_profile_calls) == 0
        # No error events should be reported
        assert not collector.has_errors()

    def test_logs_warning_when_auth_email_is_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """sync_profile logs a warning when auth_email is None."""
        client = MockAuthorizationClient()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="Jane", last_name="Doe"),
            email="jane@example.com",
            auth_email=None,
            active=True,
            approved=True,
        )

        with caplog.at_level(logging.WARNING):
            service.sync_profile(
                registry_id="Registry000001@naccdata.org",
                user_entry=entry,
            )

        # Should log a warning mentioning the user email and skipping
        assert any(
            "jane@example.com" in record.message and "auth_email" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        )


class TestSyncProfileReportsErrorOnClientError:
    """Test that sync_profile reports errors via event collector.

    Validates: Requirement 3.5
    """

    def test_reports_error_via_event_collector(self) -> None:
        """sync_profile catches AuthorizationClientError and reports via event
        collector."""
        error = ServiceUnavailableError("Service unavailable after retries")
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="John", last_name="Smith"),
            email="john@example.com",
            auth_email="john@university.edu",
            active=True,
            approved=True,
        )

        # Should not raise
        service.sync_profile(
            registry_id="Registry000002@naccdata.org",
            user_entry=entry,
        )

        # Should have reported an error event
        assert collector.has_errors()
        errors = collector.get_errors()
        assert len(errors) == 1

        event = errors[0]
        assert event.event_type == EventType.ERROR.value
        assert event.category == EventCategory.AUTHORIZATION_SYNC.value
        assert event.user_context.registry_id == "Registry000002@naccdata.org"
        assert "profile_sync" in event.message

    def test_does_not_propagate_exception(self) -> None:
        """sync_profile does not raise AuthorizationClientError."""
        error = ServiceUnavailableError("Service unavailable after retries")
        client = MockAuthorizationClient(error_to_raise=error)
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="John", last_name="Smith"),
            email="john@example.com",
            auth_email="john@university.edu",
            active=True,
            approved=True,
        )

        # Should complete without raising
        service.sync_profile(
            registry_id="Registry000002@naccdata.org",
            user_entry=entry,
        )


class TestSyncProfileCompletesSuccessfully:
    """Test that sync_profile completes without error on success.

    Validates: Requirement 6.3
    """

    def test_completes_without_error_when_api_returns_200(self) -> None:
        """sync_profile completes successfully when client returns normally."""
        client = MockAuthorizationClient()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="Alice", last_name="Johnson"),
            email="alice@example.com",
            auth_email="alice@university.edu",
            active=True,
            approved=True,
        )

        # Should complete without raising
        service.sync_profile(
            registry_id="Registry000003@naccdata.org",
            user_entry=entry,
        )

        # No errors should be reported
        assert not collector.has_errors()
        assert not collector.has_events()

    def test_constructs_request_from_user_entry_fields(self) -> None:
        """sync_profile builds UserProfileRequest with correct field
        mapping."""
        client = MockAuthorizationClient()
        collector = UserEventCollector()
        service = AuthorizationSyncService(client=client, collector=collector)

        entry = UserEntry(
            name=PersonName(first_name="Alice", last_name="Johnson"),
            email="alice@example.com",
            auth_email="alice@university.edu",
            active=False,
            approved=True,
        )

        service.sync_profile(
            registry_id="Registry000003@naccdata.org",
            user_entry=entry,
        )

        assert len(client.put_user_profile_calls) == 1
        call = client.put_user_profile_calls[0]
        assert call["profile_user_id"] == "Registry000003@naccdata.org"

        request = call["request"]
        assert request.first_name == "Alice"
        assert request.last_name == "Johnson"
        assert request.email == "alice@example.com"
        assert request.auth_email == "alice@university.edu"
        assert request.active is False
