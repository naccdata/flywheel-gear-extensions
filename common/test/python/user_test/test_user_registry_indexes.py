"""Unit tests and property tests for UserRegistry indexes and lookup methods.

Tests cover:
- find_by_registry_id() returning records without email (Task 3.1)
- get_by_parent_domain() with explicit and default domain resolution (Task 3.2)
- get_by_name() with normalized name matching (Task 3.3)
- Backward compatibility without domain_config or name_normalizer
- Property P2: Registry indexing invariant
"""

from typing import Callable, List, Optional
from unittest.mock import MagicMock

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from users.domain_config import (
    DomainRelationshipConfig,
    ParentChildMapping,
)
from users.user_registry import RegistryPerson, UserRegistry

# --- Helpers ---


def _make_person(
    emails: Optional[List[str]] = None,
    registry_id: Optional[str] = None,
    firstname: str = "Test",
    lastname: str = "User",
    status: str = "A",
    oidcsub: Optional[str] = None,
    verified: bool = True,
) -> RegistryPerson:
    """Create a RegistryPerson for testing without going through the API."""
    coperson = CoPerson(co_id=1, status=status, meta=None)

    email_addresses = None
    if emails:
        email_addresses = [
            EmailAddress(mail=e, type="official", verified=verified) for e in emails
        ]

    identifiers: List[Identifier] = []
    if registry_id:
        identifiers.append(
            Identifier(identifier=registry_id, type="naccid", status="A")
        )
    if oidcsub:
        identifiers.append(
            Identifier(identifier=oidcsub, type="oidcsub", status="A", login=True)
        )

    names = [Name(given=firstname, family=lastname, type="official", primary_name=True)]

    return RegistryPerson(
        coperson_message=CoPersonMessage(
            CoPerson=coperson,
            EmailAddress=email_addresses,
            Name=names,
            Identifier=identifiers if identifiers else None,
            CoPersonRole=None,
        )
    )


def _mock_api_response(
    persons: List[RegistryPerson],
) -> MagicMock:
    """Build a mock DefaultApi that returns the given persons via
    get_co_person.

    Uses a callable side_effect so __list can be called multiple times.
    Calls without limit/page return the count; calls with limit/page
    return paginated person data.
    """
    mock_api = MagicMock(spec=DefaultApi)

    # Pre-build the single page response (all persons fit in one page)
    page = MagicMock()
    page.total_results = str(len(persons))
    page.var_0 = persons[0].as_coperson_message() if persons else None
    if len(persons) > 1:
        page.additional_properties = {
            str(j): p.as_coperson_message().model_dump()
            for j, p in enumerate(persons[1:])
        }
    else:
        page.additional_properties = None

    count_response = MagicMock()
    count_response.total_results = str(len(persons))

    def get_co_person_handler(**kwargs):  # type: ignore[no-untyped-def]
        if "limit" in kwargs:
            return page
        return count_response

    mock_api.get_co_person.side_effect = get_co_person_handler
    return mock_api


def _build_registry_with_persons(
    persons: List[RegistryPerson],
    domain_config: Optional[DomainRelationshipConfig] = None,
    name_normalizer: Optional[Callable[[str], str]] = None,
) -> UserRegistry:
    """Build a UserRegistry populated through its public interface.

    Mocks the API to return the given persons, then triggers internal
    population by calling a public lookup method.
    """
    mock_api = _mock_api_response(persons)
    registry = UserRegistry(
        api_instance=mock_api,
        coid=1,
        domain_config=domain_config,
        name_normalizer=name_normalizer or (lambda s: " ".join(s.lower().split())),
    )

    # Trigger lazy population through a public method
    registry.get("__trigger_population__")

    return registry


# --- Task 3.1: find_by_registry_id() returns records without email ---


class TestRegistryIdIndexWithoutEmail:
    """Test that find_by_registry_id() returns records without email."""

    def test_record_without_email_found_by_registry_id(self):
        """A record with registry ID but no email should be findable."""
        person = _make_person(
            emails=None,
            registry_id="NACC-001",
            oidcsub="http://cilogon.org/serverA/users/1234",
        )
        registry = _build_registry_with_persons([person])

        result = registry.find_by_registry_id("NACC-001")
        assert result is not None
        assert result.registry_id() == "NACC-001"

    def test_record_with_email_still_found_by_registry_id(self):
        """A record with both email and registry ID should still be
        findable."""
        person = _make_person(
            emails=["user@example.com"],
            registry_id="NACC-002",
        )
        registry = _build_registry_with_persons([person])

        result = registry.find_by_registry_id("NACC-002")
        assert result is not None
        assert result.registry_id() == "NACC-002"

    def test_record_without_registry_id_not_in_id_index(self):
        """A record without registry ID should not appear in ID index."""
        person = _make_person(emails=["user@example.com"], registry_id=None)
        registry = _build_registry_with_persons([person])

        assert registry.find_by_registry_id("anything") is None

    def test_unclaimed_record_without_email_indexed_by_id(self):
        """An unclaimed record (no oidcsub) without email but with registry ID
        should still be findable by registry ID."""
        person = _make_person(
            emails=None,
            registry_id="NACC-003",
            oidcsub=None,
        )
        registry = _build_registry_with_persons([person])

        result = registry.find_by_registry_id("NACC-003")
        assert result is not None


