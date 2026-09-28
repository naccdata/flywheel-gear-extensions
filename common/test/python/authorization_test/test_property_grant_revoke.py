"""Property-based tests for AuthorizationClient grant and revoke methods.

Feature: authorization-client-library
Properties tested: 1, 3, 4, 6
"""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import UnexpectedError, ValidationError
from authorization.models import (
    BatchOperationModel,
    GrantRequest,
    GrantResult,
    PermissionCheckRequest,
    ResourceObject,
    RevokeRequest,
    RevokeResult,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from .conftest import CapturingTransport, MockResponse, no_sleep

# --- Strategies ---

# Known resource types from the authorization model
RESOURCE_TYPES = [
    "study",
    "research_center",
    "community",
    "data_pipeline",
    "dashboard",
    "page",
]

# Known relations
RELATIONS = ["member", "admin", "viewer", "submitter", "auditor", "editor"]

# Non-empty alphanumeric strings with common separators for IDs
valid_user_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789@._-"),
    min_size=1,
    max_size=50,
)

valid_resource_types = st.sampled_from(RESOURCE_TYPES)

valid_resource_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=50,
)

valid_relations = st.sampled_from(RELATIONS)

# Non-retriable, non-idempotent, non-400 errors for grant
# (400 is handled separately as ValidationError)
unexpected_grant_errors = st.sampled_from([401, 402, 403, 404, 405, 422, 429, 500, 502])

# Non-retriable, non-idempotent, non-400 errors for revoke
unexpected_revoke_errors = st.sampled_from(
    [401, 402, 403, 405, 409, 422, 429, 500, 502]
)

# Error messages for validation errors
error_messages = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:._-"
    ),
    min_size=1,
    max_size=100,
)


# --- Structured-identity call arguments ---
#
# The migrated grant/revoke signature takes a structured identity
# (resource_type, resource_label, and applicable parent fields) instead of
# a flat resource_id. This strategy produces keyword arguments carrying a
# resource type, a non-empty label, and a parent-field combination the type
# permits, so the pre-transmission ResourceObject validation always passes
# and the request reaches the transport.


@st.composite
def grant_call_kwargs(draw: st.DrawFn) -> dict:
    """Generate valid structured-identity kwargs for grant/revoke.

    Returns ``user_id``, ``resource_type``, ``resource_label``,
    ``relation`` plus whichever parent fields (``study``/``center``/
    ``community``) the chosen type permits. The parent-field
    combinations mirror the design's per-type table so construction
    never fails validation.
    """
    permitted: dict[str, list[tuple[bool, bool, bool]]] = {
        # Organization types carry no parent fields.
        "study": [(False, False, False)],
        "research_center": [(False, False, False)],
        "community": [(False, False, False)],
        "data_pipeline": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
        ],
        "dashboard": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
            (False, False, True),  # community alone
        ],
        "page": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
            (False, True, False),  # center alone
            (False, False, True),  # community alone
        ],
    }

    resource_type = draw(st.sampled_from(sorted(permitted)))
    study_present, center_present, community_present = draw(
        st.sampled_from(permitted[resource_type])
    )

    kwargs: dict = {
        "user_id": draw(valid_user_ids),
        "resource_type": resource_type,
        "resource_label": draw(valid_resource_ids),
        "relation": draw(valid_relations),
    }
    if study_present:
        kwargs["study"] = draw(valid_resource_ids)
    if center_present:
        kwargs["center"] = draw(valid_resource_ids)
    if community_present:
        kwargs["community"] = draw(valid_resource_ids)
    return kwargs


# --- Property 1: Request construction correctness ---


