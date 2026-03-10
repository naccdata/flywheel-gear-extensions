"""Test fixtures for user tests.

This module provides pytest fixtures and builders for generating test
data for user authorization tests.
"""

from typing import Callable, List, Optional
from unittest.mock import Mock

import pytest
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from flywheel.models.role_output import RoleOutput
from flywheel.models.user import User
from hypothesis import strategies as st
from users.authorizations import (
    ActionType,
    Activities,
    Activity,
    AuthMap,
    Authorizations,
    PageResource,
    Resource,
)
from users.event_models import UserEventCollector

# Test Builders


class UserBuilder:
    """Builder for creating test User objects."""

    def __init__(self):
        self._id = "test-user-id"
        self._email = "test@example.com"
        self._firstname = "Test"
        self._lastname = "User"

    def with_id(self, user_id: str) -> "UserBuilder":
        """Set the user ID.

        Args:
            user_id: The user ID

        Returns:
            Self for method chaining
        """
        self._id = user_id
        return self

    def with_email(self, email: str) -> "UserBuilder":
        """Set the user email.

        Args:
            email: The email address

        Returns:
            Self for method chaining
        """
        self._email = email
        return self

    def with_name(self, firstname: str, lastname: str) -> "UserBuilder":
        """Set the user name.

        Args:
            firstname: The first name
            lastname: The last name

        Returns:
            Self for method chaining
        """
        self._firstname = firstname
        self._lastname = lastname
        return self

    def build(self) -> User:
        """Build the User object.

        Returns:
            A mock User object with configured attributes
        """
        user = Mock(spec=User)
        user.id = self._id
        user.email = self._email
        user.firstname = self._firstname
        user.lastname = self._lastname
        return user


class AuthorizationsBuilder:
    """Builder for creating test Authorizations objects."""

    def __init__(self):
        self._activities = Activities()

    def with_page_resource(
        self, page_name: str, action: ActionType = "view"
    ) -> "AuthorizationsBuilder":
        """Add a page resource activity.

        Args:
            page_name: The page name
            action: The action type (default: "view")

        Returns:
            Self for method chaining
        """
        resource = PageResource(page=page_name)
        activity = Activity(resource=resource, action=action)
        self._activities.add(resource, activity)
        return self

    def with_activity(
        self, resource: Resource, action: ActionType
    ) -> "AuthorizationsBuilder":
        """Add a custom activity.

        Args:
            resource: The resource
            action: The action type

        Returns:
            Self for method chaining
        """
        activity = Activity(resource=resource, action=action)
        self._activities.add(resource, activity)
        return self

    def build(self) -> Authorizations:
        """Build the Authorizations object.

        Returns:
            An Authorizations object with configured activities
        """
        return Authorizations(activities=self._activities)


# Mock Factories


def create_mock_project(
    project_id: str = "test-project",
    label: str = "page-test",
    group: str = "nacc",
    **kwargs,
) -> Mock:
    """Factory for creating mock ProjectAdaptor objects.

    Args:
        project_id: The project ID (default: "test-project")
        label: The project label (default: "page-test")
        group: The group ID (default: "nacc")
        **kwargs: Additional attributes to set on the mock

    Returns:
        A mock ProjectAdaptor object
    """
    project = Mock()
    project.id = project_id
    project.label = label
    project.group = group
    project.add_user_roles = Mock(return_value=True)
    for key, value in kwargs.items():
        setattr(project, key, value)
    return project


def create_mock_nacc_group(group_id: str = "nacc", **kwargs) -> Mock:
    """Factory for creating mock NACCGroup objects.

    Args:
        group_id: The group ID (default: "nacc")
        **kwargs: Additional attributes to set on the mock

    Returns:
        A mock NACCGroup object with sensible defaults
    """
    group = Mock()
    group.id = group_id
    group.get_project = Mock(return_value=create_mock_project())
    for key, value in kwargs.items():
        setattr(group, key, value)
    return group


def create_mock_role(
    role_id: str = "test-role-id", label: str = "read-only", **kwargs
) -> RoleOutput:
    """Factory for creating mock RoleOutput objects.

    Args:
        role_id: The role ID (default: "test-role-id")
        label: The role label (default: "read-only")
        **kwargs: Additional attributes to set on the role

    Returns:
        A RoleOutput object
    """
    role = RoleOutput(id=role_id, label=label)
    for key, value in kwargs.items():
        setattr(role, key, value)
    return role