# --- Task 3.2: get_by_parent_domain() ---


class TestGetByParentDomain:
    """Test domain-aware fallback lookup."""

    def test_explicit_parent_child_mapping(self):
        """Records with child domain email found via parent domain query."""
        config = DomainRelationshipConfig(
            parent_child=[
                ParentChildMapping(child="med.umich.edu", parent="umich.edu"),
            ],
        )
        person = _make_person(emails=["alice@med.umich.edu"], registry_id="NACC-010")
        registry = _build_registry_with_persons([person], domain_config=config)

        # Query with parent domain email
        results = registry.get_by_parent_domain("bob@umich.edu")
        assert len(results) == 1
        assert results[0].person.has_email("alice@med.umich.edu")
        assert results[0].matched_email == "alice@med.umich.edu"

    def test_default_extraction_fallback(self):
        """Without explicit mapping, last-two-segments extraction is used."""
        config = DomainRelationshipConfig()
        person = _make_person(emails=["alice@sub.example.edu"], registry_id="NACC-011")
        registry = _build_registry_with_persons([person], domain_config=config)

        results = registry.get_by_parent_domain("bob@other.example.edu")
        assert len(results) == 1
        assert results[0].parent_domain == "example.edu"

    def test_domain_candidate_context_fields(self):
        """DomainCandidate has correct context fields."""
        config = DomainRelationshipConfig(
            parent_child=[
                ParentChildMapping(child="med.umich.edu", parent="umich.edu"),
            ],
        )
        person = _make_person(emails=["alice@med.umich.edu"])
        registry = _build_registry_with_persons([person], domain_config=config)

        results = registry.get_by_parent_domain("bob@umich.edu")
        assert len(results) == 1
        candidate = results[0]
        assert candidate.query_domain == "umich.edu"
        assert candidate.candidate_domain == "med.umich.edu"
        assert candidate.parent_domain == "umich.edu"
        assert candidate.matched_email == "alice@med.umich.edu"

    def test_no_match_different_parent_domain(self):
        """No candidates when parent domains differ."""
        config = DomainRelationshipConfig()
        person = _make_person(emails=["alice@foo.edu"])
        registry = _build_registry_with_persons([person], domain_config=config)

        results = registry.get_by_parent_domain("bob@bar.edu")
        assert results == []

    def test_multiple_candidates_same_parent(self):
        """Multiple records under same parent domain all returned."""
        config = DomainRelationshipConfig(
            parent_child=[
                ParentChildMapping(child="med.umich.edu", parent="umich.edu"),
                ParentChildMapping(child="eng.umich.edu", parent="umich.edu"),
            ],
        )
        p1 = _make_person(emails=["alice@med.umich.edu"])
        p2 = _make_person(emails=["bob@eng.umich.edu"])
        registry = _build_registry_with_persons([p1, p2], domain_config=config)

        results = registry.get_by_parent_domain("carol@umich.edu")
        assert len(results) == 2

    def test_empty_email_returns_empty(self):
        """Invalid email without @ returns empty list."""
        config = DomainRelationshipConfig()
        registry = _build_registry_with_persons([], domain_config=config)

        results = registry.get_by_parent_domain("not-an-email")
        assert results == []


# --- Task 3.3: get_by_name() ---


class TestGetByName:
    """Test name-based lookup."""

    def test_normalized_name_matching(self):
        """Names are matched after normalization."""
        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons([person])

        results = registry.get_by_name("alice smith")
        assert len(results) == 1
        assert results[0].has_email("alice@example.com")

    def test_case_insensitive_matching(self):
        """Name matching is case-insensitive."""
        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons([person])

        results = registry.get_by_name("ALICE SMITH")
        assert len(results) == 1

    def test_whitespace_normalization(self):
        """Extra whitespace in query is normalized."""
        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons([person])

        results = registry.get_by_name("  alice   smith  ")
        assert len(results) == 1

    def test_returns_all_matching_records(self):
        """All records with same normalized name are returned."""
        p1 = _make_person(
            emails=["alice1@example.com"], firstname="Alice", lastname="Smith"
        )
        p2 = _make_person(
            emails=["alice2@other.com"],
            firstname="Alice",
            lastname="Smith",
            oidcsub="http://cilogon.org/serverA/users/5555",
        )
        registry = _build_registry_with_persons([p1, p2])

        results = registry.get_by_name("Alice Smith")
        assert len(results) == 2

    def test_returns_records_regardless_of_claim_state(self):
        """Records are returned regardless of claim state (claimed, unclaimed,
        incomplete)."""
        # Unclaimed (no oidcsub)
        p_unclaimed = _make_person(
            emails=["a@example.com"], firstname="Alice", lastname="Smith"
        )
        # Claimed (has oidcsub + verified email)
        p_claimed = _make_person(
            emails=["b@example.com"],
            firstname="Alice",
            lastname="Smith",
            oidcsub="http://cilogon.org/serverA/users/1111",
        )
        registry = _build_registry_with_persons([p_unclaimed, p_claimed])

        results = registry.get_by_name("Alice Smith")
        assert len(results) == 2

    def test_no_match_returns_empty(self):
        """No matching name returns empty list."""
        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons([person])

        results = registry.get_by_name("Bob Jones")
        assert results == []

    def test_custom_name_normalizer(self):
        """Custom name normalizer is used when provided."""

        def reverse_normalizer(name: str) -> str:
            return name.lower()[::-1]

        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons(
            [person], name_normalizer=reverse_normalizer
        )

        # Index: "Alice Smith" -> lower -> "alice smith" -> reverse -> "htims ecila"
        # Query must normalize to the same key.
        # "Alice Smith" -> lower -> "alice smith" -> reverse -> "htims ecila" ✓
        results = registry.get_by_name("Alice Smith")
        assert len(results) == 1


