"""Domain configuration models for COManage registry resilience.

Provides Pydantic models for domain relationship configuration, IdP
domain mapping, and name normalization. All domain strings are
canonicalized on load (lowercased, stripped, trailing dots removed).
"""

from typing import Annotated, Optional, Self

from pydantic import AfterValidator, BaseModel, field_validator, model_validator


def canonicalize_domain(value: str) -> str:
    """Lowercase, strip whitespace, remove trailing dots."""
    return value.lower().strip().rstrip(".")


Domain = Annotated[str, AfterValidator(canonicalize_domain)]


class ParentChildMapping(BaseModel):
    """A single parent-child domain relationship."""

    child: Domain
    parent: Domain


class AffiliatedDomainGroup(BaseModel):
    """A group of affiliated domains that share users."""

    name: str
    domains: list[Domain]

    @field_validator("domains")
    @classmethod
    def at_least_two_domains(cls, v: list[str]) -> list[str]:
        """Affiliated group must contain at least 2 domains."""
        if len(v) < 2:
            raise ValueError("affiliated group must contain at least 2 domains")
        return v


class DomainRelationshipConfig(BaseModel):
    """Configuration for domain parent-child and affiliation relationships.

    Loaded from YAML following the AuthMap pattern. All domain strings
    are canonicalized (lowercased, stripped) on load.
    """

    parent_child: list[ParentChildMapping] = []
    affiliated_groups: list[AffiliatedDomainGroup] = []

    # Internal lookup indexes built by model_validator
    _parent_lookup: dict[str, str] = {}
    _children_lookup: dict[str, list[str]] = {}
    _affiliated_lookup: dict[str, str] = {}

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def validate_no_contradictions(self) -> Self:
        """Ensure no domain appears in multiple affiliated groups."""
        seen_domains: dict[str, str] = {}
        for group in self.affiliated_groups:
            for domain in group.domains:
                if domain in seen_domains:
                    raise ValueError(
                        f"domain '{domain}' appears in multiple affiliated groups: "
                        f"'{seen_domains[domain]}' and '{group.name}'"
                    )
                seen_domains[domain] = group.name
        return self

    @model_validator(mode="after")
    def build_lookup_indexes(self) -> Self:
        """Build internal dicts for efficient lookup.

        Called once on load.
        """
        parent_lookup: dict[str, str] = {}
        children_lookup: dict[str, list[str]] = {}
        for mapping in self.parent_child:
            parent_lookup[mapping.child] = mapping.parent
            children_lookup.setdefault(mapping.parent, []).append(mapping.child)

        affiliated_lookup: dict[str, str] = {}
        for group in self.affiliated_groups:
            for domain in group.domains:
                affiliated_lookup[domain] = group.name

        self._parent_lookup = parent_lookup
        self._children_lookup = children_lookup
        self._affiliated_lookup = affiliated_lookup
        return self

    def resolve_parent(self, domain: str) -> str:
        """Resolve a domain to its parent domain.

        1. Canonicalize the input domain
        2. Check explicit parent_child mappings
        3. Fall back to default extraction (last two segments)
        """
        canonical = canonicalize_domain(domain)

        # Check explicit mapping
        if canonical in self._parent_lookup:
            return self._parent_lookup[canonical]

        # Default: last two segments
        parts = canonical.split(".")
        if len(parts) <= 2:
            return canonical
        return ".".join(parts[-2:])

    def get_domain_group(self, domain: str) -> set[str]:
        """Get all domains related to the given domain.

        Returns the union of:
        - The domain itself (canonicalized)
        - Its parent domain (and siblings sharing that parent)
        - Any affiliated domains from affiliated_groups
        """
        canonical = canonicalize_domain(domain)
        result: set[str] = {canonical}

        # Add parent and siblings
        parent = self.resolve_parent(canonical)
        result.add(parent)

        # Add all children of the parent (siblings)
        if parent in self._children_lookup:
            result.update(self._children_lookup[parent])

        # Add affiliated domains
        group_name: Optional[str] = None
        # Check if canonical domain or its parent is in an affiliated group
        for d in list(result):
            if d in self._affiliated_lookup:
                group_name = self._affiliated_lookup[d]
                break

        if group_name:
            for group in self.affiliated_groups:
                if group.name == group_name:
                    result.update(group.domains)
                    break

        return result


class InstitutionalIdPMapping(BaseModel):
    """Maps an email domain to its expected institutional IdP."""

    domain: Domain
    idp_name: str


class IdPDomainConfig(BaseModel):
    """Configuration mapping email domains to expected IdPs.

    Loaded from YAML following the AuthMap pattern. All domain strings
    are canonicalized (lowercased, stripped) on load.
    """

    institutional_idp: list[InstitutionalIdPMapping] = []
    fallback_domains: list[Domain] = []
    fallback_idp: str = "ORCID"

    # Internal lookup indexes built by model_validator
    _idp_lookup: dict[str, str] = {}
    _fallback_set: set[str] = set()

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def validate_no_overlap(self) -> Self:
        """Ensure no domain is listed in both institutional_idp and
        fallback_domains."""
        institutional_domains = {m.domain for m in self.institutional_idp}
        fallback_set = set(self.fallback_domains)
        overlap = institutional_domains & fallback_set
        if overlap:
            raise ValueError(
                f"domains appear in both institutional_idp and "
                f"fallback_domains: {overlap}"
            )
        return self

    @model_validator(mode="after")
    def build_lookup_indexes(self) -> Self:
        """Build internal dicts for efficient lookup.

        Called once on load.
        """
        self._idp_lookup = {m.domain: m.idp_name for m in self.institutional_idp}
        self._fallback_set = set(self.fallback_domains)
        return self

    def get_expected_idp(
        self, domain: str, domain_config: DomainRelationshipConfig
    ) -> Optional[str]:
        """Get the expected IdP for an email domain.

        Canonicalizes input, resolves subdomains via
        DomainRelationshipConfig. Returns None if domain is not mapped.
        """
        canonical = canonicalize_domain(domain)

        # Direct lookup
        if canonical in self._idp_lookup:
            return self._idp_lookup[canonical]

        # Resolve parent and try again
        parent = domain_config.resolve_parent(canonical)
        if parent in self._idp_lookup:
            return self._idp_lookup[parent]

        return None

    def is_fallback_domain(
        self, domain: str, domain_config: DomainRelationshipConfig
    ) -> bool:
        """Check if a domain is expected to use the fallback IdP.

        Canonicalizes input before lookup.
        """
        canonical = canonicalize_domain(domain)

        # Direct lookup
        if canonical in self._fallback_set:
            return True

        # Resolve parent and try again
        parent = domain_config.resolve_parent(canonical)
        return parent in self._fallback_set


def normalize_person_name(name: str) -> str:
    """Normalize a person's name for case- and whitespace-insensitive matching.

    Converts to lowercase, strips leading/trailing whitespace, and
    replaces any internal whitespace runs (spaces, tabs, newlines) with
    a single space.
    """
    return " ".join(name.lower().split())