def create_mock_auth_map(**kwargs) -> Mock:
    """Factory for creating mock AuthMap objects.

    Args:
        **kwargs: Additional attributes to set on the mock

    Returns:
        A mock AuthMap object with sensible defaults
    """
    auth_map = Mock(spec=AuthMap)
    auth_map.get = Mock(return_value=[create_mock_role()])
    for key, value in kwargs.items():
        setattr(auth_map, key, value)
    return auth_map


# Pytest Fixtures


@pytest.fixture
def build_user() -> Callable[..., User]:
    """Fixture that returns a factory function for building User objects.

    Returns:
        A factory function that creates User objects
    """

    def _build(
        user_id: str = "test-user-id",
        email: str = "test@example.com",
        firstname: str = "Test",
        lastname: str = "User",
    ) -> User:
        """Build a User object for testing.

        Args:
            user_id: The user ID
            email: The email address
            firstname: The first name
            lastname: The last name

        Returns:
            A mock User object
        """
        return (
            UserBuilder()
            .with_id(user_id)
            .with_email(email)
            .with_name(firstname, lastname)
            .build()
        )

    return _build


@pytest.fixture
def build_authorizations() -> Callable[..., Authorizations]:
    """Fixture that returns a factory function for building Authorizations
    objects.

    Returns:
        A factory function that creates Authorizations objects
    """

    def _build(page_resources: Optional[List[str]] = None) -> Authorizations:
        """Build an Authorizations object for testing.

        Args:
            page_resources: List of page names to add as activities

        Returns:
            An Authorizations object
        """
        builder = AuthorizationsBuilder()
        if page_resources:
            for page_name in page_resources:
                builder.with_page_resource(page_name)
        return builder.build()

    return _build


@pytest.fixture
def mock_nacc_group() -> Mock:
    """Reusable NACCGroup mock with sensible defaults.

    Returns:
        A mock NACCGroup object
    """
    return create_mock_nacc_group()


@pytest.fixture
def mock_auth_map() -> Mock:
    """Reusable AuthMap mock with sensible defaults.

    Returns:
        A mock AuthMap object
    """
    return create_mock_auth_map()


@pytest.fixture
def mock_event_collector() -> UserEventCollector:
    """Reusable UserEventCollector instance.

    Returns:
        A UserEventCollector instance
    """
    return UserEventCollector()


@pytest.fixture
def mock_project() -> Mock:
    """Reusable ProjectAdaptor mock with sensible defaults.

    Returns:
        A mock ProjectAdaptor object
    """
    return create_mock_project()


# Pytest fixtures for COmanage-related tests


@pytest.fixture
def build_email_address() -> Callable[..., EmailAddress]:
    """Fixture that returns a factory function for building EmailAddress
    objects.

    Returns:
        A factory function that creates EmailAddress objects
    """

    def _build(
        mail: str = "test@example.com",
        email_type: str = "official",
        verified: bool = True,
    ) -> EmailAddress:
        """Build an EmailAddress object for testing.

        Args:
            mail: The email address
            email_type: The type of email (e.g., "official", "personal", "work")
            verified: Whether the email is verified

        Returns:
            An EmailAddress object
        """
        return EmailAddress(mail=mail, type=email_type, verified=verified)

    return _build


@pytest.fixture
def build_name() -> Callable[..., Name]:
    """Fixture that returns a factory function for building Name objects.

    Returns:
        A factory function that creates Name objects
    """

    def _build(
        given: str = "John",
        family: str = "Doe",
        name_type: str = "official",
        primary_name: bool = True,
    ) -> Name:
        """Build a Name object for testing.

        Args:
            given: The first/given name
            family: The last/family name
            name_type: The type of name (e.g., "official")
            primary_name: Whether this is the primary name

        Returns:
            A Name object
        """
        return Name(
            given=given, family=family, type=name_type, primary_name=primary_name
        )

    return _build


