"""Property-based tests for response model round-trip and parse errors.

Feature: authorization-client-library
Properties tested: 2, 10
"""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ParseError
from authorization.models import (
    BatchError,
    BatchOperation,
    BatchResult,
    GrantResult,
    HealthResult,
    InheritanceSource,
    ParentRelationship,
    PermissionEntry,
    ResourceObject,
    ResourceParents,
    RevokeResult,
    UserPermissions,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from .conftest import CapturingTransport, MockResponse, no_sleep

# --- Strategies ---

# Non-empty alphanumeric strings for IDs and fields
simple_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=30,
)

# Resource types from the authorization model
resource_types = st.sampled_from(
    ["study", "research_center", "community", "data_pipeline", "dashboard", "page"]
)

# Relations
relations = st.sampled_from(
    ["member", "admin", "viewer", "submitter", "auditor", "editor"]
)

# Access types
access_types = st.sampled_from(["direct", "inherited", "both"])

# Health statuses
health_statuses = st.sampled_from(["healthy", "degraded", "unhealthy"])

# Authorization engine statuses
engine_statuses = st.sampled_from(["connected", "unreachable"])

# Error codes for batch errors
error_codes = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
    min_size=1,
    max_size=20,
)

# Error messages
error_messages = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:._-"
    ),
    min_size=1,
    max_size=80,
)


# --- Composite strategies for response models ---


@st.composite
def resource_objects(draw: st.DrawFn) -> ResourceObject:
    """Generate arbitrary valid ``ResourceObject`` instances.

    Picks a resource type and a parent-field combination that is
    permitted for that type, so construction always passes the per-type
    parent-field validator. Organization types carry no parents;
    resource types carry a combination drawn from the per-type table. An
    optional ``flat_id`` (the server-owned read-only handle) is included
    so round-trip coverage exercises it.
    """
    # (study_present, center_present, community_present) combinations
    # permitted per type, mirroring the production per-type table.
    allowed: dict[str, list[tuple[bool, bool, bool]]] = {
        "study": [(False, False, False)],
        "research_center": [(False, False, False)],
        "community": [(False, False, False)],
        "data_pipeline": [(True, True, False), (True, False, False)],
        "dashboard": [
            (True, True, False),
            (True, False, False),
            (False, False, True),
        ],
        "page": [
            (True, True, False),
            (True, False, False),
            (False, True, False),
            (False, False, True),
        ],
    }
    resource_type = draw(resource_types)
    study_present, center_present, community_present = draw(
        st.sampled_from(allowed[resource_type])
    )
    return ResourceObject(
        type=resource_type,
        label=draw(simple_ids),
        flat_id=draw(st.one_of(st.none(), simple_ids)),
        study=draw(simple_ids) if study_present else None,
        center=draw(simple_ids) if center_present else None,
        community=draw(simple_ids) if community_present else None,
    )


@st.composite
def grant_results(draw: st.DrawFn) -> GrantResult:
    """Generate arbitrary GrantResult instances."""
    return GrantResult(
        user_id=draw(simple_ids),
        relation=draw(relations),
        resource=draw(resource_objects()),
    )


@st.composite
def revoke_results(draw: st.DrawFn) -> RevokeResult:
    """Generate arbitrary RevokeResult instances."""
    return RevokeResult(
        user_id=draw(simple_ids),
        relation=draw(relations),
        resource=draw(resource_objects()),
    )


@st.composite
def batch_errors(draw: st.DrawFn) -> BatchError:
    """Generate arbitrary BatchError instances."""
    return BatchError(
        index=draw(st.integers(min_value=0, max_value=99)),
        error=draw(error_codes),
        message=draw(error_messages),
    )


@st.composite
def batch_results(draw: st.DrawFn) -> BatchResult:
    """Generate arbitrary BatchResult instances."""
    total = draw(st.integers(min_value=0, max_value=200))
    succeeded = draw(st.integers(min_value=0, max_value=total))
    failed = total - succeeded
    errors = draw(st.lists(batch_errors(), min_size=0, max_size=min(failed, 5)))
    return BatchResult(
        total=total,
        succeeded=succeeded,
        failed=failed,
        errors=errors,
    )


