"""Unit tests and property tests for domain configuration models."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from users.domain_config import (
    AffiliatedDomainGroup,
    DomainRelationshipConfig,
    IdPDomainConfig,
    InstitutionalIdPMapping,
    ParentChildMapping,
    canonicalize_domain,
    normalize_person_name,
)

# --- Unit tests for canonicalize_domain ---


class TestCanonicalizeDomain:
    """Tests for canonicalize_domain validator."""

    def test_lowercase(self):
        assert canonicalize_domain("Med.Umich.EDU") == "med.umich.edu"

    def test_strip_whitespace(self):
        assert canonicalize_domain("  umich.edu  ") == "umich.edu"

    def test_remove_trailing_dots(self):
        assert canonicalize_domain("umich.edu.") == "umich.edu"

    def test_combined(self):
        assert canonicalize_domain("  Med.Umich.EDU.  ") == "med.umich.edu"

    def test_already_canonical(self):
        assert canonicalize_domain("umich.edu") == "umich.edu"


# --- Unit tests for ParentChildMapping ---


class TestParentChildMapping:
    """Tests for ParentChildMapping model."""

    def test_basic_creation(self):
        mapping = ParentChildMapping(child="med.umich.edu", parent="umich.edu")
        assert mapping.child == "med.umich.edu"
        assert mapping.parent == "umich.edu"

    def test_canonicalizes_domains(self):
        mapping = ParentChildMapping(child="Med.Umich.EDU", parent="UMICH.EDU")
        assert mapping.child == "med.umich.edu"
        assert mapping.parent == "umich.edu"


# --- Unit tests for AffiliatedDomainGroup ---


class TestAffiliatedDomainGroup:
    """Tests for AffiliatedDomainGroup model."""

    def test_valid_group(self):
        group = AffiliatedDomainGroup(name="pitt", domains=["pitt.edu", "upmc.edu"])
        assert group.name == "pitt"
        assert group.domains == ["pitt.edu", "upmc.edu"]

    def test_rejects_single_domain(self):
        with pytest.raises(ValidationError, match="at least 2 domains"):
            AffiliatedDomainGroup(name="solo", domains=["only.edu"])

    def test_rejects_empty_domains(self):
        with pytest.raises(ValidationError, match="at least 2 domains"):
            AffiliatedDomainGroup(name="empty", domains=[])

    def test_canonicalizes_domains(self):
        group = AffiliatedDomainGroup(name="pitt", domains=["PITT.EDU", "UPMC.EDU"])
        assert group.domains == ["pitt.edu", "upmc.edu"]


# --- Unit tests for DomainRelationshipConfig ---


class TestDomainRelationshipConfig:
    """Tests for DomainRelationshipConfig model."""

    @pytest.fixture
    def config(self):
        return DomainRelationshipConfig(
            parent_child=[
                ParentChildMapping(child="med.umich.edu", parent="umich.edu"),
                ParentChildMapping(child="health.ucdavis.edu", parent="ucdavis.edu"),
                ParentChildMapping(child="jh.edu", parent="jhu.edu"),
                ParentChildMapping(child="jhmi.edu", parent="jhu.edu"),
            ],
            affiliated_groups=[
                AffiliatedDomainGroup(name="pitt", domains=["pitt.edu", "upmc.edu"]),
            ],
        )

    def test_resolve_parent_explicit_mapping(self, config):
        assert config.resolve_parent("med.umich.edu") == "umich.edu"

    def test_resolve_parent_default_extraction(self, config):
        # Not in explicit mappings, falls back to last two segments
        assert config.resolve_parent("foo.bar.baz.edu") == "baz.edu"

    def test_resolve_parent_two_segment_domain(self, config):
        assert config.resolve_parent("umich.edu") == "umich.edu"

    def test_resolve_parent_canonicalizes_input(self, config):
        assert config.resolve_parent("Med.Umich.EDU") == "umich.edu"

    def test_resolve_parent_non_standard_mapping(self, config):
        # jh.edu -> jhu.edu (not a subdomain relationship)
        assert config.resolve_parent("jh.edu") == "jhu.edu"

    def test_get_domain_group_with_parent_child(self, config):
        group = config.get_domain_group("med.umich.edu")
        assert "med.umich.edu" in group
        assert "umich.edu" in group

    def test_get_domain_group_with_siblings(self, config):
        group = config.get_domain_group("jh.edu")
        assert "jh.edu" in group
        assert "jhu.edu" in group
        assert "jhmi.edu" in group

    def test_get_domain_group_with_affiliated(self, config):
        group = config.get_domain_group("pitt.edu")
        assert "pitt.edu" in group
        assert "upmc.edu" in group

    def test_get_domain_group_self_included(self, config):
        group = config.get_domain_group("unknown.edu")
        assert "unknown.edu" in group

    def test_empty_config(self):
        config = DomainRelationshipConfig()
        assert config.resolve_parent("foo.bar.edu") == "bar.edu"
        group = config.get_domain_group("foo.edu")
        assert group == {"foo.edu"}

    def test_validate_no_contradictions_rejects_duplicate(self):
        with pytest.raises(
            ValidationError, match="appears in multiple affiliated groups"
        ):
            DomainRelationshipConfig(
                affiliated_groups=[
                    AffiliatedDomainGroup(name="group1", domains=["a.edu", "b.edu"]),
                    AffiliatedDomainGroup(name="group2", domains=["b.edu", "c.edu"]),
                ]
            )


# --- Unit tests for IdPDomainConfig ---


class TestIdPDomainConfig:
    """Tests for IdPDomainConfig model."""

    @pytest.fixture
    def domain_config(self):
        return DomainRelationshipConfig(
            parent_child=[
                ParentChildMapping(child="med.umich.edu", parent="umich.edu"),
            ],
        )

    @pytest.fixture
    def idp_config(self):
        return IdPDomainConfig(
            institutional_idp=[
                InstitutionalIdPMapping(
                    domain="umich.edu", idp_name="University of Michigan"
                ),
                InstitutionalIdPMapping(
                    domain="columbia.edu", idp_name="Columbia University"
                ),
            ],
            fallback_domains=["advocatehealth.org", "vumc.org"],
            fallback_idp="ORCID",
        )

    def test_get_expected_idp_direct(self, idp_config, domain_config):
        assert (
            idp_config.get_expected_idp("umich.edu", domain_config)
            == "University of Michigan"
        )

    def test_get_expected_idp_subdomain_resolution(self, idp_config, domain_config):
        # med.umich.edu resolves to umich.edu via parent_child
        assert (
            idp_config.get_expected_idp("med.umich.edu", domain_config)
            == "University of Michigan"
        )

    def test_get_expected_idp_unknown_domain(self, idp_config, domain_config):
        assert idp_config.get_expected_idp("unknown.edu", domain_config) is None

    def test_is_fallback_domain_direct(self, idp_config, domain_config):
        assert idp_config.is_fallback_domain("advocatehealth.org", domain_config)

    def test_is_fallback_domain_not_fallback(self, idp_config, domain_config):
        assert not idp_config.is_fallback_domain("umich.edu", domain_config)

    def test_is_fallback_domain_unknown(self, idp_config, domain_config):
        assert not idp_config.is_fallback_domain("unknown.edu", domain_config)

    def test_validate_no_overlap_rejects(self):
        with pytest.raises(
            ValidationError,
            match="domains appear in both institutional_idp and fallback_domains",
        ):
            IdPDomainConfig(
                institutional_idp=[
                    InstitutionalIdPMapping(domain="umich.edu", idp_name="UMich"),
                ],
                fallback_domains=["umich.edu"],
            )

    def test_default_fallback_idp(self):
        config = IdPDomainConfig()
        assert config.fallback_idp == "ORCID"

    def test_custom_fallback_idp(self):
        config = IdPDomainConfig(fallback_idp="Custom IdP")
        assert config.fallback_idp == "Custom IdP"


# --- Unit tests for default_name_normalizer ---


class TestDefaultNameNormalizer:
    """Tests for default_name_normalizer function."""

    def test_lowercase(self):
        assert normalize_person_name("John Doe") == "john doe"

    def test_strip(self):
        assert normalize_person_name("  john doe  ") == "john doe"

    def test_collapse_whitespace(self):
        assert normalize_person_name("john   doe") == "john doe"

    def test_combined(self):
        assert normalize_person_name("  John   DOE  ") == "john doe"

    def test_tabs_and_newlines(self):
        assert normalize_person_name("john\t\ndoe") == "john doe"

    def test_empty_string(self):
        assert normalize_person_name("") == ""

    def test_single_name(self):
        assert normalize_person_name("John") == "john"


# --- Property-based tests ---


# Hypothesis strategies for domain config models


@st.composite
def domain_label_strategy(draw):
    """Generate a valid domain label (no dots, lowercase alpha + digits)."""
    return draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=["Ll"], whitelist_characters="0123456789"
            ),
            min_size=2,
            max_size=10,
        )
    )


@st.composite
def domain_strategy(draw, min_segments=2, max_segments=5):
    """Generate a domain string with 2-5 segments."""
    num_segments = draw(st.integers(min_value=min_segments, max_value=max_segments))
    segments = [draw(domain_label_strategy()) for _ in range(num_segments)]
    return ".".join(segments)


@st.composite
def parent_child_mapping_strategy(draw):
    """Generate a valid ParentChildMapping."""
    parent = draw(domain_strategy(min_segments=2, max_segments=2))
    child_prefix = draw(domain_label_strategy())
    child = f"{child_prefix}.{parent}"
    return ParentChildMapping(child=child, parent=parent)


@st.composite
def affiliated_group_strategy(draw):
    """Generate a valid AffiliatedDomainGroup with unique domains."""
    name = draw(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=["Ll"]),
        )
    )
    domains = draw(
        st.lists(
            domain_strategy(min_segments=2, max_segments=2),
            min_size=2,
            max_size=4,
            unique=True,
        )
    )
    return AffiliatedDomainGroup(name=name, domains=domains)


@st.composite
def domain_relationship_config_strategy(draw):
    """Generate a valid DomainRelationshipConfig."""
    num_mappings = draw(st.integers(min_value=0, max_value=3))
    mappings = [draw(parent_child_mapping_strategy()) for _ in range(num_mappings)]

    # For affiliated groups, ensure no domain overlap between groups
    num_groups = draw(st.integers(min_value=0, max_value=2))
    groups = []
    used_domains: set[str] = set()
    for _ in range(num_groups):
        group = draw(affiliated_group_strategy())
        # Skip if any domain overlaps with already-used domains
        group_domains = set(group.domains)
        if group_domains & used_domains:
            continue
        used_domains.update(group_domains)
        groups.append(group)

    return DomainRelationshipConfig(parent_child=mappings, affiliated_groups=groups)


@st.composite
def idp_domain_config_strategy(draw):
    """Generate a valid IdPDomainConfig with no overlap."""
    num_institutional = draw(st.integers(min_value=0, max_value=3))
    institutional = []
    used_domains: set[str] = set()
    for _ in range(num_institutional):
        domain = draw(domain_strategy(min_segments=2, max_segments=2))
        if domain not in used_domains:
            used_domains.add(domain)
            idp_name = draw(
                st.text(
                    min_size=1,
                    max_size=20,
                    alphabet=st.characters(whitelist_categories=["Lu", "Ll", "Zs"]),
                )
            )
            institutional.append(
                InstitutionalIdPMapping(domain=domain, idp_name=idp_name)
            )

    num_fallback = draw(st.integers(min_value=0, max_value=3))
    fallback = []
    for _ in range(num_fallback):
        domain = draw(domain_strategy(min_segments=2, max_segments=2))
        if domain not in used_domains:
            used_domains.add(domain)
            fallback.append(domain)

    return IdPDomainConfig(
        institutional_idp=institutional,
        fallback_domains=fallback,
    )


# Feature: comanage-registry-resilience
# Property 9: Configuration round-trip and canonicalization
class TestPropertyConfigRoundTrip:
    """Property 9: Configuration round-trip and canonicalization.

    **Validates: Requirements 9.1**
    """

    @given(config=domain_relationship_config_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_domain_relationship_config_round_trip(self, config):
        """Serialize and deserialize DomainRelationshipConfig, assert
        equivalence."""
        data = config.model_dump()
        restored = DomainRelationshipConfig.model_validate(data)
        assert restored.parent_child == config.parent_child
        assert restored.affiliated_groups == config.affiliated_groups

    @given(config=idp_domain_config_strategy())
    @settings(max_examples=100)
    def test_idp_domain_config_round_trip(self, config):
        """Serialize and deserialize IdPDomainConfig, assert equivalence."""
        data = config.model_dump()
        restored = IdPDomainConfig.model_validate(data)
        assert restored.institutional_idp == config.institutional_idp
        assert restored.fallback_domains == config.fallback_domains
        assert restored.fallback_idp == config.fallback_idp

    @given(
        raw_domain=domain_strategy(min_segments=2, max_segments=4).map(
            lambda d: d.upper() + ". "
        )
    )
    @settings(max_examples=100)
    def test_canonicalization_idempotent(self, raw_domain):
        """Canonicalizing a domain twice yields the same result."""
        once = canonicalize_domain(raw_domain)
        twice = canonicalize_domain(once)
        assert once == twice


# Feature: comanage-registry-resilience, Property 10: Default domain resolution
class TestPropertyDefaultDomainResolution:
    """Property 10: Default domain resolution.

    **Validates: Requirements 9.5**
    """

    @given(domain=domain_strategy(min_segments=3, max_segments=5))
    @settings(max_examples=100)
    def test_default_resolution_returns_last_two_segments(self, domain):
        """For domains not in explicit mappings, resolve_parent returns last
        two segments."""
        config = DomainRelationshipConfig()
        parent = config.resolve_parent(domain)
        parts = domain.lower().strip().rstrip(".").split(".")
        expected = ".".join(parts[-2:])
        assert parent == expected

    @given(domain=domain_strategy(min_segments=2, max_segments=2))
    @settings(max_examples=100)
    def test_two_segment_domain_returns_self(self, domain):
        """For two-segment domains, resolve_parent returns the domain
        itself."""
        config = DomainRelationshipConfig()
        parent = config.resolve_parent(domain)
        assert parent == canonicalize_domain(domain)


# Feature: comanage-registry-resilience
# Property 11: Configuration validation rejects contradictions
class TestPropertyConfigValidationRejectsContradictions:
    """Property 11: Configuration validation rejects contradictions.

    **Validates: Requirements 9.6**
    """

    @given(
        domain=domain_strategy(min_segments=2, max_segments=2),
        idp_name=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=["Lu", "Ll"]),
        ),
    )
    @settings(max_examples=100)
    def test_idp_config_rejects_overlap(self, domain, idp_name):
        """IdPDomainConfig rejects domain in both institutional_idp and
        fallback_domains."""
        with pytest.raises(ValidationError):
            IdPDomainConfig(
                institutional_idp=[
                    InstitutionalIdPMapping(domain=domain, idp_name=idp_name)
                ],
                fallback_domains=[domain],
            )

    @given(
        domain=domain_strategy(min_segments=2, max_segments=2),
    )
    @settings(max_examples=100)
    def test_domain_relationship_rejects_multi_group(self, domain):
        """DomainRelationshipConfig rejects domain in multiple affiliated
        groups."""
        other1 = domain + "x"  # ensure different
        other2 = domain + "y"
        with pytest.raises(ValidationError):
            DomainRelationshipConfig(
                affiliated_groups=[
                    AffiliatedDomainGroup(name="group1", domains=[domain, other1]),
                    AffiliatedDomainGroup(name="group2", domains=[domain, other2]),
                ]
            )