class TestProperty1RequestConstruction:
    """Property 1: Request construction correctness.

    For any valid grant/revoke operation with any valid combination of
    parameters, the client SHALL construct an HTTP request with the
    correct method, path, and a JSON body carrying a structured
    ``resource`` object (type + non-empty label + applicable parents) and
    no top-level ``type``/``resourceId`` and no ``flat_id``.

    **Validates: Requirements 1.1, 1.2, 1.3, 3.5**
    """

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs())
    def test_grant_request_construction(self, call_kwargs: dict) -> None:
        """Grant constructs POST /grants with a structured resource body."""
        response_body = json.dumps(
            {
                "userId": call_kwargs["user_id"],
                "relation": call_kwargs["relation"],
                "type": call_kwargs["resource_type"],
                "resourceId": call_kwargs["resource_label"],
            }
        ).encode()
        transport = CapturingTransport(
            MockResponse(status_code=201, body=response_body)
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.grant(**call_kwargs)

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        assert method == "POST"
        assert path == "/grants"
        assert query_params is None

        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == call_kwargs["user_id"]
        assert request_data["relation"] == call_kwargs["relation"]
        # No flat-shape top-level identity.
        assert "type" not in request_data
        assert "resourceId" not in request_data

        resource = request_data["resource"]
        assert resource["type"] == call_kwargs["resource_type"]
        assert resource["label"] == call_kwargs["resource_label"]
        assert len(resource["label"]) >= 1
        assert "flat_id" not in resource
        assert "flatId" not in resource
        # Applicable parent fields are carried on the resource.
        for parent in ("study", "center", "community"):
            if parent in call_kwargs:
                assert resource[parent] == call_kwargs[parent]

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs())
    def test_revoke_request_construction(self, call_kwargs: dict) -> None:
        """Revoke constructs DELETE /grants with a structured resource body."""
        response_body = json.dumps(
            {
                "userId": call_kwargs["user_id"],
                "relation": call_kwargs["relation"],
                "type": call_kwargs["resource_type"],
                "resourceId": call_kwargs["resource_label"],
            }
        ).encode()
        transport = CapturingTransport(
            MockResponse(status_code=200, body=response_body)
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.revoke(**call_kwargs)

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        assert method == "DELETE"
        assert path == "/grants"
        assert query_params is None

        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == call_kwargs["user_id"]
        assert request_data["relation"] == call_kwargs["relation"]
        assert "type" not in request_data
        assert "resourceId" not in request_data

        resource = request_data["resource"]
        assert resource["type"] == call_kwargs["resource_type"]
        assert resource["label"] == call_kwargs["resource_label"]
        assert len(resource["label"]) >= 1
        assert "flat_id" not in resource
        assert "flatId" not in resource
        for parent in ("study", "center", "community"):
            if parent in call_kwargs:
                assert resource[parent] == call_kwargs[parent]


# --- Property 3: Idempotent status codes yield success ---


class TestProperty3IdempotentSuccess:
    """Property 3: Idempotent status codes yield success.

    For any grant request that receives HTTP 409, or any revoke request
    that receives HTTP 404, the client SHALL return a success result
    (not raise an exception), synthesized from the request's structured
    resource.

    **Validates: Requirements 8.1, 8.2**
    """

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs())
    def test_grant_409_returns_success(self, call_kwargs: dict) -> None:
        """Grant with 409 response returns GrantResult without raising."""
        transport = CapturingTransport(MockResponse(status_code=409, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(**call_kwargs)

        assert isinstance(result, GrantResult)
        assert result.user_id == call_kwargs["user_id"]
        assert result.relation == call_kwargs["relation"]
        # Idempotent result carries the request's structured resource.
        assert result.resource is not None
        assert result.resource.type == call_kwargs["resource_type"]
        assert result.resource.label == call_kwargs["resource_label"]
        # No retry on an idempotent conflict.
        assert len(transport.requests) == 1

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs())
    def test_revoke_404_returns_success(self, call_kwargs: dict) -> None:
        """Revoke with 404 response returns RevokeResult without raising."""
        transport = CapturingTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(**call_kwargs)

        assert isinstance(result, RevokeResult)
        assert result.user_id == call_kwargs["user_id"]
        assert result.relation == call_kwargs["relation"]
        assert result.resource is not None
        assert result.resource.type == call_kwargs["resource_type"]
        assert result.resource.label == call_kwargs["resource_label"]
        # No retry on an idempotent not-found.
        assert len(transport.requests) == 1


# --- Property 4: Validation errors propagate message ---


class TestProperty4ValidationErrors:
    """Property 4: Validation errors propagate message.

    For any API response with HTTP 400 containing an error message, the
    client SHALL raise a ValidationError whose message matches the API
    error message.

    **Validates: Requirements 1.7**
    """

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs(), api_message=error_messages)
    def test_grant_400_raises_validation_error_with_message(
        self,
        call_kwargs: dict,
        api_message: str,
    ) -> None:
        """Grant with 400 raises ValidationError containing API message."""
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": api_message,
            }
        ).encode()
        transport = CapturingTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.grant(**call_kwargs)

        assert exc_info.value.message == api_message

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs(), api_message=error_messages)
    def test_revoke_400_raises_validation_error_with_message(
        self,
        call_kwargs: dict,
        api_message: str,
    ) -> None:
        """Revoke with 400 raises ValidationError containing API message."""
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": api_message,
            }
        ).encode()
        transport = CapturingTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.revoke(**call_kwargs)

        assert exc_info.value.message == api_message