@st.composite
def inheritance_sources(draw: st.DrawFn) -> InheritanceSource:
    """Generate arbitrary InheritanceSource instances."""
    return InheritanceSource(
        parent_type=draw(resource_types),
        parent_id=draw(simple_ids),
        parent_role=draw(relations),
    )


@st.composite
def permission_entries(draw: st.DrawFn) -> PermissionEntry:
    """Generate arbitrary PermissionEntry instances."""
    access = draw(access_types)
    inherited_from = None
    if access in ("inherited", "both"):
        inherited_from = draw(inheritance_sources())
    return PermissionEntry(
        resource=draw(resource_objects()),
        relation=draw(relations),
        access=access,
        inherited_from=inherited_from,
    )


@st.composite
def user_permissions(draw: st.DrawFn) -> UserPermissions:
    """Generate arbitrary UserPermissions instances."""
    num_types = draw(st.integers(min_value=1, max_value=3))
    types = draw(
        st.lists(resource_types, min_size=num_types, max_size=num_types, unique=True)
    )
    permissions: dict[str, list[PermissionEntry]] = {}
    for t in types:
        entries = draw(st.lists(permission_entries(), min_size=1, max_size=3))
        permissions[t] = entries
    return UserPermissions(
        user_id=draw(simple_ids),
        permissions=permissions,
    )


@st.composite
def parent_relationships(draw: st.DrawFn) -> ParentRelationship:
    """Generate arbitrary ParentRelationship instances."""
    return ParentRelationship(
        structural_relation=draw(relations),
        parent_type=draw(resource_types),
        parent_id=draw(simple_ids),
    )


@st.composite
def resource_parents(draw: st.DrawFn) -> ResourceParents:
    """Generate arbitrary ResourceParents instances.

    Identity is a structured ``resource``; the legacy top-level
    ``type``/``resource_id`` fields no longer exist. The ``parents``
    relationship list is retained.
    """
    return ResourceParents(
        resource=draw(resource_objects()),
        parents=draw(st.lists(parent_relationships(), min_size=0, max_size=4)),
    )


@st.composite
def health_results(draw: st.DrawFn) -> HealthResult:
    """Generate arbitrary HealthResult instances."""
    status = draw(health_statuses)
    engine = draw(st.one_of(st.none(), engine_statuses))
    return HealthResult(
        status=status,
        authorization_engine=engine,
    )


# --- Strategies for malformed JSON ---

# Strings that are valid JSON but not conforming to any response model schema
malformed_json_bodies = st.one_of(
    # JSON arrays (not objects)
    st.just(b"[]"),
    st.just(b"[1, 2, 3]"),
    # JSON objects missing required fields
    st.just(b'{"unexpected": "field"}'),
    st.just(b'{"status": 123}'),
    # JSON primitives
    st.just(b'"just a string"'),
    st.just(b"42"),
    st.just(b"true"),
    st.just(b"null"),
)

# Bytes that are not valid JSON at all
invalid_json_bodies = st.one_of(
    st.just(b"not json at all"),
    st.just(b"<html>error</html>"),
    st.just(b"{broken json"),
    st.just(b""),
    st.binary(min_size=1, max_size=50).filter(
        lambda b: not _is_valid_json(b),
    ),
)


def _is_valid_json(data: bytes) -> bool:
    """Check if bytes are valid JSON."""
    try:
        json.loads(data)
        return True
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


# --- Property 2: Response model round-trip ---


