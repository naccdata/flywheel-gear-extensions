"""Tests for user entry registration functionality."""

from unittest.mock import Mock

import pytest
from users.authorizations import Authorizations
from users.user_entry import ActiveUserEntry, CenterUserEntry, PersonName
from users.user_registry import RegistryPerson


class TestActiveUserEntryRegistration:
    """Tests for ActiveUserEntry registration functionality."""

    @pytest.fixture
    def unregistered_entry(self):
        """Create an unregistered ActiveUserEntry."""
        return ActiveUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            authorizations=Authorizations(),
        )

    @pytest.fixture
    def mock_registry_person(self):
        """Create a mock RegistryPerson."""
        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = "reg123"
        return mock_person

    def test_unregistered_entry_is_not_registered(self, unregistered_entry):
        """Test that a new entry is not registered by default."""
        assert not unregistered_entry.is_registered
        assert unregistered_entry.registry_id is None
        assert unregistered_entry.user_id is None
        assert unregistered_entry.registry_person is None

    def test_register_method_attaches_registry_person(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that register() method attaches the registry person."""
        unregistered_entry.register(mock_registry_person)

        assert unregistered_entry.is_registered
        assert unregistered_entry.registry_person == mock_registry_person
        assert unregistered_entry.registry_id == "reg123"
        assert unregistered_entry.user_id == "reg123"

    def test_registry_id_property_returns_id_from_registry_person(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that registry_id property calls registry_id() on registry
        person."""
        unregistered_entry.register(mock_registry_person)

        registry_id = unregistered_entry.registry_id

        assert registry_id == "reg123"
        mock_registry_person.registry_id.assert_called()

    def test_user_id_property_returns_same_as_registry_id(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that user_id property returns the same value as registry_id."""
        unregistered_entry.register(mock_registry_person)

        assert unregistered_entry.user_id == unregistered_entry.registry_id

    def test_as_user_raises_error_for_unregistered_entry(self, unregistered_entry):
        """Test that as_user() raises ValueError for unregistered entry."""
        with pytest.raises(ValueError, match="Cannot create User from unregistered"):
            unregistered_entry.as_user()

    def test_as_user_creates_user_for_registered_entry(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that as_user() creates a User object for registered entry."""
        unregistered_entry.register(mock_registry_person)

        user = unregistered_entry.as_user()

        assert user.id == "reg123"
        assert user.email == "reg123"
        assert user.firstname == "John"
        assert user.lastname == "Doe"

    def test_registry_person_excluded_from_serialization(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that registry_person is excluded from model serialization."""
        unregistered_entry.register(mock_registry_person)

        # Serialize the entry
        serialized = unregistered_entry.model_dump()

        # Verify registry_person is not in the serialized output
        assert "registry_person" not in serialized

        # Verify other fields are present
        assert serialized["email"] == "john.doe@example.com"
        assert serialized["name"]["first_name"] == "John"

    def test_registry_person_excluded_from_json_serialization(
        self, unregistered_entry, mock_registry_person
    ):
        """Test that registry_person is excluded from JSON serialization."""
        unregistered_entry.register(mock_registry_person)

        # Serialize to JSON
        json_str = unregistered_entry.model_dump_json()

        # Verify registry_person is not in the JSON output
        assert "registry_person" not in json_str

        # Verify other fields are present
        assert "john.doe@example.com" in json_str
        assert "John" in json_str


class TestCenterUserEntryRegistration:
    """Tests for CenterUserEntry registration functionality (inherits from
    ActiveUserEntry)."""

    @pytest.fixture
    def unregistered_center_entry(self):
        """Create an unregistered CenterUserEntry."""
        return CenterUserEntry(
            name=PersonName(first_name="Jane", last_name="Smith"),
            email="jane.smith@example.com",
            auth_email="jane.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

    @pytest.fixture
    def mock_registry_person(self):
        """Create a mock RegistryPerson."""
        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = "reg456"
        return mock_person

    def test_center_entry_inherits_registration_functionality(
        self, unregistered_center_entry, mock_registry_person
    ):
        """Test that CenterUserEntry inherits registration functionality from
        ActiveUserEntry."""
        # Initially unregistered
        assert not unregistered_center_entry.is_registered
        assert unregistered_center_entry.registry_id is None

        # Register the entry
        unregistered_center_entry.register(mock_registry_person)

        # Now registered
        assert unregistered_center_entry.is_registered
        assert unregistered_center_entry.registry_id == "reg456"
        assert unregistered_center_entry.registry_person == mock_registry_person

    def test_center_entry_as_user_works_when_registered(
        self, unregistered_center_entry, mock_registry_person
    ):
        """Test that CenterUserEntry.as_user() works when registered."""
        unregistered_center_entry.register(mock_registry_person)

        user = unregistered_center_entry.as_user()

        assert user.id == "reg456"
        assert user.email == "reg456"
        assert user.firstname == "Jane"
        assert user.lastname == "Smith"

    def test_center_entry_registry_person_excluded_from_serialization(
        self, unregistered_center_entry, mock_registry_person
    ):
        """Test that registry_person is excluded from CenterUserEntry
        serialization."""
        unregistered_center_entry.register(mock_registry_person)

        serialized = unregistered_center_entry.model_dump()

        # Verify registry_person is not in the serialized output
        assert "registry_person" not in serialized

        # Verify center-specific fields are present
        assert serialized["org_name"] == "Test Center"
        assert serialized["adcid"] == 123


class TestRegistrationEdgeCases:
    """Tests for edge cases in registration functionality."""

    def test_registry_id_returns_none_when_registry_person_has_no_id(self):
        """Test that registry_id returns None when
        registry_person.registry_id() returns None."""
        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="test@example.com",
            auth_email="test.auth@example.com",
            active=True,
            approved=True,
            authorizations=Authorizations(),
        )

        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = None

        entry.register(mock_person)

        # Entry is registered (has registry_person)
        assert entry.is_registered
        # But registry_id is None
        assert entry.registry_id is None
        assert entry.user_id is None

    def test_as_user_raises_error_when_registry_id_is_none(self):
        """Test that as_user() raises error when registry_id is None even if
        registered."""
        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="test@example.com",
            auth_email="test.auth@example.com",
            active=True,
            approved=True,
            authorizations=Authorizations(),
        )

        mock_person = Mock(spec=RegistryPerson)
        mock_person.registry_id.return_value = None

        entry.register(mock_person)

        # This should raise an AssertionError due to the assert in as_user()
        with pytest.raises(AssertionError):
            entry.as_user()

    def test_multiple_registrations_replace_registry_person(self):
        """Test that calling register() multiple times replaces the registry
        person."""
        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="test@example.com",
            auth_email="test.auth@example.com",
            active=True,
            approved=True,
            authorizations=Authorizations(),
        )

        # First registration
        mock_person1 = Mock(spec=RegistryPerson)
        mock_person1.registry_id.return_value = "reg111"
        entry.register(mock_person1)
        assert entry.registry_id == "reg111"

        # Second registration (replaces first)
        mock_person2 = Mock(spec=RegistryPerson)
        mock_person2.registry_id.return_value = "reg222"
        entry.register(mock_person2)
        assert entry.registry_id == "reg222"
        assert entry.registry_person == mock_person2