# --- Property 6: Immediate failure on non-retriable errors ---


class TestProperty6ImmediateFailure:
    """Property 6: Immediate failure on non-retriable errors.

    For any HTTP status code that is not 503 and not an idempotent
    success code (409 for grant, 404 for revoke) and not 200/201, the
    client SHALL raise an error on the first attempt without retrying.

    **Validates: Requirements 9.3**
    """

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs(), status_code=unexpected_grant_errors)
    def test_grant_non_retriable_errors_fail_immediately(
        self,
        call_kwargs: dict,
        status_code: int,
    ) -> None:
        """Grant raises UnexpectedError on first attempt for non-retriable
        codes."""
        error_body = json.dumps({"message": f"Error {status_code}"}).encode()
        transport = CapturingTransport(
            MockResponse(status_code=status_code, body=error_body)
        )
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.grant(**call_kwargs)

        assert exc_info.value.status_code == status_code
        # Must be exactly 1 request — no retries
        assert len(transport.requests) == 1

    @settings(max_examples=100)
    @given(call_kwargs=grant_call_kwargs(), status_code=unexpected_revoke_errors)
    def test_revoke_non_retriable_errors_fail_immediately(
        self,
        call_kwargs: dict,
        status_code: int,
    ) -> None:
        """Revoke raises UnexpectedError on first attempt for non-retriable
        codes."""
        error_body = json.dumps({"message": f"Error {status_code}"}).encode()
        transport = CapturingTransport(
            MockResponse(status_code=status_code, body=error_body)
        )
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.revoke(**call_kwargs)

        assert exc_info.value.status_code == status_code
        # Must be exactly 1 request — no retries
        assert len(transport.requests) == 1


# ---------------------------------------------------------------------------
# Property 1: Requests carry structured identity and never flat identity
#
# Feature: authorization-api-structured-resource-migration
# Property 1 (design.md "Correctness Properties")
#
# For any GrantRequest, RevokeRequest, BatchOperationModel, or
# PermissionCheckRequest built from a valid Structured Identity, the serialized
# request payload contains a `resource` object whose `label` has at least one
# character, and contains no flat_id key, no top-level `type` key, and no
# top-level `resourceId` key.
# ---------------------------------------------------------------------------

# Non-empty labels (a `label` must contain at least one character).
valid_labels = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=50,
)

# Non-empty parent-reference values (center / study / community ids).
valid_parent_values = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=40,
)

# Arbitrary server-owned flat_id handles. These may be set on a parsed
# response resource; a request must never emit them regardless.
valid_flat_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_:"),
    min_size=1,
    max_size=60,
)


@st.composite
def structured_identities(draw: st.DrawFn) -> ResourceObject:
    """Generate a ``ResourceObject`` from a valid Structured Identity.

    Each generated resource carries a resource type, a non-empty label,
    and a parent-field combination permitted for that type (per the
    design's per-type table), so ``ResourceObject`` construction always
    succeeds. To exercise the flat_id-exclusion guarantee, roughly half
    the resources are also given an arbitrary server-owned ``flat_id``
    (as a response resource would carry); a request must never emit it.
    """
    # (resource_type, [permitted (study, center, community) presence tuples])
    permitted: dict[str, list[tuple[bool, bool, bool]]] = {
        # Organization types carry no parent fields.
        "study": [(False, False, False)],
        "research_center": [(False, False, False)],
        "community": [(False, False, False)],
        "data_pipeline": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
        ],
        "dashboard": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
            (False, False, True),  # community alone
        ],
        "page": [
            (True, True, False),  # study + center
            (True, False, False),  # study alone
            (False, True, False),  # center alone
            (False, False, True),  # community alone
        ],
    }

    resource_type = draw(st.sampled_from(sorted(permitted)))
    study_present, center_present, community_present = draw(
        st.sampled_from(permitted[resource_type])
    )

    flat_id = draw(st.one_of(st.none(), valid_flat_ids))

    return ResourceObject(
        type=resource_type,
        label=draw(valid_labels),
        flat_id=flat_id,
        study=draw(valid_parent_values) if study_present else None,
        center=draw(valid_parent_values) if center_present else None,
        community=draw(valid_parent_values) if community_present else None,
    )


