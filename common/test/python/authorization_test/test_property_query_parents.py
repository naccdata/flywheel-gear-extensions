"""Property-based tests for query, parents, and retry behavior.

Tests Properties 1, 5, and 6 from the design document for
get_user_permissions and set_resource_parents methods.
"""

import json
from dataclasses import dataclass, field

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ServiceUnavailableError, UnexpectedError
from authorization.models import ParentRelationshipModel
from hypothesis import given, settings
from hypothesis import strategies as st

from .conftest import MockResponse, no_sleep

# --- Strategies ---

# Valid user IDs: non-empty alphanumeric strings with common separators
user_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789._@-"),
    min_size=1,
    max_size=50,
)

# Valid resource types from the authorization model
resource_types = st.sampled_from(
    [
        "study",
        "research_center",
        "community",
        "data_pipeline",
        "dashboard",
        "page",
    ]
)

# Valid resource IDs: non-empty strings
resource_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=50,
)

# Valid structural relations for parent relationships
structural_relations = st.sampled_from(
    [
        "parent_study",
        "parent_center",
        "parent_community",
    ]
)

# Valid relations
relations = st.sampled_from(
    ["member", "admin", "viewer", "submitter", "auditor", "editor"]
)

# Optional type filter
optional_type_filter = st.one_of(st.none(), resource_types)

# Optional relation filter
optional_relation_filter = st.one_of(st.none(), relations)

# Parent relationship strategy
parent_relationships = st.builds(
    ParentRelationshipModel,
    structural_relation=structural_relations,
    parent_type=resource_types,
    parent_id=resource_ids,
)

# List of parent relationships (0-5 items)
parent_lists = st.lists(parent_relationships, min_size=0, max_size=5)

# Non-retriable, non-success HTTP status codes (not 200, 201, 503)
non_retriable_error_codes = st.sampled_from(
    [400, 401, 403, 404, 405, 409, 422, 429, 500, 502]
)

# Retry counts (1-5)
retry_counts = st.integers(min_value=1, max_value=5)

# Base backoff values
base_backoffs = st.floats(min_value=0.1, max_value=5.0)


# --- Mock Transport ---


@dataclass
class SequentialMockTransport:
    """Dataclass-based mock transport for property tests."""

    responses: list[MockResponse] = field(default_factory=list)
    requests: list[tuple[str, str, bytes | None, dict[str, str] | None]] = field(
        default_factory=list
    )
    _call_index: int = field(default=0, init=False)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        self.requests.append((method, path, body, query_params))
        response = self.responses[min(self._call_index, len(self.responses) - 1)]
        self._call_index += 1
        return response


# --- Property 1: Request construction correctness ---
# Validates: Requirements 5.1, 6.1