@pytest.fixture
def build_identifier() -> Callable[..., Identifier]:
    """Fixture that returns a factory function for building Identifier objects.

    Returns:
        A factory function that creates Identifier objects
    """

    def _build(
        identifier: str = "test-id-123",
        identifier_type: str = "naccid",
        status: str = "A",
        login: Optional[bool] = None,
    ) -> Identifier:
        """Build an Identifier object for testing.

        Args:
            identifier: The identifier value
            identifier_type: The type of identifier (e.g., "naccid", "oidcsub", "eppn")
            status: The status (e.g., "A" for active, "D" for deleted)
            login: Whether this identifier is used for login

        Returns:
            An Identifier object
        """
        return Identifier(
            identifier=identifier, type=identifier_type, status=status, login=login
        )

    return _build


@pytest.fixture
def build_co_person() -> Callable[..., CoPerson]:
    """Fixture that returns a factory function for building CoPerson objects.

    Returns:
        A factory function that creates CoPerson objects
    """

    def _build(
        co_id: int = 1,
        status: str = "A",
    ) -> CoPerson:
        """Build a CoPerson object for testing.

        Args:
            co_id: The CO ID
            status: The status (e.g., "A": active, "D": deleted, "S": suspended)

        Returns:
            A CoPerson object
        """
        return CoPerson(co_id=co_id, status=status, meta=None)

    return _build


@pytest.fixture
def build_org_identity() -> Callable[..., OrgIdentity]:
    """Fixture that returns a factory function for building OrgIdentity
    objects.

    Returns:
        A factory function that creates OrgIdentity objects
    """

    def _build(
        email_addresses: Optional[List[EmailAddress]] = None,
        identifiers: Optional[List[Identifier]] = None,
    ) -> OrgIdentity:
        """Build an OrgIdentity object for testing.

        Args:
            email_addresses: List of email addresses for this org identity
            identifiers: List of identifiers for this org identity

        Returns:
            An OrgIdentity object
        """
        return OrgIdentity(email_address=email_addresses, identifier=identifiers)

    return _build


@pytest.fixture
def build_coperson_message() -> Callable[..., CoPersonMessage]:
    """Fixture that returns a factory function for building CoPersonMessage
    objects.

    Returns:
        A factory function that creates CoPersonMessage objects
    """

    def _build(
        co_person: Optional[CoPerson] = None,
        email_addresses: Optional[List[EmailAddress]] = None,
        names: Optional[List[Name]] = None,
        identifiers: Optional[List[Identifier]] = None,
        org_identities: Optional[List[OrgIdentity]] = None,
        co_person_roles: Optional[List[CoPersonRole]] = None,
    ) -> CoPersonMessage:
        """Build a CoPersonMessage object for testing.

        Args:
            co_person: The CoPerson object
            email_addresses: List of email addresses
            names: List of names
            identifiers: List of identifiers
            org_identities: List of organizational identities
            co_person_roles: List of CoPerson roles

        Returns:
            A CoPersonMessage object
        """
        return CoPersonMessage(
            CoPerson=co_person,
            EmailAddress=email_addresses,
            Name=names,
            Identifier=identifiers,
            OrgIdentity=org_identities,
            CoPersonRole=co_person_roles,
        )

    return _build


# Hypothesis strategies for property-based testing


@st.composite
def email_address_strategy(
    draw, email_type: Optional[str] = None, verified: Optional[bool] = None
):
    """Generate EmailAddress with optional constraints.

    Args:
        draw: Hypothesis draw function
        email_type: If provided, use this type; otherwise randomly choose
        verified: If provided, use this value; otherwise randomly choose

    Returns:
        A randomly generated EmailAddress
    """
    mail = draw(st.emails())
    chosen_type = (
        email_type
        if email_type is not None
        else draw(st.sampled_from(["official", "personal", "work"]))
    )
    chosen_verified = verified if verified is not None else draw(st.booleans())

    return EmailAddress(mail=mail, type=chosen_type, verified=chosen_verified)


@st.composite
def name_strategy(draw, primary: Optional[bool] = None):
    """Generate Name with optional constraints.

    Args:
        draw: Hypothesis draw function
        primary: If provided, use this value for primary_name; otherwise randomly choose

    Returns:
        A randomly generated Name
    """
    given = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        )
    )
    family = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        )
    )
    primary_name = primary if primary is not None else draw(st.booleans())

    return Name(given=given, family=family, type="official", primary_name=primary_name)


