"""Tests for AuthorizationClient.grant method."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import GrantResult

from .conftest import MockResponse, MockTransport, no_sleep


def _grant_response_body(
    user_id: str = "user@example.com",
    relation: str = "member",
    resource_type: str = "study",
    resource_id: str = "study-123",
    resource: dict | None = None,
) -> bytes:
    """Build a JSON grant response body with a structured resource.

    Identity is returned solely in the structured ``resource`` object;
    the response model reads identity from it and ignores any top-level
    ``type``/``resourceId``. When ``resource`` is not supplied, a
    minimal structured resource is synthesized from
    ``resource_type``/``resource_id`` (as ``label``) so a parsed result
    carries identity.
    """
    body: dict = {
        "userId": user_id,
        "relation": relation,
    }
    if resource is None:
        resource = {"type": resource_type, "label": resource_id}
    body["resource"] = resource
    return json.dumps(body).encode()


class TestGrant:
    """Tests for the grant method."""

    def test_grant_sends_post_with_structured_resource(self) -> None:
        """Verify grant POSTs /grants with a structured resource body."""
        transport = MockTransport(
            MockResponse(status_code=201, body=_grant_response_body())
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.grant(
            user_id="user@example.com",
            resource_type="data_pipeline",
            resource_label="pipeline-1",
            relation="member",
            study="study-123",
            center="center-1",
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "POST"
        assert path == "/grants"
        assert query_params is None

        # Request body carries userId, relation, and a structured resource;
        # no top-level type/resourceId and no flat_id.
        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == "user@example.com"
        assert request_data["relation"] == "member"
        assert "type" not in request_data
        assert "resourceId" not in request_data

        resource = request_data["resource"]
        assert resource["type"] == "data_pipeline"
        assert resource["label"] == "pipeline-1"
        assert resource["study"] == "study-123"
        assert resource["center"] == "center-1"
        assert "flat_id" not in resource
        assert "flatId" not in resource

    def test_grant_returns_grant_result_on_201(self) -> None:
        """Verify 201 response is parsed into GrantResult."""
        transport = MockTransport(
            MockResponse(
                status_code=201,
                body=_grant_response_body(
                    relation="admin",
                    resource_type="research_center",
                    resource_id="center-456",
                ),
            )
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="research_center",
            resource_label="center-456",
            relation="admin",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "admin"
        assert result.resource is not None
        assert result.resource.type == "research_center"
        assert result.resource.label == "center-456"

    def test_grant_returns_grant_result_on_200(self) -> None:
        """Verify 200 response is also treated as success."""
        transport = MockTransport(
            MockResponse(
                status_code=200,
                body=_grant_response_body(
                    relation="viewer",
                    resource={
                        "type": "dashboard",
                        "label": "dash-1",
                        "study": "study-1",
                    },
                ),
            )
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="dashboard",
            resource_label="dash-1",
            relation="viewer",
            study="study-1",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"

    def test_grant_treats_409_as_success_from_structured_resource(self) -> None:
        """Verify 409 (conflict) returns a GrantResult built from the
        structured resource without raising or retrying."""
        transport = MockTransport(MockResponse(status_code=409, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="data_pipeline",
            resource_label="pipeline-1",
            relation="member",
            study="study-123",
            center="center-1",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "member"
        # Idempotent result is built from the request's structured resource.
        assert result.resource is not None
        assert result.resource.type == "data_pipeline"
        assert result.resource.label == "pipeline-1"
        assert result.resource.study == "study-123"
        assert result.resource.center == "center-1"
        # No retry on an idempotent conflict.
        assert len(transport.requests) == 1

    def test_grant_raises_validation_error_on_400(self) -> None:
        """Verify 400 raises ValidationError with API message."""
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": "Invalid resource type",
                "details": {"field": "type"},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.grant(
                user_id="user@example.com",
                resource_type="dashboard",
                resource_label="res-1",
                relation="member",
                study="study-1",
            )

        assert exc_info.value.message == "Invalid resource type"
        assert exc_info.value.details == {"field": "type"}

    def test_grant_rejects_invalid_identity_before_request(self) -> None:
        """Verify an invalid structured identity raises before any HTTP call
        (empty label)."""
        transport = MockTransport(MockResponse(status_code=201, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_label="",
                relation="member",
            )

        # No request sent because identity failed validation.
        assert len(transport.requests) == 0

    def test_grant_raises_unexpected_error_on_500(self) -> None:
        """Verify 500 raises UnexpectedError immediately."""
        error_body = json.dumps({"message": "Internal server error"}).encode()
        transport = MockTransport(MockResponse(status_code=500, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_label="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 500
        assert "Internal server error" in exc_info.value.message

    def test_grant_raises_unexpected_error_on_403(self) -> None:
        """Verify 403 raises UnexpectedError (not retried)."""
        error_body = json.dumps({"message": "Forbidden"}).encode()
        transport = MockTransport(MockResponse(status_code=403, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_label="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 403
        # Should only make one request (no retry)
        assert len(transport.requests) == 1

    def test_grant_retries_on_503(self) -> None:
        """Verify 503 triggers retry and succeeds on subsequent attempt."""
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(
                status_code=201,
                body=_grant_response_body(resource_id="study-1"),
            ),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="study",
            resource_label="study-1",
            relation="member",
        )

        assert isinstance(result, GrantResult)
        # Initial request + 1 retry
        assert len(transport.requests) == 2

    def test_grant_raises_service_unavailable_after_retries_exhausted(
        self,
    ) -> None:
        """Verify ServiceUnavailableError when all retries fail with 503."""
        transport = MockTransport(MockResponse(status_code=503, body=b""))
        client = AuthorizationClient(transport=transport, max_retries=2, sleep=no_sleep)

        with pytest.raises(ServiceUnavailableError):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_label="study-1",
                relation="member",
            )

        # Initial request + 2 retries = 3 total
        assert len(transport.requests) == 3

    def test_grant_raises_parse_error_on_invalid_response(self) -> None:
        """Verify ParseError when 201 response has invalid JSON."""
        transport = MockTransport(MockResponse(status_code=201, body=b"not valid json"))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_label="study-1",
                relation="member",
            )

        assert exc_info.value.raw_content == b"not valid json"
