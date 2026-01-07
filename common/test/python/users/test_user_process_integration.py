"""Integration tests for modified UserProcess classes (TDD).

Tests that existing functionality is preserved with error handling
integrated, that error events are created for failure cases, and that
all existing log messages still occur.
"""

import logging
from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import FlywheelError
from users.error_models import ErrorCategory, ErrorCollector
from users.failure_analyzer import FailureAnalyzer
from users.user_entry import ActiveUserEntry, PersonName, RegisteredUserEntry
from users.user_processes import (
    ActiveUserProcess,
    ClaimedUserProcess,
    UpdateUserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import RegistryPerson


class TestActiveUserProcessIntegration:
    """Integration tests for ActiveUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.notification_client = Mock()
        return mock_env

    @pytest.fixture
    def error_collector(self):
        """Create an ErrorCollector for testing."""
        return ErrorCollector()

    @pytest.fixture
    def sample_active_entry(self):
        """Create a sample ActiveUserEntry for testing."""
        return ActiveUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

    def test_active_user_process_preserves_existing_functionality(
        self, mock_environment, error_collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess preserves existing functionality when no
        errors occur."""
        # Setup mocks for successful processing
        mock_person = Mock(spec=RegistryPerson)
        mock_person.creation_date = "2024-01-01"
        mock_person.is_claimed.return_value = True
        mock_person.registry_id.return_value = "reg123"

        mock_environment.user_registry.get.return_value = [mock_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        # Create process with error handling
        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.INFO):
            process.visit(sample_active_entry)

        # Verify existing functionality is preserved
        mock_environment.user_registry.get.assert_called_once_with(
            email="john.auth@example.com"
        )

        # Verify no errors were collected for successful processing
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0

        # Verify entry was processed correctly (would be added to claimed queue)
        # This is verified by the fact that no error logs occurred

    def test_active_user_process_creates_error_for_missing_auth_email(
        self, mock_environment, error_collector, caplog
    ):
        """Test that ActiveUserProcess creates error event for missing auth
        email."""
        # Create entry without auth email
        entry_no_auth = ActiveUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email=None,  # Missing auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(entry_no_auth)

        # Verify existing log message still occurs
        assert "User john.doe@example.com must have authentication email" in caplog.text

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.MISSING_DIRECTORY_PERMISSIONS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "no authentication email" in error_event.error_details["message"]

    def test_active_user_process_creates_error_for_bad_claim(
        self, mock_environment, error_collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess creates error event for bad ORCID
        claims."""
        # Setup mocks for bad claim scenario
        mock_environment.user_registry.get.return_value = []  # No person found
        mock_environment.user_registry.has_bad_claim.return_value = True

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_active_entry)

        # Verify existing log message still occurs
        assert (
            "Active user has incomplete claim: John Doe, john.doe@example.com"
            in caplog.text
        )

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.BAD_ORCID_CLAIMS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "incomplete ORCID claim" in error_event.error_details["message"]

    def test_active_user_process_creates_error_for_missing_creation_date(
        self, mock_environment, error_collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess creates error event for missing creation
        date."""
        # Setup mocks for missing creation date scenario
        mock_person = Mock(spec=RegistryPerson)
        mock_person.creation_date = None  # No creation date

        mock_environment.user_registry.get.return_value = [mock_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.WARNING):
            process.visit(sample_active_entry)

        # Verify existing log message still occurs
        assert (
            "person record for john.doe@example.com has no creation date" in caplog.text
        )

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.UNCLAIMED_RECORDS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "no creation date" in error_event.error_details["message"]

    def test_active_user_process_creates_error_for_missing_registry_id(
        self, mock_environment, error_collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess creates error event for missing registry
        ID."""
        # Setup mocks for missing registry ID scenario
        mock_person = Mock(spec=RegistryPerson)
        mock_person.creation_date = "2024-01-01"
        mock_person.is_claimed.return_value = True
        mock_person.registry_id.return_value = None  # No registry ID

        mock_environment.user_registry.get.return_value = [mock_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_active_entry)

        # Verify existing log message still occurs
        assert "User john.doe@example.com has no registry ID" in caplog.text

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.UNCLAIMED_RECORDS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "no registry ID" in error_event.error_details["message"]

    def test_active_user_process_handles_new_user_registration(
        self, mock_environment, error_collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess handles new user registration without
        errors."""
        # Setup mocks for new user scenario
        mock_environment.user_registry.get.return_value = []  # No person found
        mock_environment.user_registry.has_bad_claim.return_value = False
        mock_environment.user_registry.add.return_value = []

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process the entry
        with caplog.at_level(logging.INFO):
            process.visit(sample_active_entry)

        # Verify existing log messages still occur
        assert "Active user not in registry: john.doe@example.com" in caplog.text
        assert (
            "Added user john.doe@example.com to registry using email "
            "john.auth@example.com"
        ) in caplog.text

        # Verify no errors were collected for successful new user registration
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0

        # Verify notification was sent
        mock_environment.notification_client.send_claim_email.assert_called_once_with(
            sample_active_entry
        )


class TestClaimedUserProcessIntegration:
    """Integration tests for ClaimedUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.proxy = Mock()
        mock_env.notification_client = Mock()
        return mock_env

    @pytest.fixture
    def error_collector(self):
        """Create an ErrorCollector for testing."""
        return ErrorCollector()

    @pytest.fixture
    def failure_analyzer(self, mock_environment):
        """Create a FailureAnalyzer for testing."""
        return FailureAnalyzer(mock_environment)

    @pytest.fixture
    def sample_registered_entry(self):
        """Create a sample RegisteredUserEntry for testing."""
        return RegisteredUserEntry(
            name=PersonName(first_name="Jane", last_name="Smith"),
            email="jane.smith@example.com",
            auth_email="jane.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=456,
            authorizations=[],
            registry_id="reg456",
        )

    def test_claimed_user_process_preserves_existing_functionality(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
    ):
        """Test that ClaimedUserProcess preserves existing functionality when
        no errors occur."""
        # Setup mocks for successful processing
        mock_user = Mock()
        mock_user.id = "user123"
        mock_environment.proxy.find_user.return_value = mock_user
        mock_environment.proxy.add_user.return_value = "user123"

        claimed_queue = UserQueue()
        process = ClaimedUserProcess(
            mock_environment, claimed_queue, error_collector, failure_analyzer
        )

        # Process the entry
        process.visit(sample_registered_entry)

        # Verify existing functionality is preserved
        mock_environment.proxy.find_user.assert_called_with("reg456")

        # Verify no errors were collected for successful processing
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0

    def test_claimed_user_process_creates_user_when_not_found(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that ClaimedUserProcess creates user when not found in
        Flywheel."""
        # Setup mocks for user creation scenario
        mock_environment.proxy.find_user.side_effect = [
            None,
            Mock(),
        ]  # Not found, then found after creation
        mock_environment.proxy.add_user.return_value = "user123"

        claimed_queue = UserQueue()
        process = ClaimedUserProcess(
            mock_environment, claimed_queue, error_collector, failure_analyzer
        )

        # Process the entry
        with caplog.at_level(logging.INFO):
            process.visit(sample_registered_entry)

        # Verify existing log messages still occur
        assert (
            "User jane.smith@example.com has no flywheel user with ID: reg456"
            in caplog.text
        )
        assert "Added user reg456" in caplog.text

        # Verify user creation was attempted
        mock_environment.proxy.add_user.assert_called_once()

        # Verify no errors were collected for successful user creation
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0

    def test_claimed_user_process_uses_failure_analyzer_for_creation_failure(
        self, mock_environment, error_collector, sample_registered_entry, caplog
    ):
        """Test that ClaimedUserProcess uses FailureAnalyzer for Flywheel user
        creation failures."""
        # Setup mocks for failure scenario
        mock_environment.proxy.find_user.return_value = None
        flywheel_error = FlywheelError("Permission denied")
        mock_environment.proxy.add_user.side_effect = flywheel_error

        claimed_queue = UserQueue()

        # Create a real failure analyzer for this test
        failure_analyzer = FailureAnalyzer(mock_environment)

        process = ClaimedUserProcess(
            mock_environment, claimed_queue, error_collector, failure_analyzer
        )

        # Process the entry (this will fail 3 times)
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)
            process.visit(sample_registered_entry)  # Second attempt
            process.visit(sample_registered_entry)  # Third attempt

        # Verify existing log message still occurs after 3 failures
        assert (
            "Unable to add user jane.smith@example.com with ID reg456: "
            "Permission denied"
        ) in caplog.text

        # Verify failure analysis was performed and error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.INSUFFICIENT_PERMISSIONS.value
        assert error_event.user_context.email == "jane.smith@example.com"
        assert "Insufficient permissions" in error_event.error_details["message"]

    def test_claimed_user_process_handles_user_not_found_after_creation(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that ClaimedUserProcess handles case where user is not found
        after creation."""
        # Setup mocks for user not found after creation
        mock_environment.proxy.find_user.return_value = None  # Always not found
        mock_environment.proxy.add_user.return_value = "user123"

        claimed_queue = UserQueue()
        process = ClaimedUserProcess(
            mock_environment, claimed_queue, error_collector, failure_analyzer
        )

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert (
            "Failed to find user jane.smith@example.com with ID reg456" in caplog.text
        )

        # Verify no errors were collected (this is existing behavior)
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0


class TestUpdateUserProcessIntegration:
    """Integration tests for UpdateUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.proxy = Mock()
        return mock_env

    @pytest.fixture
    def error_collector(self):
        """Create an ErrorCollector for testing."""
        return ErrorCollector()

    @pytest.fixture
    def failure_analyzer(self, mock_environment):
        """Create a FailureAnalyzer for testing."""
        return FailureAnalyzer(mock_environment)

    @pytest.fixture
    def sample_registered_entry(self):
        """Create a sample RegisteredUserEntry for testing."""
        return RegisteredUserEntry(
            name=PersonName(first_name="Bob", last_name="Wilson"),
            email="bob.wilson@example.com",
            auth_email="bob.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=789,
            authorizations=[],
            registry_id="reg789",
        )

    def test_update_user_process_preserves_existing_functionality(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
    ):
        """Test that UpdateUserProcess preserves existing functionality when no
        errors occur."""
        # Setup mocks for successful processing
        mock_registry_person = Mock()
        mock_registry_person.email_address = Mock()
        mock_registry_person.email_address.mail = "bob.registry@example.com"

        mock_fw_user = Mock()
        mock_fw_user.email = "bob.wilson@example.com"

        mock_environment.user_registry.find_by_registry_id.return_value = (
            mock_registry_person
        )
        mock_environment.proxy.find_user.return_value = mock_fw_user

        process = UpdateUserProcess(mock_environment, error_collector, failure_analyzer)

        # Process the entry
        process.visit(sample_registered_entry)

        # Verify existing functionality is preserved
        mock_environment.user_registry.find_by_registry_id.assert_called_once_with(
            "reg789"
        )
        mock_environment.proxy.find_user.assert_called_once_with("reg789")

        # Verify no errors were collected for successful processing
        assert not error_collector.has_errors()
        assert error_collector.error_count() == 0

    def test_update_user_process_uses_failure_analyzer_for_missing_claimed_user(
        self, mock_environment, error_collector, sample_registered_entry, caplog
    ):
        """Test that UpdateUserProcess uses FailureAnalyzer for missing claimed
        users."""
        # Setup mocks for missing claimed user scenario
        mock_environment.user_registry.find_by_registry_id.return_value = None
        mock_environment.user_registry.get.return_value = []  # For failure analyzer

        # Create a real failure analyzer for this test
        failure_analyzer = FailureAnalyzer(mock_environment)

        process = UpdateUserProcess(mock_environment, error_collector, failure_analyzer)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert (
            "Failed to find a claimed user with Registry ID reg789 and email "
            "bob.wilson@example.com"
        ) in caplog.text

        # Verify failure analysis was performed and error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.UNCLAIMED_RECORDS.value
        assert error_event.user_context.email == "bob.wilson@example.com"
        assert "not found in registry" in error_event.error_details["message"]

    def test_update_user_process_creates_error_for_missing_flywheel_user(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that UpdateUserProcess creates error event for missing Flywheel
        user."""
        # Setup mocks for missing Flywheel user scenario
        mock_registry_person = Mock()
        mock_registry_person.email_address = Mock()
        mock_registry_person.email_address.mail = "bob.registry@example.com"

        mock_environment.user_registry.find_by_registry_id.return_value = (
            mock_registry_person
        )
        mock_environment.proxy.find_user.return_value = (
            None  # User not found in Flywheel
        )

        process = UpdateUserProcess(mock_environment, error_collector, failure_analyzer)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert "Failed to add user bob.wilson@example.com with ID reg789" in caplog.text

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.FLYWHEEL_ERROR.value
        assert error_event.user_context.email == "bob.wilson@example.com"
        assert (
            "should exist in Flywheel but was not found"
            in error_event.error_details["message"]
        )

    def test_update_user_process_creates_error_for_missing_registry_email(
        self,
        mock_environment,
        error_collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that UpdateUserProcess creates error event for missing registry
        email address."""
        # Setup mocks for missing registry email scenario
        mock_registry_person = Mock()
        mock_registry_person.email_address = None  # No email address

        mock_fw_user = Mock()
        mock_fw_user.email = "bob.wilson@example.com"

        mock_environment.user_registry.find_by_registry_id.return_value = (
            mock_registry_person
        )
        mock_environment.proxy.find_user.return_value = mock_fw_user

        process = UpdateUserProcess(mock_environment, error_collector, failure_analyzer)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert "Registry record does not have email address: reg789" in caplog.text

        # Verify error event was created
        assert error_collector.has_errors()
        assert error_collector.error_count() == 1

        errors = error_collector.get_errors()
        error_event = errors[0]
        assert error_event.category == ErrorCategory.UNVERIFIED_EMAIL.value
        assert error_event.user_context.email == "bob.wilson@example.com"
        assert "has no email address" in error_event.error_details["message"]


class TestUserProcessIntegrationEndToEnd:
    """End-to-end integration tests for UserProcess classes working
    together."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.proxy = Mock()
        mock_env.notification_client = Mock()
        return mock_env

    @pytest.fixture
    def error_collector(self):
        """Create an ErrorCollector for testing."""
        return ErrorCollector()

    def test_multiple_error_types_collected_in_single_run(
        self, mock_environment, error_collector, caplog
    ):
        """Test that multiple different error types are collected in a single
        run."""
        # Create entries that will trigger different error types
        entry_no_auth = ActiveUserEntry(
            name=PersonName(first_name="No", last_name="Auth"),
            email="no.auth@example.com",
            auth_email=None,  # Missing auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        entry_bad_claim = ActiveUserEntry(
            name=PersonName(first_name="Bad", last_name="Claim"),
            email="bad.claim@example.com",
            auth_email="bad.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        # Setup mocks for different scenarios
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.has_bad_claim.return_value = True

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process both entries
        with caplog.at_level(logging.ERROR):
            process.visit(entry_no_auth)
            process.visit(entry_bad_claim)

        # Verify both error types were collected
        assert error_collector.has_errors()
        assert error_collector.error_count() == 2

        errors = error_collector.get_errors()
        error_categories = [error.category for error in errors]

        assert ErrorCategory.MISSING_DIRECTORY_PERMISSIONS.value in error_categories
        assert ErrorCategory.BAD_ORCID_CLAIMS.value in error_categories

        # Verify both log messages occurred
        assert "no.auth@example.com must have authentication email" in caplog.text
        assert "Bad Claim, bad.claim@example.com" in caplog.text

    def test_error_collector_maintains_state_across_processes(
        self, mock_environment, error_collector
    ):
        """Test that ErrorCollector maintains state across different process
        instances."""
        # Create first process and add an error
        entry1 = ActiveUserEntry(
            name=PersonName(first_name="First", last_name="User"),
            email="first@example.com",
            auth_email=None,
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        process1 = ActiveUserProcess(mock_environment, error_collector)
        process1.visit(entry1)

        # Verify first error was collected
        assert error_collector.error_count() == 1

        # Create second process with same error collector
        entry2 = RegisteredUserEntry(
            name=PersonName(first_name="Second", last_name="User"),
            email="second@example.com",
            auth_email="second.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=456,
            authorizations=[],
            registry_id="reg456",
        )

        # Setup mocks for missing claimed user
        mock_environment.user_registry.find_by_registry_id.return_value = None
        mock_environment.user_registry.get.return_value = []

        failure_analyzer = FailureAnalyzer(mock_environment)
        process2 = UpdateUserProcess(
            mock_environment, error_collector, failure_analyzer
        )
        process2.visit(entry2)

        # Verify both errors are now collected
        assert error_collector.error_count() == 2

        errors = error_collector.get_errors()
        emails = [error.user_context.email for error in errors]
        assert "first@example.com" in emails
        assert "second@example.com" in emails

    def test_existing_logging_behavior_preserved_with_error_handling(
        self, mock_environment, error_collector, caplog
    ):
        """Test that all existing logging behavior is preserved when error
        handling is integrated."""
        # Test various scenarios to ensure all log messages still occur

        # Scenario 1: Missing auth email
        entry_no_auth = ActiveUserEntry(
            name=PersonName(first_name="No", last_name="Auth"),
            email="no.auth@example.com",
            auth_email=None,
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        # Scenario 2: Bad claim
        entry_bad_claim = ActiveUserEntry(
            name=PersonName(first_name="Bad", last_name="Claim"),
            email="bad.claim@example.com",
            auth_email="bad.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        # Scenario 3: New user registration
        entry_new_user = ActiveUserEntry(
            name=PersonName(first_name="New", last_name="User"),
            email="new.user@example.com",
            auth_email="new.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        # Setup mocks for different scenarios
        def mock_get_side_effect(email):
            if email == "bad.auth@example.com":
                return []  # No person found for bad claim
            elif email == "new.auth@example.com":
                return []  # No person found for new user
            return []

        def mock_has_bad_claim_side_effect(full_name):
            return full_name == "Bad Claim"

        mock_environment.user_registry.get.side_effect = mock_get_side_effect
        mock_environment.user_registry.has_bad_claim.side_effect = (
            mock_has_bad_claim_side_effect
        )
        mock_environment.user_registry.add.return_value = []

        process = ActiveUserProcess(mock_environment, error_collector)

        # Process all entries and capture logs
        with caplog.at_level(logging.INFO):
            process.visit(entry_no_auth)
            process.visit(entry_bad_claim)
            process.visit(entry_new_user)

        # Verify all expected log messages occurred
        expected_log_messages = [
            "no.auth@example.com must have authentication email",
            "Active user has incomplete claim: Bad Claim, bad.claim@example.com",
            "Active user not in registry: new.user@example.com",
            (
                "Added user new.user@example.com to registry using email "
                "new.auth@example.com"
            ),
        ]

        for expected_message in expected_log_messages:
            assert expected_message in caplog.text

        # Verify errors were collected for failure cases
        assert error_collector.error_count() == 2  # Missing auth email and bad claim

        # Verify notification was sent for new user
        mock_environment.notification_client.send_claim_email.assert_called_once()