class TestProperty2ResponseRoundTrip:
    """Property 2: Response model round-trip.

    For any valid response model instance, serializing to JSON and
    parsing back SHALL produce an equivalent model instance.

    **Validates: Requirements 9.2**
    """

    @settings(max_examples=100)
    @given(model=grant_results())
    def test_grant_result_round_trip(self, model: GrantResult) -> None:
        """GrantResult survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = GrantResult.model_validate_json(json_bytes)
        assert restored == model

    @settings(max_examples=100)
    @given(model=revoke_results())
    def test_revoke_result_round_trip(self, model: RevokeResult) -> None:
        """RevokeResult survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = RevokeResult.model_validate_json(json_bytes)
        assert restored == model

    @settings(max_examples=100)
    @given(model=batch_results())
    def test_batch_result_round_trip(self, model: BatchResult) -> None:
        """BatchResult survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = BatchResult.model_validate_json(json_bytes)
        assert restored == model

    def test_batch_result_null_errors_coerced_to_empty_list(self) -> None:
        """A null ``errors`` field parses as an empty list, not an error.

        Some API responses send ``"errors": null`` on a clean batch. The
        client must tolerate this rather than fail parsing.
        """
        json_bytes = b'{"total": 3, "succeeded": 3, "failed": 0, "errors": null}'
        restored = BatchResult.model_validate_json(json_bytes)
        assert restored.errors == []
        assert restored.total == 3
        assert restored.succeeded == 3
        assert restored.failed == 0

    def test_batch_result_missing_errors_defaults_to_empty_list(self) -> None:
        """An omitted ``errors`` field still defaults to an empty list."""
        json_bytes = b'{"total": 3, "succeeded": 3, "failed": 0}'
        restored = BatchResult.model_validate_json(json_bytes)
        assert restored.errors == []

    @settings(max_examples=100)
    @given(model=user_permissions())
    def test_user_permissions_round_trip(self, model: UserPermissions) -> None:
        """UserPermissions survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = UserPermissions.model_validate_json(json_bytes)
        assert restored == model

    @settings(max_examples=100)
    @given(model=resource_parents())
    def test_resource_parents_round_trip(self, model: ResourceParents) -> None:
        """ResourceParents survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = ResourceParents.model_validate_json(json_bytes)
        assert restored == model

    @settings(max_examples=100)
    @given(model=health_results())
    def test_health_result_round_trip(self, model: HealthResult) -> None:
        """HealthResult survives serialize-then-parse cycle."""
        json_bytes = model.model_dump_json(by_alias=True).encode()
        restored = HealthResult.model_validate_json(json_bytes)
        assert restored == model


# --- Property 10: Malformed response raises ParseError with raw content ---


class TestProperty10MalformedResponseParseError:
    """Property 10: Malformed response raises ParseError with raw content.

    For any response body that does not conform to the expected JSON
    schema, the client SHALL raise a ParseError whose raw_content
    attribute contains the original response bytes.

    **Validates: Requirements 9.3**
    """

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_grant_malformed_response_raises_parse_error(self, bad_body: bytes) -> None:
        """Grant with malformed 200 response raises ParseError with raw
        bytes."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.grant(
                user_id="user1",
                resource_type="study",
                resource_label="res1",
                relation="member",
            )

        assert exc_info.value.raw_content == bad_body

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_revoke_malformed_response_raises_parse_error(
        self, bad_body: bytes
    ) -> None:
        """Revoke with malformed 200 response raises ParseError with raw
        bytes."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.revoke(
                user_id="user1",
                resource_type="study",
                resource_label="res1",
                relation="member",
            )

        assert exc_info.value.raw_content == bad_body

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_get_user_permissions_malformed_response_raises_parse_error(
        self, bad_body: bytes
    ) -> None:
        """get_user_permissions with malformed 200 raises ParseError."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.get_user_permissions(user_id="user1", type_filter="study")

        assert exc_info.value.raw_content == bad_body

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_set_resource_parents_malformed_response_raises_parse_error(
        self, bad_body: bytes
    ) -> None:
        """set_resource_parents with malformed 200 raises ParseError."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.set_resource_parents(
                resource_type="study",
                resource_id="res1",
                parents=[],
            )

        assert exc_info.value.raw_content == bad_body

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_health_check_malformed_response_raises_parse_error(
        self, bad_body: bytes
    ) -> None:
        """health_check with malformed 200 raises ParseError."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.health_check()

        assert exc_info.value.raw_content == bad_body

    @settings(max_examples=50)
    @given(bad_body=st.one_of(malformed_json_bodies, invalid_json_bodies))
    def test_batch_malformed_response_raises_parse_error(self, bad_body: bytes) -> None:
        """batch with malformed 200 raises ParseError."""
        transport = CapturingTransport(MockResponse(status_code=200, body=bad_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.batch(
                operations=[
                    BatchOperation(
                        action="grant",
                        user_id="user1",
                        resource_type="study",
                        resource_label="res1",
                        relation="member",
                    )
                ]
            )

        assert exc_info.value.raw_content == bad_body


# NOTE: The former ``TestResourceObjectValidation`` class validated the
# legacy combined ``f"{type}:{resourceId}"`` length/whitespace rule enforced
# by ``_ResourceObjectValidatorMixin``. Under the structured-``resource``
# contract that mixin no longer governs write requests (identity is a
# structured ``ResourceObject`` with discrete fields, not a concatenated
# ``type:resourceId``), so the combined-length rule no longer applies. The
# per-type parent-field validation that replaces it is covered below by
# ``TestProperty7ParentFieldCombinations`` (Requirements 2.5-2.9), and the
# non-empty ``label`` rule by the structured-identity request property in
# ``test_property_grant_revoke.py``.


# --- Property 7: Parent-field combinations are valid per resource type ---
#
# Feature: authorization-api-structured-resource-migration
# Property 7 (design.md "Correctness Properties")

# Resource types that participate in the per-type parent-field table.
organization_types = st.sampled_from(["study", "research_center", "community"])
constrained_resource_types = st.sampled_from(["data_pipeline", "dashboard", "page"])
# A forward-compatible type absent from the per-type table and not an
# organization type: unconstrained beyond the label rule.
unconstrained_types = st.sampled_from(["gizmo", "widget", "sensor"])

# The three parent fields, each either present (a non-empty value) or absent.
parent_presence = st.tuples(
    st.booleans(),  # study present
    st.booleans(),  # center present
    st.booleans(),  # community present
)

# The permitted (study, center, community) presence combinations per type,
# mirroring the design's per-type table. Kept independent of the production
# lookup so the test pins the intended semantics rather than the code.
_ALLOWED_COMBINATIONS: dict[str, set[tuple[bool, bool, bool]]] = {
    "study": {(False, False, False)},
    "research_center": {(False, False, False)},
    "community": {(False, False, False)},
    "data_pipeline": {
        (True, True, False),
        (True, False, False),
    },
    "dashboard": {
        (True, True, False),
        (True, False, False),
        (False, False, True),
    },
    "page": {
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    },
}


def _build_resource(
    resource_type: str, presence: tuple[bool, bool, bool]
) -> "ResourceObject":
    """Construct a ResourceObject with the given parent-field presence.

    Each present parent field is populated with a distinct non-empty
    value; each absent field is left as ``None``.
    """
    study_present, center_present, community_present = presence
    return ResourceObject(
        type=resource_type,
        label="ingest-example",
        study="study-1" if study_present else None,
        center="center-1" if center_present else None,
        community="community-1" if community_present else None,
    )


class TestProperty7ParentFieldCombinations:
    """Property 7: Parent-field combinations are valid per resource type.

    For any resource type and any combination of the parent fields
    (``study``, ``center``, ``community``) present or absent,
    constructing a ``ResourceObject`` succeeds if and only if the
    combination is permitted for that type. When it is not permitted the
    validator raises an error whose message names the offending type.
    Types outside the per-type table (and not organization types) are
    unconstrained beyond the label rule.

    **Validates: Requirements 2.5, 2.6, 2.7, 2.8, 2.9**
    """

    @settings(max_examples=200)
    @given(
        resource_type=st.one_of(organization_types, constrained_resource_types),
        presence=parent_presence,
    )
    def test_construction_succeeds_iff_combination_permitted(
        self,
        resource_type: str,
        presence: tuple[bool, bool, bool],
    ) -> None:
        """Construction succeeds exactly when the combination is allowed."""
        permitted = presence in _ALLOWED_COMBINATIONS[resource_type]

        if permitted:
            resource = _build_resource(resource_type, presence)
            # The stored parent fields reflect exactly the requested
            # presence pattern.
            assert (resource.study is not None) == presence[0]
            assert (resource.center is not None) == presence[1]
            assert (resource.community is not None) == presence[2]
        else:
            with pytest.raises(ValidationError) as exc_info:
                _build_resource(resource_type, presence)
            # The rejection message names the offending resource type.
            assert resource_type in str(exc_info.value)

    @settings(max_examples=100)
    @given(
        resource_type=unconstrained_types,
        presence=parent_presence,
    )
    def test_unknown_types_are_unconstrained(
        self,
        resource_type: str,
        presence: tuple[bool, bool, bool],
    ) -> None:
        """A type outside the table accepts any parent-field combination."""
        resource = _build_resource(resource_type, presence)
        assert resource.type == resource_type
        assert (resource.study is not None) == presence[0]
        assert (resource.center is not None) == presence[1]
        assert (resource.community is not None) == presence[2]
