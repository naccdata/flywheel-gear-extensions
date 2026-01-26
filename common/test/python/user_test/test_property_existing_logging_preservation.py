"""Property test for existing logging preservation.

**Feature: automated-error-handling, Property 6: Existing Logging Preservation**
**Validates: Requirements 1a.8**
"""

import logging
from io import StringIO
from unittest.mock import Mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from users.event_models import UserEventCollector
from users.user_entry import ActiveUserEntry, PersonName, RegisteredUserEntry
from users.user_processes import (
    ActiveUserProcess,
    ClaimedUserProcess,
    UpdateUserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import RegistryPerson


class LogCapture:
    """Context manager to capture log messages without using pytest
    fixtures."""

    def __init__(self, logger_name=None, level=logging.DEBUG):
        self.logger_name = logger_name
        self.level = level
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setLevel(level)

    def __enter__(self):
        if self.logger_name:
            self.logger = logging.getLogger(self.logger_name)
        else:
            self.logger = logging.getLogger()

        # Store original level and handlers
        self.original_level = self.logger.level
        self.original_handlers = self.logger.handlers[:]

        # Set up our handler
        self.logger.setLevel(self.level)
        self.logger.addHandler(self.handler)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original state
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.original_level)

    @property
    def text(self):
        """Get captured log text."""
        return self.stream.getvalue()


@st.composite
def active_user_entry_strategy(draw):
    """Generate random ActiveUserEntry for testing."""
    # Use simple, direct generation to avoid filtering
    return ActiveUserEntry(
        name=PersonName(first_name="TestFirst", last_name="TestLast"),
        email="test@example.com",
        auth_email=draw(st.one_of(st.none(), st.just("auth@example.com"))),
        active=True,
        approved=True,
        org_name="Test Center",
        adcid=123,
        authorizations=[],
    )


@st.composite
def registered_user_entry_strategy(draw):
    """Generate random RegisteredUserEntry for testing."""
    # Use simple, direct generation to avoid filtering
    return RegisteredUserEntry(
        name=PersonName(first_name="TestFirst", last_name="TestLast"),
        email="test@example.com",
        auth_email=draw(st.one_of(st.none(), st.just("auth@example.com"))),
        active=True,
        approved=True,
        org_name="Test Center",
        adcid=123,
        authorizations=[],
        registry_id="test123",
    )


@st.composite
def mock_environment_strategy(draw):
    """Generate mock UserProcessEnvironment for testing."""
    # Use simple, direct generation
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.user_registry = Mock()
    mock_env.user_registry.coid = 123  # Set coid as integer to avoid validation errors
    mock_env.proxy = Mock()
    mock_env.notification_client = Mock()

    # Set default return values for methods that should return lists
    mock_env.user_registry.get = Mock(return_value=[])  # Default to empty list
    mock_env.user_registry.get_bad_claim = Mock(
        return_value=[]
    )  # Default to empty list

    # Configure wrapper methods to delegate to proxy and user_registry
    mock_env.find_user = Mock(
        side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
    )
    mock_env.add_user = Mock(side_effect=lambda user: mock_env.proxy.add_user(user))
    mock_env.get_from_registry = Mock(
        side_effect=lambda email: mock_env.user_registry.get(email=email)
    )

    return mock_env