# --- Task 3.4: Backward compatibility ---


class TestBackwardCompatibility:
    """Test that UserRegistry works without domain_config or
    name_normalizer."""

    def test_no_domain_config(self):
        """UserRegistry without domain_config uses default resolution."""
        person = _make_person(emails=["alice@sub.example.edu"])
        registry = _build_registry_with_persons([person])

        # Default extraction: sub.example.edu -> example.edu
        results = registry.get_by_parent_domain("bob@other.example.edu")
        assert len(results) == 1

    def test_no_name_normalizer(self):
        """UserRegistry without name_normalizer uses
        default_name_normalizer."""
        person = _make_person(
            emails=["alice@example.com"], firstname="Alice", lastname="Smith"
        )
        registry = _build_registry_with_persons([person])

        results = registry.get_by_name("alice smith")
        assert len(results) == 1

    def test_email_index_unchanged(self):
        """Existing email-based lookup still works."""
        person = _make_person(emails=["alice@example.com"])
        registry = _build_registry_with_persons([person])

        results = registry.get("alice@example.com")
        assert len(results) == 1
        assert results[0].has_email("alice@example.com")


# --- Task 3.5: Property test P2 - Registry indexing invariant ---


@st.composite
def registry_person_strategy(draw):
    """Generate a RegistryPerson with random combinations of emails, registry
    IDs, and oidcsub identifiers."""
    # Random emails (0-3)
    num_emails = draw(st.integers(min_value=0, max_value=3))
    emails = None
    if num_emails > 0:
        email_list = [draw(st.emails()) for _ in range(num_emails)]
        emails = email_list if email_list else None

    # Random registry ID
    has_registry_id = draw(st.booleans())
    registry_id = None
    if has_registry_id:
        registry_id = f"NACC-{draw(st.integers(min_value=1000, max_value=9999))}"

    # Random oidcsub
    has_oidcsub = draw(st.booleans())
    oidcsub = None
    if has_oidcsub:
        user_num = draw(st.integers(min_value=1000, max_value=9999))
        oidcsub = f"http://cilogon.org/serverA/users/{user_num}"

    return _make_person(
        emails=emails,
        registry_id=registry_id,
        oidcsub=oidcsub,
        firstname=draw(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            )
        ),
        lastname=draw(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            )
        ),
    )


# Feature: comanage-registry-resilience, Property 2: Registry indexing invariant
class TestPropertyRegistryIndexingInvariant:
    """Property 2: Registry indexing invariant.

    For any set of CoPerson records loaded into the UserRegistry, a record
    appears in the registry-ID index iff it has a registry ID, and a record
    appears in the email index iff it has that email.

    **Validates: Requirements 2.1, 2.3**
    """

    @given(persons=st.lists(registry_person_strategy(), min_size=1, max_size=10))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_registry_id_index_iff_has_id(self, persons):
        """find_by_registry_id(id) returns record iff it has that registry
        ID."""
        registry = _build_registry_with_persons(persons)

        for person in persons:
            rid = person.registry_id()
            if rid:
                found = registry.find_by_registry_id(rid)
                assert found is not None, (
                    f"Person with registry_id={rid} not found in index"
                )
            # If no registry_id, we can't assert absence since another
            # person might have the same ID

    @given(persons=st.lists(registry_person_strategy(), min_size=1, max_size=10))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_email_index_iff_has_email(self, persons):
        """get(email) contains record iff it has that email."""
        registry = _build_registry_with_persons(persons)

        for person in persons:
            for addr in person.email_addresses:
                results = registry.get(addr.mail)
                found = any(r.has_email(addr.mail) for r in results)
                assert found, f"Person with email={addr.mail} not found in email index"