@st.composite
def identifier_strategy(
    draw, identifier_type: Optional[str] = None, status: Optional[str] = None
):
    """Generate Identifier with optional constraints.

    Args:
        draw: Hypothesis draw function
        identifier_type: If provided, use this type; otherwise randomly choose
        status: If provided, use this status; otherwise randomly choose

    Returns:
        A randomly generated Identifier
    """
    chosen_type = (
        identifier_type
        if identifier_type is not None
        else draw(st.sampled_from(["naccid", "oidcsub", "eppn"]))
    )
    chosen_status = status if status is not None else draw(st.sampled_from(["A", "D"]))

    # Generate appropriate identifier value based on type
    if chosen_type == "oidcsub":
        user_id = draw(st.integers(min_value=1000, max_value=9999))
        id_value = f"http://cilogon.org/serverA/users/{user_id}"
        login = draw(st.booleans())
    else:
        id_value = f"{chosen_type}-{draw(st.integers(min_value=1000, max_value=9999))}"
        login = None

    return Identifier(
        identifier=id_value, type=chosen_type, status=chosen_status, login=login
    )


@st.composite
def coperson_message_strategy(  # noqa: C901
    draw,
    min_emails: int = 0,
    max_emails: int = 5,
    ensure_official: bool = False,
    ensure_verified: bool = False,
    ensure_org_email: bool = False,
    include_identifiers: bool = True,
    include_names: bool = True,
    status: Optional[str] = None,
):
    """Generate CoPersonMessage with configurable properties.

    This strategy avoids overzealous filtering by explicitly adding required
    email types when requested, rather than hoping random generation produces them.

    Args:
        draw: Hypothesis draw function
        min_emails: Minimum number of emails to generate
        max_emails: Maximum number of emails to generate
        ensure_official: If True, guarantee at least one official email
        ensure_verified: If True, guarantee at least one verified email
        ensure_org_email: If True, add organizational identity with email
        include_identifiers: If True, generate identifiers
        include_names: If True, generate names
        status: If provided, use this status for CoPerson; otherwise randomly choose

    Returns:
        A randomly generated CoPersonMessage
    """
    # Generate base emails
    num_emails = draw(st.integers(min_value=min_emails, max_value=max_emails))
    emails = []

    # Add required email types first to avoid filtering issues
    if ensure_official and num_emails > 0:
        emails.append(draw(email_address_strategy(email_type="official")))
        num_emails -= 1

    if ensure_verified and num_emails > 0:
        # Add verified email (may or may not be official)
        emails.append(draw(email_address_strategy(verified=True)))
        num_emails -= 1

    # Fill remaining slots with random emails
    for _ in range(num_emails):
        emails.append(draw(email_address_strategy()))

    # Shuffle to avoid position bias
    if emails:
        import random

        random.shuffle(emails)

    # Generate organizational identity with email if requested
    org_identity = None
    if ensure_org_email:
        org_email = draw(email_address_strategy())
        user_id = draw(st.integers(min_value=1000, max_value=9999))
        org_identifier = Identifier(
            identifier=f"http://cilogon.org/serverA/users/{user_id}",
            type="oidcsub",
            login=True,
            status="A",
        )
        org_identity = OrgIdentity(
            email_address=[org_email], identifier=[org_identifier]
        )

    # Generate identifiers
    identifiers = None
    if include_identifiers:
        num_identifiers = draw(st.integers(min_value=0, max_value=3))
        if num_identifiers > 0:
            identifiers = [draw(identifier_strategy()) for _ in range(num_identifiers)]

    # Generate names
    names = None
    if include_names:
        num_names = draw(st.integers(min_value=0, max_value=2))
        if num_names > 0:
            names = []
            for i in range(num_names):
                # First name is primary
                names.append(draw(name_strategy(primary=(i == 0))))

    # Generate CoPerson with random or specified status
    chosen_status = (
        status if status is not None else draw(st.sampled_from(["A", "D", "S"]))
    )
    coperson = CoPerson(co_id=1, status=chosen_status, meta=None)

    return CoPersonMessage(
        CoPerson=coperson,
        EmailAddress=emails if emails else None,
        OrgIdentity=[org_identity] if org_identity else None,
        Identifier=identifiers,
        Name=names,
        CoPersonRole=None,
    )
