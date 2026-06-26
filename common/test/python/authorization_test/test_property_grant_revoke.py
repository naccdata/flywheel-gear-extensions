"""Property-based tests for AuthorizationClient grant and revoke methods.

Feature: authorization-client-library
Properties tested: 1, 3, 4, 6
"""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import UnexpectedError, ValidationError
from authorization.models import GrantResult, RevokeResult
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


# --- Property 1: Request construction correctness ---


class TestProperty1RequestConstruction:
    """Property 1: Request construction correctness.

    For any valid grant/revoke operation with any valid combination of
    parameters, the client SHALL construct an HTTP request with the
    correct method, path, and JSON body containing all provided fields.

    **Validates: Requirements 2.1, 3.1**
    """

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
    )
    def test_grant_request_construction(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> None:
        """Grant constructs POST /grants with correct JSON body.

        **Validates: Requirements 2.1**
        """
        # Build a success response matching the request
        response_body = json.dumps(
            {
                "userId": user_id,
                "relation": relation,
                "type": resource_type,
                "resourceId": resource_id,
            }
        ).encode()
        transport = CapturingTransport(
            MockResponse(status_code=201, body=response_body)
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.grant(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        # Correct HTTP method and path
        assert method == "POST"
        assert path == "/grants"
        assert query_params is None

        # Body contains all fields with correct aliases
        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == user_id
        assert request_data["relation"] == relation
        assert request_data["type"] == resource_type
        assert request_data["resourceId"] == resource_id

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
    )
    def test_revoke_request_construction(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> None:
        """Revoke constructs DELETE /grants with correct JSON body.

        **Validates: Requirements 3.1**
        """
        # Build a success response matching the request
        response_body = json.dumps(
            {
                "userId": user_id,
                "relation": relation,
                "type": resource_type,
                "resourceId": resource_id,
            }
        ).encode()
        transport = CapturingTransport(
            MockResponse(status_code=200, body=response_body)
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.revoke(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        # Correct HTTP method and path
        assert method == "DELETE"
        assert path == "/grants"
        assert query_params is None

        # Body contains all fields with correct aliases
        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == user_id
        assert request_data["relation"] == relation
        assert request_data["type"] == resource_type
        assert request_data["resourceId"] == resource_id


# --- Property 3: Idempotent status codes yield success ---


class TestProperty3IdempotentSuccess:
    """Property 3: Idempotent status codes yield success.

    For any grant request that receives HTTP 409, or any revoke request
    that receives HTTP 404, the client SHALL return a success result
    (not raise an exception).

    **Validates: Requirements 2.3, 3.3**
    """

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
    )
    def test_grant_409_returns_success(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> None:
        """Grant with 409 response returns GrantResult without raising.

        **Validates: Requirements 2.3**
        """
        transport = CapturingTransport(MockResponse(status_code=409, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        # Should return a GrantResult, not raise
        assert isinstance(result, GrantResult)
        assert result.user_id == user_id
        assert result.relation == relation
        assert result.type == resource_type
        assert result.resource_id == resource_id

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
    )
    def test_revoke_404_returns_success(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> None:
        """Revoke with 404 response returns RevokeResult without raising.

        **Validates: Requirements 3.3**
        """
        transport = CapturingTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        # Should return a RevokeResult, not raise
        assert isinstance(result, RevokeResult)
        assert result.user_id == user_id
        assert result.relation == relation
        assert result.type == resource_type
        assert result.resource_id == resource_id


# --- Property 4: Validation errors propagate message ---


class TestProperty4ValidationErrors:
    """Property 4: Validation errors propagate message.

    For any API response with HTTP 400 containing an error message, the
    client SHALL raise a ValidationError whose message matches the API
    error message.

    **Validates: Requirements 2.4, 3.4**
    """

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
        api_message=error_messages,
    )
    def test_grant_400_raises_validation_error_with_message(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
        api_message: str,
    ) -> None:
        """Grant with 400 raises ValidationError containing API message.

        **Validates: Requirements 2.4**
        """
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": api_message,
            }
        ).encode()
        transport = CapturingTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.grant(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            )

        assert exc_info.value.message == api_message

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
        api_message=error_messages,
    )
    def test_revoke_400_raises_validation_error_with_message(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
        api_message: str,
    ) -> None:
        """Revoke with 400 raises ValidationError containing API message.

        **Validates: Requirements 3.4**
        """
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": api_message,
            }
        ).encode()
        transport = CapturingTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.revoke(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            )

        assert exc_info.value.message == api_message


# --- Property 6: Immediate failure on non-retriable errors ---


class TestProperty6ImmediateFailure:
    """Property 6: Immediate failure on non-retriable errors.

    For any HTTP status code that is not 503 and not an idempotent
    success code (409 for grant, 404 for revoke) and not 200/201, the
    client SHALL raise an error on the first attempt without retrying.

    **Validates: Requirements 2.6, 3.6**
    """

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
        status_code=unexpected_grant_errors,
    )
    def test_grant_non_retriable_errors_fail_immediately(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
        status_code: int,
    ) -> None:
        """Grant raises UnexpectedError on first attempt for non-retriable
        codes.

        **Validates: Requirements 2.6**
        """
        error_body = json.dumps({"message": f"Error {status_code}"}).encode()
        transport = CapturingTransport(
            MockResponse(status_code=status_code, body=error_body)
        )
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.grant(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            )

        assert exc_info.value.status_code == status_code
        # Must be exactly 1 request — no retries
        assert len(transport.requests) == 1

    @settings(max_examples=100)
    @given(
        user_id=valid_user_ids,
        resource_type=valid_resource_types,
        resource_id=valid_resource_ids,
        relation=valid_relations,
        status_code=unexpected_revoke_errors,
    )
    def test_revoke_non_retriable_errors_fail_immediately(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
        status_code: int,
    ) -> None:
        """Revoke raises UnexpectedError on first attempt for non-retriable
        codes.

        **Validates: Requirements 3.6**
        """
        error_body = json.dumps({"message": f"Error {status_code}"}).encode()
        transport = CapturingTransport(
            MockResponse(status_code=status_code, body=error_body)
        )
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.revoke(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            )

        assert exc_info.value.status_code == status_code
        # Must be exactly 1 request — no retries
        assert len(transport.requests) == 1
