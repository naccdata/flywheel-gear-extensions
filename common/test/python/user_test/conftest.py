"""Test fixtures for RegistryPerson tests.

This module provides pytest fixtures and Hypothesis strategies for
generating test data for RegistryPerson tests.
"""

from typing import Callable, List, Optional

import pytest
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from hypothesis import strategies as st

# Pytest fixtures that return factory functions for building test objects


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
