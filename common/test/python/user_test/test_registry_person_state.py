"""Property-based tests for RegistryPerson claim state.

# Feature: comanage-registry-resilience, Property 3: Claim state trichotomy

**Validates: Requirements 3.1, 3.2, 3.3**

Uses Hypothesis to generate CoPersonMessage objects with random combinations
of status, verified emails, and oidcsub identifiers. Asserts exactly one of
is_claimed(), is_incomplete_claim(), is_unclaimed() is True for any active
RegistryPerson.
"""

from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from users.user_registry import RegistryPerson

# Fast email strategy: avoids the slow st.emails() for property tests
# where the actual email content doesn't matter, only its presence.
_fast_email = st.builds(
    lambda user, domain: f"{user}@{domain}.com",
    st.text(
        alphabet=st.characters(whitelist_categories=["Ll"]),
        min_size=1,
        max_size=8,
    ),
    st.text(
        alphabet=st.characters(whitelist_categories=["Ll"]),
        min_size=1,
        max_size=8,
    ),
)


@st.composite
def active_coperson_message_strategy(draw):
    """Generate an active CoPersonMessage with random email/identifier combos.

    Always generates an active CoPerson (status="A") so the trichotomy
    property applies. Varies:
    - Whether verified emails are present
    - Whether oidcsub identifiers from cilogon.org are present
    - Whether other identifiers/emails are present
    """
    coperson = CoPerson(co_id=1, status="A", meta=None)

    # Decide whether to include verified emails
    has_verified_email = draw(st.booleans())
    has_unverified_email = draw(st.booleans())

    emails = []
    if has_verified_email:
        mail = draw(_fast_email)
        emails.append(EmailAddress(mail=mail, type="official", verified=True))
    if has_unverified_email:
        mail = draw(_fast_email)
        emails.append(EmailAddress(mail=mail, type="personal", verified=False))

    # Decide whether to include oidcsub from cilogon.org
    has_oidcsub = draw(st.booleans())
    identifiers = []
    if has_oidcsub:
        user_id = draw(st.integers(min_value=1000, max_value=99999))
        identifiers.append(
            Identifier(
                identifier=f"http://cilogon.org/serverA/users/{user_id}",
                type="oidcsub",
                status="A",
            )
        )

    # Optionally add non-oidcsub identifiers
    has_other_id = draw(st.booleans())
    if has_other_id:
        identifiers.append(
            Identifier(identifier="NACC123456", type="naccid", status="A")
        )

    return CoPersonMessage(
        CoPerson=coperson,
        EmailAddress=emails if emails else None,
        Identifier=identifiers if identifiers else None,
        Name=None,
        OrgIdentity=None,
        CoPersonRole=None,
    )


@given(msg=active_coperson_message_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_claim_state_trichotomy(msg):
    """Property 3: Exactly one of is_claimed, is_incomplete_claim, is_unclaimed
    is True for any active RegistryPerson.

    # Feature: comanage-registry-resilience, Property 3: Claim state trichotomy
    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    person = RegistryPerson(msg)

    claimed = person.is_claimed()
    incomplete = person.is_incomplete_claim()
    unclaimed = person.is_unclaimed()

    states = [claimed, incomplete, unclaimed]
    assert sum(states) == 1, (
        f"Expected exactly one True, got claimed={claimed}, "
        f"incomplete={incomplete}, unclaimed={unclaimed}"
    )


@given(
    emails=st.lists(_fast_email, min_size=1, max_size=5),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_multi_email_skeleton_creation(emails):
    """Property 4: Multi-email skeleton creation.

    For any non-empty list of email strings, RegistryPerson.create(email=emails)
    produces exactly one EmailAddress per input, each with type="official".

    # Feature: comanage-registry-resilience, Property 4: Multi-email skeleton creation
    **Validates: Requirements 4.1, 4.2**
    """
    person = RegistryPerson.create(
        firstname="Test",
        lastname="User",
        email=emails,
        coid=1,
    )

    assert len(person.email_addresses) == len(emails), (
        f"Expected {len(emails)} email addresses, got {len(person.email_addresses)}"
    )

    for i, addr in enumerate(person.email_addresses):
        assert addr.mail == emails[i], (
            f"Email at index {i}: expected {emails[i]}, got {addr.mail}"
        )
        assert addr.type == "official", (
            f"Email at index {i}: expected type='official', got type='{addr.type}'"
        )