def _assert_no_flat_id(node: object) -> None:
    """Recursively assert no ``flat_id``/``flatId`` key appears anywhere."""
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in ("flat_id", "flatId"), (
                f"forbidden flat-identity key {key!r} present in payload"
            )
            _assert_no_flat_id(value)
    elif isinstance(node, list):
        for item in node:
            _assert_no_flat_id(item)


def _assert_structured_resource_payload(payload: dict) -> None:
    """Assert a serialized write-request payload carries structured identity.

    The payload must contain a ``resource`` object with a non-empty
    ``label`` and a ``type``; it must not carry a top-level ``type`` or
    ``resourceId`` key, and no ``flat_id`` key anywhere.
    """
    # A structured resource object is present.
    assert "resource" in payload
    resource = payload["resource"]
    assert isinstance(resource, dict)

    # The resource carries a non-empty label and its type.
    assert "label" in resource
    assert isinstance(resource["label"], str)
    assert len(resource["label"]) >= 1
    assert "type" in resource

    # No flat identity anywhere in the payload.
    _assert_no_flat_id(payload)

    # No top-level flat-shape identity fields.
    assert "type" not in payload, "top-level `type` must not appear in the payload"
    assert "resourceId" not in payload, (
        "top-level `resourceId` must not appear in the payload"
    )


class TestMigrationProperty1StructuredIdentity:
    """Property 1: Requests carry structured identity and never flat identity.

    For any ``GrantRequest``, ``RevokeRequest``, ``BatchOperationModel``,
    or ``PermissionCheckRequest`` built from a valid Structured Identity,
    the serialized payload carries a ``resource`` object with a non-empty
    ``label`` and never a ``flat_id``, a top-level ``type``, or a
    top-level ``resourceId``.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.3, 2.4**
    """

    @settings(max_examples=200)
    @given(
        user_id=valid_user_ids,
        relation=valid_relations,
        resource=structured_identities(),
    )
    def test_grant_request_carries_structured_identity(
        self,
        user_id: str,
        relation: str,
        resource: ResourceObject,
    ) -> None:
        """A serialized ``GrantRequest`` carries only structured identity."""
        request = GrantRequest(user_id=user_id, relation=relation, resource=resource)
        payload = json.loads(request.request_body())

        assert payload["userId"] == user_id
        assert payload["relation"] == relation
        _assert_structured_resource_payload(payload)

    @settings(max_examples=200)
    @given(
        user_id=valid_user_ids,
        relation=valid_relations,
        resource=structured_identities(),
    )
    def test_revoke_request_carries_structured_identity(
        self,
        user_id: str,
        relation: str,
        resource: ResourceObject,
    ) -> None:
        """A serialized ``RevokeRequest`` carries only structured identity."""
        request = RevokeRequest(user_id=user_id, relation=relation, resource=resource)
        payload = json.loads(request.request_body())

        assert payload["userId"] == user_id
        assert payload["relation"] == relation
        _assert_structured_resource_payload(payload)

    @settings(max_examples=200)
    @given(
        user_id=valid_user_ids,
        relation=valid_relations,
        resource=structured_identities(),
    )
    def test_permission_check_request_carries_structured_identity(
        self,
        user_id: str,
        relation: str,
        resource: ResourceObject,
    ) -> None:
        """A serialized ``PermissionCheckRequest`` carries structured
        identity."""
        request = PermissionCheckRequest(
            user_id=user_id, relation=relation, resource=resource
        )
        payload = json.loads(request.request_body())

        assert payload["userId"] == user_id
        assert payload["relation"] == relation
        _assert_structured_resource_payload(payload)

    @settings(max_examples=200)
    @given(
        action=st.sampled_from(["grant", "revoke"]),
        user_id=valid_user_ids,
        relation=valid_relations,
        resource=structured_identities(),
    )
    def test_batch_operation_model_carries_structured_identity(
        self,
        action: str,
        user_id: str,
        relation: str,
        resource: ResourceObject,
    ) -> None:
        """A serialized ``BatchOperationModel`` carries structured identity.

        ``BatchOperationModel`` has no ``request_body()``; it is
        serialized via the same ``resource.request_dump()`` path the
        batch request uses, so the assertion targets that structured
        payload.
        """
        operation = BatchOperationModel(
            action=action,
            user_id=user_id,
            relation=relation,
            resource=resource,
        )
        payload = {
            "action": operation.action,
            "userId": operation.user_id,
            "relation": operation.relation,
            "resource": operation.resource.request_dump(),
        }

        assert payload["userId"] == user_id
        assert payload["relation"] == relation
        assert payload["action"] == action
        _assert_structured_resource_payload(payload)