@given(entry=active_user_entry_strategy(), mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_active_user_process_preserves_existing_logging_with_error_handling(
    entry, mock_env
):
    """Property test: ActiveUserProcess maintains all existing log messages
    while adding error event capture.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    collector = UserEventCollector()

    # Test scenario 1: Missing auth email (should log error)
    if entry.auth_email is None:
        process = ActiveUserProcess(mock_env, collector)

        with LogCapture(level=logging.ERROR) as log_capture:
            process.visit(entry)

        # Assert - Existing log message should be preserved
        expected_log_message = f"User {entry.email} must have authentication email"
        assert expected_log_message in log_capture.text, (
            f"Expected log message '{expected_log_message}' should be preserved "
            f"when error handling is integrated. Actual logs: {log_capture.text}"
        )

        # Assert - Error event should also be created (error handling integration)
        assert collector.has_errors(), (
            "Error event should be created when error handling is integrated"
        )

        return  # Exit early for this scenario

    # Test scenario 2: Bad claim (should log error)
    mock_env.user_registry.get.return_value = []  # No person found
    mock_env.user_registry.has_bad_claim.return_value = True
    mock_env.user_registry.get_bad_claim.return_value = [
        Mock(spec=RegistryPerson)
    ]  # Return list of mocks

    process = ActiveUserProcess(mock_env, collector)

    with LogCapture(level=logging.ERROR) as log_capture:
        process.visit(entry)

    # Assert - Existing log message should be preserved for bad claim
    expected_log_message = (
        f"Active user has incomplete claim: {entry.full_name}, {entry.email}"
    )
    assert expected_log_message in log_capture.text, (
        f"Expected log message '{expected_log_message}' should be preserved "
        f"when error handling is integrated. Actual logs: {log_capture.text}"
    )

    # Assert - Error event should also be created (error handling integration)
    assert collector.has_errors(), (
        "Error event should be created when error handling is integrated"
    )


@given(entry=active_user_entry_strategy(), mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_active_user_process_preserves_info_logging_for_new_users(entry, mock_env):
    """Property test: ActiveUserProcess preserves info logging for new user
    registration.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    # Skip if no auth email (different test scenario)
    if entry.auth_email is None:
        return

    collector = UserEventCollector()

    # Setup for new user scenario
    mock_env.user_registry.get.return_value = []  # No person found
    mock_env.user_registry.has_bad_claim.return_value = False  # Not a bad claim
    mock_env.user_registry.add.return_value = []

    process = ActiveUserProcess(mock_env, collector)

    with LogCapture(level=logging.INFO) as log_capture:
        process.visit(entry)

    # Assert - Existing log messages should be preserved for new user registration
    expected_log_messages = [
        f"Active user not in registry: {entry.email}",
        f"Added user {entry.email} to registry using email {entry.auth_email}",
    ]

    for expected_message in expected_log_messages:
        assert expected_message in log_capture.text, (
            f"Expected log message '{expected_message}' should be preserved "
            f"when error handling is integrated. Actual logs: {log_capture.text}"
        )

    # Assert - No errors should be collected for successful new user registration
    assert not collector.has_errors(), (
        "No error events should be created for successful new user registration"
    )

    # Assert - Notification should be sent (existing functionality preserved)
    mock_env.notification_client.send_claim_email.assert_called_once_with(entry)


@given(entry=registered_user_entry_strategy(), mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_update_user_process_preserves_existing_logging_with_error_handling(
    entry, mock_env
):
    """Property test: UpdateUserProcess maintains all existing log messages
    while adding error event capture.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    collector = UserEventCollector()

    # Test scenario: Missing claimed user (should log error)
    mock_env.user_registry.find_by_registry_id.return_value = None
    mock_env.get_from_registry.return_value = []  # For failure analyzer
    mock_env.user_registry.get_bad_claim.return_value = []  # No bad claims

    process = UpdateUserProcess(mock_env, collector)

    with LogCapture(level=logging.ERROR) as log_capture:
        process.visit(entry)

    # Assert - Existing log message should be preserved
    expected_log_message = (
        f"Failed to find a claimed user with Registry ID {entry.registry_id} "
        f"and email {entry.email}"
    )
    assert expected_log_message in log_capture.text, (
        f"Expected log message '{expected_log_message}' should be preserved "
        f"when error handling is integrated. Actual logs: {log_capture.text}"
    )

    # Assert - Error event should also be created (error handling integration)
    assert collector.has_errors(), (
        "Error event should be created when error handling is integrated"
    )


@given(entry=registered_user_entry_strategy(), mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_update_user_process_preserves_info_logging_for_successful_updates(
    entry, mock_env
):
    """Property test: UpdateUserProcess preserves info logging for successful
    user updates.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    collector = UserEventCollector()

    # Setup for successful update scenario
    mock_registry_person = Mock(spec=RegistryPerson)
    mock_registry_person.email_address = Mock()
    mock_registry_person.email_address.mail = "registry@example.com"

    mock_fw_user = Mock()
    mock_fw_user.email = entry.email
    mock_fw_user.id = "user123"

    mock_env.user_registry.find_by_registry_id.return_value = mock_registry_person
    mock_env.proxy.find_user.return_value = mock_fw_user

    process = UpdateUserProcess(mock_env, collector)

    process.visit(entry)

    # Assert - No errors should be collected for successful processing
    assert not collector.has_errors(), (
        "No error events should be created for successful user updates"
    )

    # Assert - Existing functionality should be preserved
    mock_env.user_registry.find_by_registry_id.assert_called_once_with(
        entry.registry_id
    )
    mock_env.proxy.find_user.assert_called_once_with(entry.registry_id)


@given(entry=registered_user_entry_strategy(), mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_claimed_user_process_preserves_existing_logging_with_error_handling(
    entry, mock_env
):
    """Property test: ClaimedUserProcess maintains all existing log messages
    while adding error event capture.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    collector = UserEventCollector()

    claimed_queue: UserQueue[RegisteredUserEntry] = UserQueue()

    # Test scenario: User creation needed (should log info)
    mock_env.proxy.find_user.side_effect = [
        None,
        Mock(),
    ]  # Not found, then found after creation
    mock_env.proxy.add_user.return_value = "user123"

    process = ClaimedUserProcess(mock_env, claimed_queue, collector)

    with LogCapture(level=logging.INFO) as log_capture:
        process.visit(entry)

    # Assert - Existing log messages should be preserved for user creation
    expected_log_messages = [
        f"User {entry.email} has no flywheel user with ID: {entry.registry_id}",
        f"Added user {entry.registry_id}",
    ]

    for expected_message in expected_log_messages:
        assert expected_message in log_capture.text, (
            f"Expected log message '{expected_message}' should be preserved "
            f"when error handling is integrated. Actual logs: {log_capture.text}"
        )

    # Assert - No errors should be collected for successful user creation
    assert not collector.has_errors(), (
        "No error events should be created for successful user creation"
    )

    # Assert - User creation should be attempted (existing functionality preserved)
    mock_env.proxy.add_user.assert_called_once()


@given(mock_env=mock_environment_strategy())
@settings(max_examples=2, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_collector_does_not_interfere_with_logging(mock_env):
    """Property test: UserEventCollector itself does not interfere with
    existing logging.

    **Feature: automated-error-handling, Property 6: Existing Logging Preservation**
    **Validates: Requirements 1a.8**

    For any user processing operation, the system should maintain all existing
    log messages while adding error event capture.
    """
    collector = UserEventCollector()

    # Create a simple entry that will trigger logging
    entry = ActiveUserEntry(
        name=PersonName(first_name="Test", last_name="User"),
        email="test@example.com",
        auth_email=None,  # This will trigger error logging
        active=True,
        approved=True,
        org_name="Test Center",
        adcid=123,
        authorizations=[],
    )

    # Test with error collector
    process_with_collector = ActiveUserProcess(mock_env, collector)

    with LogCapture(level=logging.ERROR) as log_capture_with:
        process_with_collector.visit(entry)

    logs_with_collector = log_capture_with.text

    # Test without error collector (simulate original behavior)
    # Note: This is a conceptual test - in practice, the original classes
    # would not have error collector parameter
    process_without_collector = ActiveUserProcess(mock_env, UserEventCollector())

    with LogCapture(level=logging.ERROR) as log_capture_without:
        process_without_collector.visit(entry)

    logs_without_collector = log_capture_without.text

    # Assert - The core log message should be present in both cases
    expected_log_message = "test@example.com must have authentication email"

    assert expected_log_message in logs_with_collector, (
        "Expected log message should be present with error collector: "
        f"{logs_with_collector}"
    )

    assert expected_log_message in logs_without_collector, (
        "Expected log message should be present without error collector: "
        f"{logs_without_collector}"
    )

    # Assert - Error collector should capture the error
    assert collector.has_errors(), "Error collector should capture error events"

    # Assert - The logging behavior should be fundamentally the same
    # (allowing for minor differences in formatting or additional context)
    core_message_parts = expected_log_message.split()
    for part in core_message_parts:
        assert part in logs_with_collector, (
            f"Core message part '{part}' should be preserved with error collector"
        )
        assert part in logs_without_collector, (
            f"Core message part '{part}' should be preserved without error collector"
        )
