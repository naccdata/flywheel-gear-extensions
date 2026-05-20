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


class TestGrant:
    """Tests for the grant method."""

    def test_grant_sends_post_to_grants(self) -> None:
        """Verify grant sends POST to /grants with correct JSON body."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-123",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=201, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.grant(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-123",
            relation="member",
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "POST"
        assert path == "/grants"
        assert query_params is None

        # Verify the request body contains the correct fields
        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == "user@example.com"
        assert request_data["relation"] == "member"
        assert request_data["type"] == "study"
        assert request_data["resourceId"] == "study-123"

    def test_grant_returns_grant_result_on_201(self) -> None:
        """Verify 201 response is parsed into GrantResult."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "admin",
                "type": "research_center",
                "resourceId": "center-456",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=201, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="research_center",
            resource_id="center-456",
            relation="admin",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "admin"
        assert result.type == "research_center"
        assert result.resource_id == "center-456"

    def test_grant_returns_grant_result_on_200(self) -> None:
        """Verify 200 response is also treated as success."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "viewer",
                "type": "dashboard",
                "resourceId": "dash-1",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="dashboard",
            resource_id="dash-1",
            relation="viewer",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"

    def test_grant_treats_409_as_success(self) -> None:
        """Verify 409 (conflict) returns GrantResult without raising."""
        transport = MockTransport(MockResponse(status_code=409, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-123",
            relation="member",
        )

        assert isinstance(result, GrantResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "member"
        assert result.type == "study"
        assert result.resource_id == "study-123"

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
                resource_type="invalid_type",
                resource_id="res-1",
                relation="member",
            )

        assert exc_info.value.message == "Invalid resource type"
        assert exc_info.value.details == {"field": "type"}

    def test_grant_raises_unexpected_error_on_500(self) -> None:
        """Verify 500 raises UnexpectedError immediately."""
        error_body = json.dumps({"message": "Internal server error"}).encode()
        transport = MockTransport(MockResponse(status_code=500, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
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
                resource_id="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 403
        # Should only make one request (no retry)
        assert len(transport.requests) == 1

    def test_grant_retries_on_503(self) -> None:
        """Verify 503 triggers retry and succeeds on subsequent attempt."""
        success_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-1",
            }
        ).encode()
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(status_code=201, body=success_body),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.grant(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-1",
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
                resource_id="study-1",
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
                resource_id="study-1",
                relation="member",
            )

        assert exc_info.value.raw_content == b"not valid json"
