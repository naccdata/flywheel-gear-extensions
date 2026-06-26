"""Tests for FailureAnalyzer methods (TDD)."""

from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import FlywheelError
from users.authorizations import Authorizations
from users.user_entry import CenterUserEntry, PersonName
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
        """Create a sample CenterUserEntry with registry_person for testing."""
        # Create a mock RegistryPerson
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg123"

        entry = CenterUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        entry.register(mock_registry_person)
        return entry

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
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg456"

        different_entry = CenterUserEntry(
            name=PersonName(first_name="Jane", last_name="Smith"),
            email="jane.smith@example.com",
            auth_email="jane.auth@example.com",
            active=True,
            approved=True,
            org_name="Different Center",
            adcid=456,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        different_entry.register(mock_registry_person)

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
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg123"

        entry_no_auth = CenterUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email=None,  # No auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        entry_no_auth.register(mock_registry_person)

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
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg789"

        different_entry = CenterUserEntry(
            name=PersonName(first_name="Alice", last_name="Johnson"),
            email="alice.johnson@example.com",
            auth_email="alice.auth@example.com",
            active=True,
            approved=True,
            org_name="Another Center",
            adcid=789,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        different_entry.register(mock_registry_person)

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
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg999"

        full_entry = CenterUserEntry(
            name=PersonName(first_name="Full", last_name="Context"),
            email="full.context@example.com",
            auth_email="full.auth@example.com",
            active=True,
            approved=True,
            org_name="Full Context Center",
            adcid=999,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        full_entry.register(mock_registry_person)

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


class TestFailureAnalyzerWithIdPConfig:
    """Tests for FailureAnalyzer wrong-IdP detection (tasks 5.1-5.4)."""

    @pytest.fixture
    def domain_config(self):
        """Create a DomainRelationshipConfig with parent-child mappings."""
        from users.domain_config import DomainRelationshipConfig

        return DomainRelationshipConfig(
            parent_child=[
                {"child": "med.umich.edu", "parent": "umich.edu"},
                {"child": "health.ucdavis.edu", "parent": "ucdavis.edu"},
            ],
        )

    @pytest.fixture
    def idp_config(self):
        """Create an IdPDomainConfig with institutional and fallback
        domains."""
        from users.domain_config import IdPDomainConfig

        return IdPDomainConfig(
            institutional_idp=[
                {"domain": "umich.edu", "idp_name": "University of Michigan"},
                {"domain": "ucdavis.edu", "idp_name": "UC Davis"},
            ],
            fallback_domains=["advocatehealth.org", "ccf.org"],
            fallback_idp="ORCID",
        )

    @pytest.fixture
    def mock_environment(self, domain_config, idp_config):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock()
        mock_env.proxy = Mock()
        mock_env.user_registry = Mock()
        mock_env.domain_config = domain_config
        mock_env.idp_config = idp_config
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )
        return mock_env

    @pytest.fixture
    def make_entry(self):
        """Factory for creating CenterUserEntry objects."""

        def _make(
            email: str = "user@umich.edu",
            auth_email: str | None = "user@umich.edu",
            first_name: str = "John",
            last_name: str = "Doe",
        ):
            mock_rp = Mock(spec=RegistryPerson)
            mock_rp.registry_id.return_value = "reg-test"
            entry = CenterUserEntry(
                name=PersonName(first_name=first_name, last_name=last_name),
                email=email,
                auth_email=auth_email,
                active=True,
                approved=True,
                org_name="Test Center",
                adcid=100,
                authorizations=Authorizations(),
                study_authorizations=[],
            )
            entry.register(mock_rp)
            return entry

        return _make

    @pytest.fixture
    def make_bad_claim_person(self):
        """Factory for creating mock RegistryPerson with org identities."""
        from coreapi_client.models.org_identity import OrgIdentity

        def _make(org_name: str = "ORCID"):
            person = Mock(spec=RegistryPerson)
            org_id = OrgIdentity(o=org_name)
            person.org_identities = Mock(
                side_effect=lambda predicate=None: (
                    [org_id] if predicate is None or predicate(org_id) else []
                )
            )
            return person

        return _make

    # --- Initialization tests ---

    def test_init_with_idp_and_domain_config(
        self, mock_environment, idp_config, domain_config
    ):
        """FailureAnalyzer pulls idp_config and domain_config from
        environment."""
        from users.failure_analyzer import FailureAnalyzer

        analyzer = FailureAnalyzer(mock_environment)
        assert analyzer._idp_config is idp_config  # noqa: SLF001
        assert analyzer._domain_config is domain_config  # noqa: SLF001

    def test_init_without_configs_backward_compatible(self, mock_environment):
        """FailureAnalyzer without config on environment defaults to None."""
        from users.failure_analyzer import FailureAnalyzer

        mock_environment.idp_config = None
        mock_environment.domain_config = None
        analyzer = FailureAnalyzer(mock_environment)
        assert analyzer._idp_config is None  # noqa: SLF001
        assert analyzer._domain_config is None  # noqa: SLF001

    # --- _detect_wrong_idp tests ---

    def test_detect_wrong_idp_institutional_domain_via_fallback(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When domain maps to institutional IdP and claim was via fallback
        IdP, return WRONG_IDP_SELECTION event."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is not None
        assert result.category == EventCategory.WRONG_IDP_SELECTION.value
        assert "umich.edu" in result.message
        assert "ORCID" in result.message
        assert "University of Michigan" in result.message

    def test_detect_wrong_idp_subdomain_resolves_to_parent(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """Subdomain med.umich.edu resolves to umich.edu IdP mapping."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(
            email="user@med.umich.edu",
            auth_email="user@med.umich.edu",
        )
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is not None
        assert result.category == EventCategory.WRONG_IDP_SELECTION.value
        assert "University of Michigan" in result.message

    def test_detect_wrong_idp_fallback_domain_returns_none(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When domain is in fallback_domains, return None (correct IdP)."""
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(
            email="user@advocatehealth.org",
            auth_email="user@advocatehealth.org",
        )
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is None

    def test_detect_wrong_idp_unmapped_domain_returns_none(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When domain is not mapped to any IdP, return None."""
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(
            email="user@unknown.edu",
            auth_email="user@unknown.edu",
        )
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is None

    def test_detect_wrong_idp_claimed_via_correct_idp_returns_none(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When claim was via the correct institutional IdP, return None."""
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        # Person claimed via institutional IdP, not ORCID
        bad_person = make_bad_claim_person(org_name="University of Michigan")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is None

    def test_detect_wrong_idp_no_email_returns_none(
        self,
        mock_environment,
        make_bad_claim_person,
    ):
        """When entry has no usable email, return None."""
        from users.failure_analyzer import FailureAnalyzer

        # Entry with email that has no @ sign
        mock_rp = Mock(spec=RegistryPerson)
        mock_rp.registry_id.return_value = "reg-test"
        entry = CenterUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="no-at-sign",
            auth_email=None,
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=100,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        entry.register(mock_rp)

        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is None

    # --- detect_incomplete_claim integration tests ---

    def test_detect_incomplete_claim_with_configs_delegates_to_wrong_idp(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When configs are available and wrong IdP detected,
        detect_incomplete_claim returns WRONG_IDP_SELECTION."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer.detect_incomplete_claim(entry, [bad_person])

        assert result is not None
        assert result.category == EventCategory.WRONG_IDP_SELECTION.value

    def test_detect_incomplete_claim_with_configs_fallback_domain(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """When configs are available but domain is fallback, falls through to
        existing ORCID detection."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(
            email="user@advocatehealth.org",
            auth_email="user@advocatehealth.org",
        )
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer.detect_incomplete_claim(entry, [bad_person])

        assert result is not None
        # Falls through to existing ORCID detection
        assert result.category == EventCategory.BAD_ORCID_CLAIMS.value

    def test_detect_incomplete_claim_without_configs_backward_compatible(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """Without configs, detect_incomplete_claim uses existing ORCID
        detection."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        bad_person = make_bad_claim_person(org_name="ORCID")

        # No configs provided
        mock_environment.idp_config = None
        mock_environment.domain_config = None
        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer.detect_incomplete_claim(entry, [bad_person])

        assert result is not None
        # Without configs, falls through to existing BAD_ORCID_CLAIMS
        assert result.category == EventCategory.BAD_ORCID_CLAIMS.value

    def test_detect_incomplete_claim_without_configs_non_orcid(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """Without configs and non-ORCID claim, returns INCOMPLETE_CLAIM."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        bad_person = make_bad_claim_person(org_name="Some Other IdP")

        mock_environment.idp_config = None
        mock_environment.domain_config = None
        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer.detect_incomplete_claim(entry, [bad_person])

        assert result is not None
        assert result.category == EventCategory.INCOMPLETE_CLAIM.value

    def test_detect_wrong_idp_action_needed_contains_expected_idp(
        self,
        mock_environment,
        make_entry,
        make_bad_claim_person,
    ):
        """The action_needed field references the expected institutional
        IdP."""
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(
            email="user@ucdavis.edu",
            auth_email="user@ucdavis.edu",
        )
        bad_person = make_bad_claim_person(org_name="ORCID")

        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer._detect_wrong_idp(entry, [bad_person])  # noqa: SLF001

        assert result is not None
        assert result.action_needed is not None
        assert "uc_davis" in result.action_needed

    def test_detect_incomplete_claim_only_idp_config_no_domain_config(
        self,
        mock_environment,
        idp_config,
        make_entry,
        make_bad_claim_person,
    ):
        """When only idp_config is provided (no domain_config), falls through
        to existing detection."""
        from users.event_models import EventCategory
        from users.failure_analyzer import FailureAnalyzer

        entry = make_entry(email="user@umich.edu", auth_email="user@umich.edu")
        bad_person = make_bad_claim_person(org_name="ORCID")

        # Only idp_config, no domain_config
        mock_environment.domain_config = None
        analyzer = FailureAnalyzer(mock_environment)
        result = analyzer.detect_incomplete_claim(entry, [bad_person])

        assert result is not None
        # Without both configs, skips wrong-IdP check
        assert result.category == EventCategory.BAD_ORCID_CLAIMS.value
