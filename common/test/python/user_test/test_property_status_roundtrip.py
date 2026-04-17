"""Property test for status update round-trip preservation.

**Feature: disable-inactive-comanage-users, Property 1: Status update round-trip
preserves all non-status fields**
**Validates: Requirements 1.1, 1.2, 2.1, 2.2, 6.1, 6.2, 6.3, 6.4**
"""

from copy import deepcopy
from unittest.mock import MagicMock

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from users.user_registry import UserRegistry

# --- Fast strategies to avoid slow st.emails() ---

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


# --- Hypothesis strategies for generating CoPersonMessage components ---


@st.composite
def _email_strategy(draw):
    """Generate a random EmailAddress."""
    mail = draw(_fast_email)
    email_type = draw(st.sampled_from(["official", "personal", "work"]))
    verified = draw(st.booleans())
    return EmailAddress(mail=mail, type=email_type, verified=verified)


@st.composite
def _name_strategy(draw):
    """Generate a random Name."""
    letters = st.characters(whitelist_categories=("Lu", "Ll"))
    given_name = draw(st.text(min_size=1, max_size=20, alphabet=letters))
    family = draw(st.text(min_size=1, max_size=20, alphabet=letters))
    primary = draw(st.booleans())
    return Name(given=given_name, family=family, type="official", primary_name=primary)


@st.composite
def _identifier_strategy(draw):
    """Generate a random Identifier."""
    id_type = draw(st.sampled_from(["naccid", "oidcsub", "eppn"]))
    # Identifier model only accepts "A" or "S" for status
    status = draw(st.sampled_from(["A", "S"]))
    id_value = f"{id_type}-{draw(st.integers(min_value=1000, max_value=9999))}"
    login = draw(st.booleans()) if id_type == "oidcsub" else None
    return Identifier(identifier=id_value, type=id_type, status=status, login=login)


@st.composite
def _role_strategy(draw):
    """Generate a random CoPersonRole."""
    affiliation = draw(st.sampled_from(["member", "staff", "faculty"]))
    status = draw(st.sampled_from(["A", "D"]))
    return CoPersonRole(cou_id=None, affiliation=affiliation, status=status)


@st.composite
def _org_identity_strategy(draw):
    """Generate a random OrgIdentity with optional emails and identifiers."""
    has_emails = draw(st.booleans())
    has_identifiers = draw(st.booleans())
    emails = (
        draw(st.lists(_email_strategy(), min_size=1, max_size=2))
        if has_emails
        else None
    )
    identifiers = (
        draw(st.lists(_identifier_strategy(), min_size=1, max_size=2))
        if has_identifiers
        else None
    )
    return OrgIdentity(email_address=emails, identifier=identifiers)


@st.composite
def _coperson_message_strategy(draw):
    """Generate a CoPersonMessage with random related models.

    Uses status 'A' as the initial status since the test will exercise
    both suspend (-> 'S') and re-enable (-> 'A') paths.
    """
    coperson = CoPerson(co_id=1, status="A", meta=None)

    emails = draw(st.lists(_email_strategy(), min_size=0, max_size=5))
    names = draw(st.lists(_name_strategy(), min_size=0, max_size=3))
    identifiers = draw(st.lists(_identifier_strategy(), min_size=0, max_size=3))
    roles = draw(st.lists(_role_strategy(), min_size=0, max_size=2))
    org_ids = draw(st.lists(_org_identity_strategy(), min_size=0, max_size=2))

    return CoPersonMessage(
        CoPerson=coperson,
        EmailAddress=emails if emails else None,
        Name=names if names else None,
        Identifier=identifiers if identifiers else None,
        CoPersonRole=roles if roles else None,
        OrgIdentity=org_ids if org_ids else None,
        CoGroupMember=None,
        SshKey=None,
        Url=None,
    )


# --- Helpers ---


def _build_get_response(person_message: CoPersonMessage) -> MagicMock:
    """Build a mock GetCoPerson200Response with var_0 holding the message."""
    response = MagicMock()
    response.var_0 = person_message
    return response


def _build_registry(mock_api: MagicMock) -> UserRegistry:
    """Build a UserRegistry with a mock API (dry_run=False)."""
    return UserRegistry(
        api_instance=mock_api,
        coid=1,
        name_normalizer=lambda s: " ".join(s.lower().split()),
        dry_run=False,
    )


# --- Property test ---


@given(
    original_message=_coperson_message_strategy(),
    use_suspend=st.booleans(),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_status_update_roundtrip_preserves_non_status_fields(
    original_message: CoPersonMessage,
    use_suspend: bool,
):
    """Property 1: Status update round-trip preserves all non-status fields.

    **Feature: disable-inactive-comanage-users, Property 1: Status update
    round-trip preserves all non-status fields**
    **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 6.1, 6.2, 6.3, 6.4**

    For any valid CoPersonMessage, performing a status update (GET -> modify
    status -> PUT) preserves all non-status fields and all related models
    unchanged. Only the CoPerson.status field differs.
    """
    # Arrange: snapshot the original state before mutation
    snapshot = deepcopy(original_message)

    mock_api = MagicMock(spec=DefaultApi)
    mock_api.get_co_person.return_value = _build_get_response(original_message)

    registry = _build_registry(mock_api)
    registry_id = "NACC-TEST-001"

    # Act: call suspend or re_enable
    if use_suspend:
        registry.suspend(registry_id)
        expected_status = "S"
    else:
        registry.re_enable(registry_id)
        expected_status = "A"

    # Assert: update_co_person was called with the message
    mock_api.update_co_person.assert_called_once()
    call_kwargs = mock_api.update_co_person.call_args.kwargs
    updated_message: CoPersonMessage = call_kwargs["co_person_message"]

    # Assert: CoPerson.status is the target status
    assert updated_message.co_person is not None
    assert updated_message.co_person.status == expected_status

    # Assert: all CoPerson fields except status are preserved
    assert snapshot.co_person is not None
    assert updated_message.co_person.co_id == snapshot.co_person.co_id
    assert updated_message.co_person.meta == snapshot.co_person.meta
    assert updated_message.co_person.date_of_birth == snapshot.co_person.date_of_birth
    assert updated_message.co_person.timezone == snapshot.co_person.timezone

    # Assert: all related models are identical to the original
    assert updated_message.email_address == snapshot.email_address
    assert updated_message.name == snapshot.name
    assert updated_message.identifier == snapshot.identifier
    assert updated_message.org_identity == snapshot.org_identity
    assert updated_message.co_person_role == snapshot.co_person_role
    assert updated_message.co_group_member == snapshot.co_group_member
    assert updated_message.ssh_key == snapshot.ssh_key
    assert updated_message.url == snapshot.url
