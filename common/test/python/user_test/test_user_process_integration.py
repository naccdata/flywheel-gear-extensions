"""Integration tests for modified UserProcess classes (TDD).

Tests that existing functionality is preserved with error handling
integrated, that error events are created for failure cases, and that
all existing log messages still occur.
"""

import logging
from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import FlywheelError
from users.authorizations import Authorizations
from users.event_models import EventCategory, UserEventCollector
from users.failure_analyzer import FailureAnalyzer
from users.user_entry import ActiveUserEntry, CenterUserEntry, PersonName
from users.user_processes import (
    ActiveUserProcess,
    ClaimedUserProcess,
    UpdateCenterUserProcess,
    UpdateUserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import DomainCandidate, RegistryPerson


class TestActiveUserProcessIntegration:
    """Integration tests for ActiveUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.notification_client = Mock()

        # Add wrapper methods
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
            if hasattr(mock_env, "proxy")
            else None
        )
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        # Domain-aware and name-based fallback defaults (return no candidates)
        mock_env.user_registry.get_by_parent_domain = Mock(return_value=[])
        mock_env.user_registry.get_by_name = Mock(return_value=[])

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create an UserEventCollector for testing."""
        return UserEventCollector()

    @pytest.fixture
    def sample_active_entry(self):
        """Create a sample CenterUserEntry for testing."""
        return CenterUserEntry(
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

    def test_active_user_process_preserves_existing_functionality(
        self, mock_environment, collector, sample_active_entry, caplog
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
        process = ActiveUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.INFO):
            process.visit(sample_active_entry)

        # Verify existing functionality is preserved
        mock_environment.user_registry.get.assert_called_once_with(
            email="john.auth@example.com"
        )

        # Verify no errors were collected for successful processing
        assert not collector.has_errors()
        assert collector.error_count() == 0

        # Verify entry was processed correctly (would be added to claimed queue)
        # This is verified by the fact that no error logs occurred

    def test_active_user_process_creates_error_for_missing_auth_email(
        self, mock_environment, collector, caplog
    ):
        """Test that ActiveUserProcess creates error event for missing auth
        email."""
        # Create entry without auth email
        entry_no_auth = CenterUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email=None,  # Missing auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        process = ActiveUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(entry_no_auth)

        # Verify existing log message still occurs
        assert "User john.doe@example.com must have authentication email" in caplog.text

        # Verify error event was created
        assert collector.has_errors()
        assert collector.error_count() == 1

        errors = collector.get_errors()
        error_event = errors[0]
        assert error_event.category == EventCategory.MISSING_DIRECTORY_DATA.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "no authentication email" in error_event.message

    def test_active_user_process_creates_error_for_bad_claim(
        self, mock_environment, collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess creates error event for bad ORCID
        claims."""
        # Setup mocks for bad claim scenario
        mock_environment.user_registry.get.return_value = []  # No person found
        mock_environment.user_registry.has_bad_claim.return_value = True
        mock_environment.user_registry.get_bad_claim.return_value = [
            Mock(spec=RegistryPerson)
        ]  # Return list

        process = ActiveUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_active_entry)

        # Verify existing log message still occurs
        assert (
            "Active user has incomplete claim: John Doe, john.doe@example.com"
            in caplog.text
        )

        # Verify error event was created
        assert collector.has_errors()
        assert collector.error_count() == 1

        errors = collector.get_errors()
        error_event = errors[0]
        assert error_event.category == EventCategory.BAD_ORCID_CLAIMS.value
        assert error_event.user_context.email == "john.doe@example.com"
        assert "incomplete claim" in error_event.message

    def test_active_user_process_no_error_for_missing_creation_date(
        self, mock_environment, collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess does NOT create error event for missing
        creation date (defensive check)."""
        # Setup mocks for missing creation date scenario
        mock_person = Mock(spec=RegistryPerson)
        mock_person.creation_date = None  # No creation date

        mock_environment.user_registry.get.return_value = [mock_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.WARNING):
            process.visit(sample_active_entry)

        # Verify existing log message still occurs
        assert (
            "person record for john.doe@example.com has no creation date" in caplog.text
        )

        # Verify NO error event was created (this is a defensive check)
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_active_user_process_no_error_for_missing_registry_id(
        self, mock_environment, collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess handles claimed user with
        registry_person attached."""
        # Setup mocks for claimed user scenario
        mock_person = Mock(spec=RegistryPerson)
        mock_person.creation_date = "2024-01-01"
        mock_person.is_claimed.return_value = True
        mock_person.registry_id.return_value = "reg123"

        mock_environment.user_registry.get.return_value = [mock_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.INFO):
            process.visit(sample_active_entry)

        # Verify the entry was registered with the registry_person
        assert sample_active_entry.is_registered
        assert sample_active_entry.registry_person == mock_person

        # Verify NO error event was created
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_active_user_process_handles_new_user_registration(
        self, mock_environment, collector, sample_active_entry, caplog
    ):
        """Test that ActiveUserProcess handles new user registration without
        errors."""
        # Setup mocks for new user scenario
        mock_environment.user_registry.get.return_value = []  # No person found
        mock_environment.user_registry.has_bad_claim.return_value = False
        mock_environment.user_registry.get_bad_claim.return_value = []
        mock_environment.user_registry.add.return_value = []
        mock_environment.user_registry.coid = 123  # Set coid as integer

        process = ActiveUserProcess(mock_environment, collector)

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
        assert not collector.has_errors()
        assert collector.error_count() == 0

        # Verify notification was sent
        mock_environment.notification_client.send_claim_email.assert_called_once_with(
            sample_active_entry
        )

    def test_active_user_process_domain_candidates_emit_near_miss_no_skeleton(
        self, mock_environment, collector, caplog
    ):
        """Test that domain-aware candidates trigger near-miss event and
        prevent skeleton creation."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Alice", last_name="Smith"),
            email="alice@med.umich.edu",
            auth_email="alice@med.umich.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=100,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No exact match, no bad claim
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []

        # Domain-aware lookup returns a candidate
        mock_candidate_person = Mock(spec=RegistryPerson)
        mock_candidate_person.registry_id.return_value = "reg-domain-1"
        mock_candidate_person.primary_name = "Alice Smith"
        mock_candidate_person.email_address = Mock()
        mock_candidate_person.email_address.mail = "alice@umich.edu"

        domain_candidate = DomainCandidate(
            person=mock_candidate_person,
            matched_email="alice@umich.edu",
            query_domain="med.umich.edu",
            candidate_domain="umich.edu",
            parent_domain="umich.edu",
        )
        mock_environment.user_registry.get_by_parent_domain.return_value = [
            domain_candidate
        ]
        mock_environment.user_registry.get_by_name.return_value = []

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify near-miss event was emitted
        assert collector.has_errors()
        errors = collector.get_errors()
        assert any(e.category == EventCategory.DOMAIN_NEAR_MISS.value for e in errors)

        # Verify skeleton was NOT created
        mock_environment.user_registry.add.assert_not_called()
        mock_environment.notification_client.send_claim_email.assert_not_called()

    def test_active_user_process_name_candidates_emit_near_miss_no_skeleton(
        self, mock_environment, collector, caplog
    ):
        """Test that name-based candidates trigger near-miss event and prevent
        skeleton creation."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Bob", last_name="Jones"),
            email="bob@newdomain.edu",
            auth_email="bob@newdomain.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=200,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No exact match, no bad claim, no domain candidates
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []
        mock_environment.user_registry.get_by_parent_domain.return_value = []

        # Name-based lookup returns a candidate
        mock_name_person = Mock(spec=RegistryPerson)
        mock_name_person.registry_id.return_value = "reg-name-1"
        mock_name_person.primary_name = "Bob Jones"
        mock_name_person.email_address = Mock()
        mock_name_person.email_address.mail = "bob.jones@olddomain.edu"

        mock_environment.user_registry.get_by_name.return_value = [mock_name_person]

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify near-miss event was emitted
        assert collector.has_errors()
        errors = collector.get_errors()
        assert any(e.category == EventCategory.NAME_NEAR_MISS.value for e in errors)

        # Verify skeleton was NOT created
        mock_environment.user_registry.add.assert_not_called()
        mock_environment.notification_client.send_claim_email.assert_not_called()

    def test_active_user_process_combined_candidates_emit_combined_near_miss(
        self, mock_environment, collector, caplog
    ):
        """Test that overlapping domain and name candidates trigger combined
        near-miss event."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Carol", last_name="White"),
            email="carol@med.umich.edu",
            auth_email="carol@med.umich.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=300,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No exact match, no bad claim
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []

        # Same person appears in both domain and name results
        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = "reg-combined-1"
        mock_person.primary_name = "Carol White"
        mock_person.email_address = Mock()
        mock_person.email_address.mail = "carol@umich.edu"

        domain_candidate = DomainCandidate(
            person=mock_person,
            matched_email="carol@umich.edu",
            query_domain="med.umich.edu",
            candidate_domain="umich.edu",
            parent_domain="umich.edu",
        )
        mock_environment.user_registry.get_by_parent_domain.return_value = [
            domain_candidate
        ]
        mock_environment.user_registry.get_by_name.return_value = [mock_person]

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify combined near-miss event was emitted
        assert collector.has_errors()
        errors = collector.get_errors()
        assert any(e.category == EventCategory.COMBINED_NEAR_MISS.value for e in errors)

        # Verify skeleton was NOT created
        mock_environment.user_registry.add.assert_not_called()

    def test_active_user_process_no_candidates_creates_skeleton(
        self, mock_environment, collector, caplog
    ):
        """Test that when no candidates are found, skeleton is still
        created."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Dave", last_name="Brown"),
            email="dave@brand-new.edu",
            auth_email="dave@brand-new.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=400,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No matches anywhere
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []
        mock_environment.user_registry.get_by_parent_domain.return_value = []
        mock_environment.user_registry.get_by_name.return_value = []
        mock_environment.user_registry.add.return_value = []
        mock_environment.user_registry.coid = 1

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify skeleton WAS created
        mock_environment.user_registry.add.assert_called_once()
        mock_environment.notification_client.send_claim_email.assert_called_once()

        # Verify no near-miss errors
        errors = collector.get_errors()
        near_miss_categories = {
            EventCategory.DOMAIN_NEAR_MISS.value,
            EventCategory.NAME_NEAR_MISS.value,
            EventCategory.COMBINED_NEAR_MISS.value,
        }
        assert not any(e.category in near_miss_categories for e in errors)

    def test_add_to_registry_passes_multiple_emails_when_distinct(
        self, mock_environment, collector, caplog
    ):
        """Test that __add_to_registry passes both contact and auth email when
        they are distinct."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Eve", last_name="Green"),
            email="eve.contact@example.com",
            auth_email="eve.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=500,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No matches anywhere — triggers skeleton creation
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []
        mock_environment.user_registry.get_by_parent_domain.return_value = []
        mock_environment.user_registry.get_by_name.return_value = []
        mock_environment.user_registry.add.return_value = []
        mock_environment.user_registry.coid = 1

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify add was called
        mock_environment.user_registry.add.assert_called_once()

        # Get the RegistryPerson passed to add()
        added_person = mock_environment.user_registry.add.call_args[0][0]
        email_addresses = added_person.email_addresses

        # Both emails should be present since they are distinct
        email_mails = [addr.mail for addr in email_addresses]
        assert "eve.auth@example.com" in email_mails
        assert "eve.contact@example.com" in email_mails
        assert len(email_addresses) == 2

    def test_add_to_registry_passes_single_email_when_same(
        self, mock_environment, collector, caplog
    ):
        """Test that __add_to_registry passes single email when contact and
        auth email are the same."""
        entry = CenterUserEntry(
            name=PersonName(first_name="Frank", last_name="Gray"),
            email="frank@example.com",
            auth_email="frank@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=600,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # No matches anywhere — triggers skeleton creation
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.get_bad_claim.return_value = []
        mock_environment.user_registry.get_by_parent_domain.return_value = []
        mock_environment.user_registry.get_by_name.return_value = []
        mock_environment.user_registry.add.return_value = []
        mock_environment.user_registry.coid = 1

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Verify add was called
        mock_environment.user_registry.add.assert_called_once()

        # Get the RegistryPerson passed to add()
        added_person = mock_environment.user_registry.add.call_args[0][0]
        email_addresses = added_person.email_addresses

        # Only one email since contact and auth are the same
        assert len(email_addresses) == 1
        assert email_addresses[0].mail == "frank@example.com"


class TestClaimedUserProcessIntegration:
    """Integration tests for ClaimedUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.proxy = Mock()
        mock_env.notification_client = Mock()

        # Configure wrapper methods to delegate to proxy
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.add_user = Mock(side_effect=lambda user: mock_env.proxy.add_user(user))
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: []
        )  # Default empty list

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create an UserEventCollector for testing."""
        return UserEventCollector()

    @pytest.fixture
    def failure_analyzer(self, mock_environment):
        """Create a FailureAnalyzer for testing."""
        return FailureAnalyzer(mock_environment)

    @pytest.fixture
    def sample_registered_entry(self):
        """Create a sample CenterUserEntry with registry_person for testing."""
        from users.user_registry import RegistryPerson

        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg456"

        entry = CenterUserEntry(
            name=PersonName(first_name="Jane", last_name="Smith"),
            email="jane.smith@example.com",
            auth_email="jane.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=456,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        entry.register(mock_registry_person)
        return entry

    def test_claimed_user_process_preserves_existing_functionality(
        self,
        mock_environment,
        collector,
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

        claimed_queue: UserQueue[ActiveUserEntry] = UserQueue()
        process = ClaimedUserProcess(mock_environment, claimed_queue, collector)

        # Process the entry
        process.visit(sample_registered_entry)

        # Verify existing functionality is preserved
        mock_environment.proxy.find_user.assert_called_with("reg456")

        # Verify no errors were collected for successful processing
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_claimed_user_process_creates_user_when_not_found(
        self,
        mock_environment,
        collector,
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

        claimed_queue: UserQueue[ActiveUserEntry] = UserQueue()
        process = ClaimedUserProcess(mock_environment, claimed_queue, collector)

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
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_claimed_user_process_uses_failure_analyzer_for_creation_failure(
        self, mock_environment, collector, sample_registered_entry, caplog
    ):
        """Test that ClaimedUserProcess uses FailureAnalyzer for Flywheel user
        creation failures."""
        # Setup mocks for failure scenario
        mock_environment.proxy.find_user.return_value = None
        flywheel_error = FlywheelError("Permission denied")
        mock_environment.proxy.add_user.side_effect = flywheel_error

        claimed_queue: UserQueue[ActiveUserEntry] = UserQueue()

        # Create a real failure analyzer for this test

        process = ClaimedUserProcess(mock_environment, claimed_queue, collector)

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
        assert collector.has_errors()
        assert collector.error_count() == 1

        errors = collector.get_errors()
        error_event = errors[0]
        assert error_event.category == EventCategory.INSUFFICIENT_PERMISSIONS.value
        assert error_event.user_context.email == "jane.smith@example.com"
        assert "Insufficient permissions" in error_event.message

    def test_claimed_user_process_handles_user_not_found_after_creation(
        self,
        mock_environment,
        collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that ClaimedUserProcess handles case where user is not found
        after creation."""
        # Setup mocks for user not found after creation
        mock_environment.proxy.find_user.return_value = None  # Always not found
        mock_environment.proxy.add_user.return_value = "user123"

        claimed_queue: UserQueue[ActiveUserEntry] = UserQueue()
        process = ClaimedUserProcess(mock_environment, claimed_queue, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert "Failed to add user jane.smith@example.com with ID reg456" in caplog.text

        # Verify no errors were collected (this is existing behavior)
        assert not collector.has_errors()
        assert collector.error_count() == 0


class TestUpdateUserProcessIntegration:
    """Integration tests for UpdateUserProcess with error handling."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.proxy = Mock()

        # Configure wrapper methods to delegate to proxy
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.add_user = Mock(side_effect=lambda user: mock_env.proxy.add_user(user))
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create an UserEventCollector for testing."""
        return UserEventCollector()

    @pytest.fixture
    def failure_analyzer(self, mock_environment):
        """Create a FailureAnalyzer for testing."""
        return FailureAnalyzer(mock_environment)

    @pytest.fixture
    def sample_registered_entry(self):
        """Create a sample CenterUserEntry with registry_person for testing."""
        from users.user_registry import RegistryPerson

        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg789"

        entry = CenterUserEntry(
            name=PersonName(first_name="Bob", last_name="Wilson"),
            email="bob.wilson@example.com",
            auth_email="bob.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=789,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        entry.register(mock_registry_person)
        return entry

    def test_update_user_process_preserves_existing_functionality(
        self,
        mock_environment,
        collector,
        failure_analyzer,
        sample_registered_entry,
    ):
        """Test that UpdateUserProcess preserves existing functionality when no
        errors occur."""
        # Setup mocks for successful processing
        # Set up the email on the entry's registry_person (NEW behavior)
        sample_registered_entry.registry_person.email_address = Mock()
        sample_registered_entry.registry_person.email_address.mail = (
            "bob.registry@example.com"
        )

        mock_fw_user = Mock()
        mock_fw_user.email = "bob.wilson@example.com"

        mock_environment.proxy.find_user.return_value = mock_fw_user

        process = UpdateUserProcess(mock_environment, collector)

        # Process the entry
        process.visit(sample_registered_entry)

        # Verify existing functionality is preserved
        mock_environment.proxy.find_user.assert_called_once_with("reg789")

        # Verify no errors were collected for successful processing
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_update_user_process_uses_failure_analyzer_for_missing_registry_person(
        self, mock_environment, collector, caplog
    ):
        """Test that UpdateUserProcess handles entry without
        registry_person."""
        # Create an entry WITHOUT registry_person (unregistered)
        entry = CenterUserEntry(
            name=PersonName(first_name="Bob", last_name="Wilson"),
            email="bob.wilson@example.com",
            auth_email="bob.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=789,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        # Don't call entry.register() - leave it unregistered

        process = UpdateUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(entry)

        # Verify error log message occurs
        assert (
            "Cannot update user without registry_person: bob.wilson@example.com"
            in caplog.text
        )

        # Verify NO error event was created (this is a defensive check)
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_update_user_process_no_error_for_missing_flywheel_user(
        self,
        mock_environment,
        collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that UpdateUserProcess does NOT create error event for missing
        Flywheel user (defensive check)."""
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

        process = UpdateUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert (
            "Expected user bob.wilson@example.com with ID reg789 in Flywheel not found"
            in caplog.text
        )

        # Verify NO error event was created (this is a defensive check)
        assert not collector.has_errors()
        assert collector.error_count() == 0

    def test_update_user_process_no_error_for_missing_registry_email(
        self,
        mock_environment,
        collector,
        failure_analyzer,
        sample_registered_entry,
        caplog,
    ):
        """Test that UpdateCenterUserProcess does NOT create error event for
        missing registry email address (defensive check)."""
        # Setup mocks for missing registry email scenario
        # Set the email_address to None on the entry's registry_person
        sample_registered_entry.registry_person.email_address = None

        # Set fw_user on the entry (required by UpdateCenterUserProcess)
        mock_fw_user = Mock()
        mock_fw_user.email = "bob.wilson@example.com"
        sample_registered_entry.set_fw_user(mock_fw_user)

        process = UpdateCenterUserProcess(mock_environment, collector)

        # Process the entry
        with caplog.at_level(logging.ERROR):
            process.visit(sample_registered_entry)

        # Verify existing log message still occurs
        assert "Registry record does not have email address: reg789" in caplog.text

        # Verify NO error event was created (this is a defensive check)
        assert not collector.has_errors()
        assert collector.error_count() == 0


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

        # Configure wrapper methods to delegate to proxy
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.add_user = Mock(side_effect=lambda user: mock_env.proxy.add_user(user))
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        # Domain-aware and name-based fallback defaults (return no candidates)
        mock_env.user_registry.get_by_parent_domain = Mock(return_value=[])
        mock_env.user_registry.get_by_name = Mock(return_value=[])

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create an UserEventCollector for testing."""
        return UserEventCollector()

    def test_multiple_error_types_collected_in_single_run(
        self, mock_environment, collector, caplog
    ):
        """Test that multiple different error types are collected in a single
        run."""
        # Create entries that will trigger different error types
        entry_no_auth = CenterUserEntry(
            name=PersonName(first_name="No", last_name="Auth"),
            email="no.auth@example.com",
            auth_email=None,  # Missing auth email
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        entry_bad_claim = CenterUserEntry(
            name=PersonName(first_name="Bad", last_name="Claim"),
            email="bad.claim@example.com",
            auth_email="bad.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # Setup mocks for different scenarios
        mock_environment.user_registry.get.return_value = []
        mock_environment.user_registry.has_bad_claim.return_value = True
        mock_environment.user_registry.get_bad_claim.return_value = [
            Mock(spec=RegistryPerson)
        ]  # Return list

        process = ActiveUserProcess(mock_environment, collector)

        # Process both entries
        with caplog.at_level(logging.ERROR):
            process.visit(entry_no_auth)
            process.visit(entry_bad_claim)

        # Verify both error types were collected
        assert collector.has_errors()
        assert collector.error_count() == 2

        errors = collector.get_errors()
        error_categories = [error.category for error in errors]

        assert EventCategory.MISSING_DIRECTORY_DATA.value in error_categories
        assert EventCategory.BAD_ORCID_CLAIMS.value in error_categories

        # Verify both log messages occurred
        assert "no.auth@example.com must have authentication email" in caplog.text
        assert "Bad Claim, bad.claim@example.com" in caplog.text

    def test_collector_maintains_state_across_processes(
        self, mock_environment, collector
    ):
        """Test that UserEventCollector maintains state across different
        process instances."""
        # Create first process and add an error
        entry1 = CenterUserEntry(
            name=PersonName(first_name="First", last_name="User"),
            email="first@example.com",
            auth_email=None,
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        process1 = ActiveUserProcess(mock_environment, collector)
        process1.visit(entry1)

        # Verify first error was collected
        assert collector.error_count() == 1

        # Create second process with same error collector
        # Create an unregistered entry to trigger error in UpdateUserProcess
        entry2 = CenterUserEntry(
            name=PersonName(first_name="Second", last_name="User"),
            email="second@example.com",
            auth_email="second.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=456,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        # Don't register entry2 - this will trigger the error path

        process2 = UpdateUserProcess(mock_environment, collector)
        process2.visit(entry2)

        # Verify first error is still there
        assert collector.error_count() == 1

        errors = collector.get_errors()
        emails = [error.user_context.email for error in errors]
        assert "first@example.com" in emails

    def test_existing_logging_behavior_preserved_with_error_handling(
        self, mock_environment, collector, caplog
    ):
        """Test that all existing logging behavior is preserved when error
        handling is integrated."""
        # Test various scenarios to ensure all log messages still occur

        # Scenario 1: Missing auth email
        entry_no_auth = CenterUserEntry(
            name=PersonName(first_name="No", last_name="Auth"),
            email="no.auth@example.com",
            auth_email=None,
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # Scenario 2: Bad claim
        entry_bad_claim = CenterUserEntry(
            name=PersonName(first_name="Bad", last_name="Claim"),
            email="bad.claim@example.com",
            auth_email="bad.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # Scenario 3: New user registration
        entry_new_user = CenterUserEntry(
            name=PersonName(first_name="New", last_name="User"),
            email="new.user@example.com",
            auth_email="new.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
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

        def mock_get_bad_claim_side_effect(full_name):
            if full_name == "Bad Claim":
                return [Mock(spec=RegistryPerson)]  # Return list for bad claim
            return []  # Return empty list for others

        mock_environment.user_registry.get.side_effect = mock_get_side_effect
        mock_environment.user_registry.has_bad_claim.side_effect = (
            mock_has_bad_claim_side_effect
        )
        mock_environment.user_registry.get_bad_claim.side_effect = (
            mock_get_bad_claim_side_effect
        )
        mock_environment.user_registry.add.return_value = []
        mock_environment.user_registry.coid = 123  # Set coid as integer

        process = ActiveUserProcess(mock_environment, collector)

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
        assert collector.error_count() == 2  # Missing auth email and bad claim

        # Verify notification was sent for new user
        mock_environment.notification_client.send_claim_email.assert_called_once()