class TestProperty1RequestConstruction:
    """Property 1: Request construction correctness.

    For any valid operation (get_user_permissions, set_resource_parents)
    with any valid combination of parameters, the client SHALL construct
    an HTTP request with the correct method, path, and JSON body
    containing all provided fields.

    **Validates: Requirements 5.1, 6.1**
    """

    @settings(max_examples=100)
    @given(
        user_id=user_ids,
        type_filter=optional_type_filter,
        relation_filter=optional_relation_filter,
    )
    def test_get_user_permissions_request_construction(
        self,
        user_id: str,
        type_filter: str | None,
        relation_filter: str | None,
    ) -> None:
        """get_user_permissions sends GET to /users/{userId}/permissions.

        **Validates: Requirements 5.1**
        """
        response_body = json.dumps({"userId": user_id, "permissions": {}}).encode()
        transport = SequentialMockTransport(
            responses=[MockResponse(status_code=200, body=response_body)]
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.get_user_permissions(
            user_id=user_id,
            type_filter=type_filter,
            relation_filter=relation_filter,
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        # Correct HTTP method
        assert method == "GET"

        # Correct path with user_id
        assert path == f"/users/{user_id}/permissions"

        # No body for GET requests
        assert body is None

        # Query params match filters
        expected_params: dict[str, str] = {}
        if type_filter is not None:
            expected_params["type"] = type_filter
        if relation_filter is not None:
            expected_params["relation"] = relation_filter

        if expected_params:
            assert query_params == expected_params
        else:
            assert query_params is None

    @settings(max_examples=100)
    @given(
        resource_type=resource_types,
        resource_id=resource_ids,
        parents=parent_lists,
    )
    def test_set_resource_parents_request_construction(
        self,
        resource_type: str,
        resource_id: str,
        parents: list[ParentRelationshipModel],
    ) -> None:
        """set_resource_parents sends PUT to /resources/{type}/{id}/parents.

        **Validates: Requirements 6.1**
        """
        # Build a valid response body
        response_body = json.dumps(
            {
                "type": resource_type,
                "resourceId": resource_id,
                "parents": [
                    {
                        "structuralRelation": p.structural_relation,
                        "parentType": p.parent_type,
                        "parentId": p.parent_id,
                    }
                    for p in parents
                ],
            }
        ).encode()
        transport = SequentialMockTransport(
            responses=[MockResponse(status_code=200, body=response_body)]
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.set_resource_parents(
            resource_type=resource_type,
            resource_id=resource_id,
            parents=parents,
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]

        # Correct HTTP method
        assert method == "PUT"

        # Correct path with resource type and id
        assert path == f"/resources/{resource_type}/{resource_id}/parents"

        # No query params for PUT
        assert query_params is None

        # Body contains all parent relationships in camelCase
        assert body is not None
        request_data = json.loads(body)
        assert "parents" in request_data
        assert len(request_data["parents"]) == len(parents)

        for i, parent in enumerate(parents):
            sent_parent = request_data["parents"][i]
            assert sent_parent["structuralRelation"] == parent.structural_relation
            assert sent_parent["parentType"] == parent.parent_type
            assert sent_parent["parentId"] == parent.parent_id


# --- Property 5: Retry on 503 with exponential backoff ---
# Validates: Requirements 5.3, 6.4, 8.1, 8.2


class TestProperty5RetryOn503:
    """Property 5: Retry on 503 with exponential backoff.

    For any request that receives HTTP 503 responses, the client SHALL
    retry up to max_retries times with delays following the pattern
    base_backoff * 2^(attempt-1), then raise ServiceUnavailableError
    if all retries are exhausted.

    **Validates: Requirements 5.3, 6.4, 8.1, 8.2**
    """

    @settings(max_examples=100)
    @given(
        user_id=user_ids,
        max_retries=retry_counts,
        base_backoff=base_backoffs,
    )
    def test_get_user_permissions_retry_count_and_backoff(
        self,
        user_id: str,
        max_retries: int,
        base_backoff: float,
    ) -> None:
        """get_user_permissions retries max_retries times then raises.

        **Validates: Requirements 5.3, 8.1, 8.2**
        """
        # All responses are 503
        responses = [MockResponse(status_code=503, body=b"")] * (max_retries + 2)
        transport = SequentialMockTransport(responses=responses)

        sleep_calls: list[float] = []

        def tracking_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        client = AuthorizationClient(
            transport=transport,
            max_retries=max_retries,
            base_backoff=base_backoff,
            sleep=tracking_sleep,
        )

        with pytest.raises(ServiceUnavailableError):
            client.get_user_permissions(user_id=user_id)

        # Total requests: 1 initial + max_retries retries
        assert len(transport.requests) == 1 + max_retries

        # Verify sleep was called max_retries times
        assert len(sleep_calls) == max_retries

        # Verify exponential backoff pattern
        for attempt in range(max_retries):
            expected_delay = base_backoff * (2**attempt)
            assert abs(sleep_calls[attempt] - expected_delay) < 1e-9

    @settings(max_examples=100)
    @given(
        resource_type=resource_types,
        resource_id=resource_ids,
        max_retries=retry_counts,
        base_backoff=base_backoffs,
    )
    def test_set_resource_parents_retry_count_and_backoff(
        self,
        resource_type: str,
        resource_id: str,
        max_retries: int,
        base_backoff: float,
    ) -> None:
        """set_resource_parents retries max_retries times then raises.

        **Validates: Requirements 6.4, 8.1, 8.2**
        """
        # All responses are 503
        responses = [MockResponse(status_code=503, body=b"")] * (max_retries + 2)
        transport = SequentialMockTransport(responses=responses)

        sleep_calls: list[float] = []

        def tracking_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        client = AuthorizationClient(
            transport=transport,
            max_retries=max_retries,
            base_backoff=base_backoff,
            sleep=tracking_sleep,
        )

        with pytest.raises(ServiceUnavailableError):
            client.set_resource_parents(
                resource_type=resource_type,
                resource_id=resource_id,
                parents=[],
            )

        # Total requests: 1 initial + max_retries retries
        assert len(transport.requests) == 1 + max_retries

        # Verify sleep was called max_retries times
        assert len(sleep_calls) == max_retries

        # Verify exponential backoff pattern
        for attempt in range(max_retries):
            expected_delay = base_backoff * (2**attempt)
            assert abs(sleep_calls[attempt] - expected_delay) < 1e-9

    @settings(max_examples=100)
    @given(
        user_id=user_ids,
        max_retries=retry_counts,
    )
    def test_get_user_permissions_succeeds_after_503_retries(
        self,
        user_id: str,
        max_retries: int,
    ) -> None:
        """get_user_permissions succeeds when 503 clears before exhaustion.

        **Validates: Requirements 5.3, 8.1**
        """
        # Return 503 for (max_retries - 1) retries, then succeed
        retries_before_success = max_retries - 1
        responses: list[MockResponse] = [MockResponse(status_code=503, body=b"")] * (
            retries_before_success + 1
        )  # +1 for initial request
        success_body = json.dumps({"userId": user_id, "permissions": {}}).encode()
        responses.append(MockResponse(status_code=200, body=success_body))

        transport = SequentialMockTransport(responses=responses)
        client = AuthorizationClient(
            transport=transport,
            max_retries=max_retries,
            sleep=no_sleep,
        )

        result = client.get_user_permissions(user_id=user_id)
        assert result.user_id == user_id


# --- Property 6: Immediate failure on non-retriable errors ---
# Validates: Requirements 5.4, 6.5, 8.4


class TestProperty6ImmediateFailure:
    """Property 6: Immediate failure on non-retriable errors.

    For any HTTP status code that is not 503 and not 200/201, the client
    SHALL raise an error on the first attempt without retrying.

    **Validates: Requirements 5.4, 6.5, 8.4**
    """

    @settings(max_examples=100)
    @given(
        user_id=user_ids,
        status_code=non_retriable_error_codes,
    )
    def test_get_user_permissions_fails_immediately_on_non_retriable(
        self,
        user_id: str,
        status_code: int,
    ) -> None:
        """get_user_permissions raises immediately on non-503 errors.

        **Validates: Requirements 5.4, 8.4**
        """
        error_body = json.dumps(
            {"error": "some_error", "message": "Error occurred"}
        ).encode()
        transport = SequentialMockTransport(
            responses=[MockResponse(status_code=status_code, body=error_body)]
        )
        client = AuthorizationClient(
            transport=transport,
            max_retries=3,
            sleep=no_sleep,
        )

        with pytest.raises((UnexpectedError, Exception)):
            client.get_user_permissions(user_id=user_id)

        # Only one request was made — no retries
        assert len(transport.requests) == 1

    @settings(max_examples=100)
    @given(
        resource_type=resource_types,
        resource_id=resource_ids,
        status_code=non_retriable_error_codes,
    )
    def test_set_resource_parents_fails_immediately_on_non_retriable(
        self,
        resource_type: str,
        resource_id: str,
        status_code: int,
    ) -> None:
        """set_resource_parents raises immediately on non-503 errors.

        **Validates: Requirements 6.5, 8.4**
        """
        error_body = json.dumps(
            {"error": "some_error", "message": "Error occurred"}
        ).encode()
        transport = SequentialMockTransport(
            responses=[MockResponse(status_code=status_code, body=error_body)]
        )
        client = AuthorizationClient(
            transport=transport,
            max_retries=3,
            sleep=no_sleep,
        )

        with pytest.raises((UnexpectedError, Exception)):
            client.set_resource_parents(
                resource_type=resource_type,
                resource_id=resource_id,
                parents=[],
            )

        # Only one request was made — no retries
        assert len(transport.requests) == 1
