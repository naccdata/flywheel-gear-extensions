"""Tests for FailureAnalyzer methods (TDD)."""

from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import FlywheelError
from users.user_entry import PersonName, RegisteredUserEntry
from users.user_registry import RegistryPerson


class TestFailureAnalyzer:
    """Tests for FailureAnalyzer class methods."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock()
        mock_env.proxy = Mock()
        mock_env.user_registry = Mock()

        # Add wrapper methods that delegate to proxy and user_registry
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        return mock_env

    @pytest.fixture
    def sample_registered_entry(self):
        """Create a sample RegisteredUserEntry for testing."""
        return RegisteredUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
            registry_id="reg123",
        )

    @pytest.fixture
    def sample_flywheel_error(self):
        """Create a sample FlywheelError for testing."""
        return FlywheelError("Test Flywheel error")

    def test_failure_analyzer_initialization(self, mock_environment):
        """Test FailureAnalyzer initialization with environment."""
        from users.failure_analyzer import FailureAnalyzer

        analyzer = FailureAnalyzer(mock_environment)
        assert analyzer.env == mock_environment

    def test_analyze_flywheel_user_creation_failure_duplicate_user(
        self, mock_environment, sample_registered_entry, sample_flywheel_error
    ):
        """Test analyze_flywheel_user_creation_failure when user already exists
        (duplicate)."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return existing user (duplicate scenario)
        mock_existing_user = Mock()
        mock_existing_user.id = "existing_user_id"
        mock_environment.proxy.find_user.return_value = mock_existing_user

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, sample_flywheel_error
        )

        # Verify the error event was created correctly
        assert error_event is not None
        assert error_event.category == EventCategory.DUPLICATE_USER_RECORDS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert error_event.message == "User already exists in Flywheel"
        assert error_event.action_needed == "deactivate_duplicate_and_clear_cache"

        # Verify proxy.find_user was called with correct registry_id
        mock_environment.proxy.find_user.assert_called_once_with("reg123")

    def test_analyze_flywheel_user_creation_failure_permission_error(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_flywheel_user_creation_failure with permission
        error."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return no existing user
        mock_environment.proxy.find_user.return_value = None

        # Create permission-related error
        permission_error = FlywheelError("Permission denied: unauthorized access")

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, permission_error
        )

        # Verify the error event was created correctly
        assert error_event is not None
        assert error_event.category == EventCategory.INSUFFICIENT_PERMISSIONS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert (
            error_event.message == "Insufficient permissions to create user in Flywheel"
        )

    def test_analyze_flywheel_user_creation_failure_unauthorized_error(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_flywheel_user_creation_failure with unauthorized
        error."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return no existing user
        mock_environment.proxy.find_user.return_value = None

        # Create unauthorized-related error
        unauthorized_error = FlywheelError("Unauthorized: invalid credentials")

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, unauthorized_error
        )

        # Verify the error event was created correctly
        assert error_event is not None
        assert error_event.category == EventCategory.INSUFFICIENT_PERMISSIONS.value

    def test_analyze_flywheel_user_creation_failure_generic_error(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_flywheel_user_creation_failure with generic error."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return no existing user
        mock_environment.proxy.find_user.return_value = None

        # Create generic error
        generic_error = FlywheelError("Network timeout occurred")

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, generic_error
        )

        # Verify the error event was created correctly
        assert error_event is not None
        assert error_event.category == EventCategory.FLYWHEEL_ERROR.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert error_event.message == "Flywheel user creation failed after 3 attempts"

        assert error_event.action_needed == "check_flywheel_logs_and_service_status"

    def test_analyze_flywheel_user_creation_failure_with_different_user_data(
        self, mock_environment
    ):
        """Test analyze_flywheel_user_creation_failure with different user
        data."""
        from users.failure_analyzer import FailureAnalyzer

        # Create different user entry
        different_entry = RegisteredUserEntry(
            name=PersonName(first_name="Jane", last_name="Smith"),
            email="jane.smith@example.com",
            auth_email="jane.auth@example.com",
            active=True,
            approved=True,
            org_name="Different Center",
            adcid=456,
            authorizations=[],
            registry_id="reg456",
        )

        # Setup mock to return no existing user
        mock_environment.proxy.find_user.return_value = None

        generic_error = FlywheelError("Some error")

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            different_entry, generic_error
        )

        # Verify the error event contains correct user data
        assert error_event is not None
        assert error_event.user_context.email == "jane.smith@example.com"
        assert error_event.user_context.name
        assert error_event.user_context.name == "Jane Smith"

    def test_analyze_missing_claimed_user_no_person_found(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_missing_claimed_user when no person found in
        registry."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return empty list (no person found)
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []  # No bad claims

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_missing_claimed_user(sample_registered_entry)

        # Verify the error event was created correctly
        assert error_event is not None
        assert error_event.category == EventCategory.MISSING_REGISTRY_DATA.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "not found in registry" in error_event.message

        assert (
            error_event.action_needed == "verify_registry_record_exists_or_was_deleted"
        )

        # Verify get_from_registry was called with correct email
        mock_environment.get_from_registry.assert_called_once_with(
            email="john.auth@example.com"
        )

    def test_analyze_missing_claimed_user_fallback_to_main_email(
        self, mock_environment
    ):
        """Test analyze_missing_claimed_user falls back to main email when
        auth_email is None."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Create entry without auth_email
        entry_no_auth = RegisteredUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email=None,  # No auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
            registry_id="reg123",
        )

        # Setup mock to return empty list
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []  # No bad claims

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_missing_claimed_user(entry_no_auth)

        # Verify get_from_registry was called with main email as fallback
        mock_environment.get_from_registry.assert_called_once_with(
            email="john.doe@example.com"
        )

        assert error_event is not None
        assert error_event.category == EventCategory.MISSING_REGISTRY_DATA.value

    def test_analyze_missing_claimed_user_person_exists_but_not_claimed(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_missing_claimed_user when person exists but not.

        properly claimed - should raise RuntimeError.
        """
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return person list (user exists - this is a data inconsistency)
        mock_person1 = Mock(spec=RegistryPerson)
        mock_person1.registry_id.return_value = "different_id_1"
        mock_person2 = Mock(spec=RegistryPerson)
        mock_person2.registry_id.return_value = "different_id_2"
        mock_environment.user_registry.get.return_value = [mock_person1, mock_person2]

        analyzer = FailureAnalyzer(mock_environment)

        # This should raise RuntimeError because user found by email but not by
        #  registry_id
        with pytest.raises(RuntimeError) as exc_info:
            analyzer.analyze_missing_claimed_user(sample_registered_entry)

        # Verify the error message indicates data inconsistency
        assert "Registry data inconsistency" in str(exc_info.value)
        assert "john.auth@example.com" in str(exc_info.value)
        assert "reg123" in str(exc_info.value)

    def test_analyze_missing_claimed_user_single_person_record(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_missing_claimed_user with single person record.

        Should raise RuntimeError.
        """
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return single person (data inconsistency)
        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = "different_id"
        mock_environment.user_registry.get.return_value = [mock_person]

        analyzer = FailureAnalyzer(mock_environment)

        # This should raise RuntimeError because user found by email but
        # not by registry_id
        with pytest.raises(RuntimeError) as exc_info:
            analyzer.analyze_missing_claimed_user(sample_registered_entry)

        # Verify the error message indicates data inconsistency
        assert "Registry data inconsistency" in str(exc_info.value)

    def test_analyze_missing_claimed_user_with_different_user_data(
        self, mock_environment
    ):
        """Test analyze_missing_claimed_user with different user data."""
        from users.failure_analyzer import FailureAnalyzer

        # Create different user entry
        different_entry = RegisteredUserEntry(
            name=PersonName(first_name="Alice", last_name="Johnson"),
            email="alice.johnson@example.com",
            auth_email="alice.auth@example.com",
            active=True,
            approved=True,
            org_name="Another Center",
            adcid=789,
            authorizations=[],
            registry_id="reg789",
        )

        # Setup mock to return empty list
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []  # No bad claims

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_missing_claimed_user(different_entry)

        # Verify the error event contains correct user data
        assert error_event is not None
        assert error_event.user_context.email == "alice.johnson@example.com"
        assert error_event.user_context.name
        assert error_event.user_context.name == "Alice Johnson"

        # Verify correct email was used for lookup
        mock_environment.get_from_registry.assert_called_once_with(
            email="alice.auth@example.com"
        )

    def test_analyze_flywheel_user_creation_failure_proxy_exception(
        self, mock_environment, sample_registered_entry, sample_flywheel_error
    ):
        """Test analyze_flywheel_user_creation_failure when proxy.find_user
        raises exception."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to raise exception when finding user
        mock_environment.proxy.find_user.side_effect = FlywheelError("API call failed")

        analyzer = FailureAnalyzer(mock_environment)
        error_event = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, sample_flywheel_error
        )

        # Should still return a generic error event when proxy call fails
        assert error_event is not None
        assert error_event.category == EventCategory.FLYWHEEL_ERROR.value
        assert error_event.message == "Flywheel user creation failed after 3 attempts"

    def test_analyze_missing_claimed_user_registry_exception(
        self, mock_environment, sample_registered_entry
    ):
        """Test analyze_missing_claimed_user when get_from_registry raises
        exception."""
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to raise exception when getting user
        mock_environment.user_registry.get.side_effect = Exception("Registry error")

        analyzer = FailureAnalyzer(mock_environment)

        # The exception should propagate up
        with pytest.raises(Exception) as exc_info:
            analyzer.analyze_missing_claimed_user(sample_registered_entry)

        assert "Registry error" in str(exc_info.value)

    def test_failure_analyzer_methods_return_optional_error_event(
        self, mock_environment, sample_registered_entry, sample_flywheel_error
    ):
        """Test that FailureAnalyzer methods return
        Optional[UserProcessEvent]."""
        from users.failure_analyzer import FailureAnalyzer

        # Setup mocks
        mock_environment.proxy.find_user.return_value = None
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []  # No bad claims

        analyzer = FailureAnalyzer(mock_environment)

        # Test that methods can return UserProcessEvent
        flywheel_result = analyzer.analyze_flywheel_user_creation_failure(
            sample_registered_entry, sample_flywheel_error
        )
        missing_user_result = analyzer.analyze_missing_claimed_user(
            sample_registered_entry
        )

        # Both should return UserProcessEvent objects (not None in these cases)
        assert flywheel_result is not None
        assert missing_user_result is not None

        # Verify they are the correct type
        from users.event_models import UserProcessEvent

        assert isinstance(flywheel_result, UserProcessEvent)
        assert isinstance(missing_user_result, UserProcessEvent)

    def test_analyze_flywheel_user_creation_failure_case_insensitive_permission_check(
        self, mock_environment, sample_registered_entry
    ):
        """Test that permission error detection is case-insensitive."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        # Setup mock to return no existing user
        mock_environment.proxy.find_user.return_value = None

        # Test various case combinations
        permission_errors = [
            FlywheelError("PERMISSION denied"),
            FlywheelError("Permission DENIED"),
            FlywheelError("permission denied"),
            FlywheelError("UNAUTHORIZED access"),
            FlywheelError("Unauthorized ACCESS"),
            FlywheelError("unauthorized access"),
        ]

        analyzer = FailureAnalyzer(mock_environment)

        for error in permission_errors:
            error_event = analyzer.analyze_flywheel_user_creation_failure(
                sample_registered_entry, error
            )

            assert error_event is not None
            assert error_event.category == EventCategory.INSUFFICIENT_PERMISSIONS.value
            assert (
                error_event.message
                == "Insufficient permissions to create user in Flywheel"
            )

    def test_analyze_methods_preserve_user_context_data(
        self, mock_environment, sample_flywheel_error
    ):
        """Test that analyzer methods preserve all user context data."""
        from users.failure_analyzer import FailureAnalyzer

        # Create entry with full user context data
        full_entry = RegisteredUserEntry(
            name=PersonName(first_name="Full", last_name="Context"),
            email="full.context@example.com",
            auth_email="full.auth@example.com",
            active=True,
            approved=True,
            org_name="Full Context Center",
            adcid=999,
            authorizations=[],
            registry_id="reg999",
        )

        # Setup mocks
        mock_environment.proxy.find_user.return_value = None
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []

        analyzer = FailureAnalyzer(mock_environment)

        # Test both methods preserve user context
        flywheel_result = analyzer.analyze_flywheel_user_creation_failure(
            full_entry, sample_flywheel_error
        )
        missing_user_result = analyzer.analyze_missing_claimed_user(full_entry)

        # Verify user context is preserved in both results
        for result in [flywheel_result, missing_user_result]:
            assert result is not None
            assert result.user_context.email == "full.context@example.com"
            assert result.user_context.name
            assert result.user_context.name == "Full Context"
            assert result.user_context.auth_email == "full.auth@example.com"
