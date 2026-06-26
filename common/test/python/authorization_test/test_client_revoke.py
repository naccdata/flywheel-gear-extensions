"""Tests for AuthorizationClient.revoke method."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import RevokeResult

from .conftest import MockResponse, MockTransport, no_sleep


class TestRevoke:
    """Tests for the revoke method."""

    def test_revoke_sends_delete_to_grants(self) -> None:
        """Verify revoke sends DELETE to /grants with correct JSON body."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-123",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.revoke(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-123",
            relation="member",
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "DELETE"
        assert path == "/grants"
        assert query_params is None

        # Verify the request body contains the correct fields
        assert body is not None
        request_data = json.loads(body)
        assert request_data["userId"] == "user@example.com"
        assert request_data["relation"] == "member"
        assert request_data["type"] == "study"
        assert request_data["resourceId"] == "study-123"

    def test_revoke_returns_revoke_result_on_200(self) -> None:
        """Verify 200 response is parsed into RevokeResult."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "admin",
                "type": "research_center",
                "resourceId": "center-456",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="research_center",
            resource_id="center-456",
            relation="admin",
        )

        assert isinstance(result, RevokeResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "admin"
        assert result.type == "research_center"
        assert result.resource_id == "center-456"

    def test_revoke_treats_404_as_success(self) -> None:
        """Verify 404 (not found) returns RevokeResult without raising."""
        transport = MockTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-123",
            relation="member",
        )

        assert isinstance(result, RevokeResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "member"
        assert result.type == "study"
        assert result.resource_id == "study-123"

    def test_revoke_raises_validation_error_on_400(self) -> None:
        """Verify 400 raises ValidationError with API message."""
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": "Missing required field: relation",
                "details": {"field": "relation"},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="",
            )

        assert exc_info.value.message == "Missing required field: relation"
        assert exc_info.value.details == {"field": "relation"}

    def test_revoke_raises_unexpected_error_on_500(self) -> None:
        """Verify 500 raises UnexpectedError immediately."""
        error_body = json.dumps({"message": "Internal server error"}).encode()
        transport = MockTransport(MockResponse(status_code=500, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 500
        assert "Internal server error" in exc_info.value.message

    def test_revoke_raises_unexpected_error_on_409(self) -> None:
        """Verify 409 on revoke raises UnexpectedError (not idempotent for
        revoke)."""
        error_body = json.dumps({"message": "Conflict"}).encode()
        transport = MockTransport(MockResponse(status_code=409, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 409

    def test_revoke_retries_on_503(self) -> None:
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
            MockResponse(status_code=200, body=success_body),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="study",
            resource_id="study-1",
            relation="member",
        )

        assert isinstance(result, RevokeResult)
        # Initial request + 1 retry
        assert len(transport.requests) == 2

    def test_revoke_raises_service_unavailable_after_retries_exhausted(
        self,
    ) -> None:
        """Verify ServiceUnavailableError when all retries fail with 503."""
        transport = MockTransport(MockResponse(status_code=503, body=b""))
        client = AuthorizationClient(transport=transport, max_retries=2, sleep=no_sleep)

        with pytest.raises(ServiceUnavailableError):
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        # Initial request + 2 retries = 3 total
        assert len(transport.requests) == 3

    def test_revoke_raises_parse_error_on_invalid_response(self) -> None:
        """Verify ParseError when 200 response has invalid JSON."""
        transport = MockTransport(MockResponse(status_code=200, body=b"not valid json"))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        assert exc_info.value.raw_content == b"not valid json"

    def test_revoke_does_not_retry_on_non_503_errors(self) -> None:
        """Verify non-503 errors are not retried."""
        error_body = json.dumps({"message": "Forbidden"}).encode()
        transport = MockTransport(MockResponse(status_code=403, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        # Should only make one request (no retry)
        assert len(transport.requests) == 1
