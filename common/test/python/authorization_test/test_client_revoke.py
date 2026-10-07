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


def _revoke_response_body(
    user_id: str = "user@example.com",
    relation: str = "member",
    resource_type: str = "study",
    resource_id: str = "study-123",
    resource: dict | None = None,
) -> bytes:
    """Build a JSON revoke response body with a structured resource.

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


class TestRevoke:
    """Tests for the revoke method."""

    def test_revoke_sends_delete_with_structured_resource(self) -> None:
        """Verify revoke sends DELETE to /grants with a structured resource
        body."""
        transport = MockTransport(
            MockResponse(status_code=200, body=_revoke_response_body())
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.revoke(
            user_id="user@example.com",
            resource_type="data_pipeline",
            resource_label="pipeline-1",
            relation="member",
            study="study-123",
            center="center-1",
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "DELETE"
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

    def test_revoke_returns_revoke_result_on_200(self) -> None:
        """Verify 200 response is parsed into RevokeResult."""
        transport = MockTransport(
            MockResponse(
                status_code=200,
                body=_revoke_response_body(
                    relation="admin",
                    resource_type="research_center",
                    resource_id="center-456",
                ),
            )
        )
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="research_center",
            resource_label="center-456",
            relation="admin",
        )

        assert isinstance(result, RevokeResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "admin"
        assert result.resource is not None
        assert result.resource.type == "research_center"
        assert result.resource.label == "center-456"

    def test_revoke_treats_404_as_success_from_structured_resource(self) -> None:
        """Verify 404 (not found) returns a RevokeResult built from the
        structured resource without raising or retrying."""
        transport = MockTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="data_pipeline",
            resource_label="pipeline-1",
            relation="member",
            study="study-123",
            center="center-1",
        )

        assert isinstance(result, RevokeResult)
        assert result.user_id == "user@example.com"
        assert result.relation == "member"
        # Idempotent result is built from the request's structured resource.
        assert result.resource is not None
        assert result.resource.type == "data_pipeline"
        assert result.resource.label == "pipeline-1"
        assert result.resource.study == "study-123"
        assert result.resource.center == "center-1"
        # No retry on an idempotent not-found.
        assert len(transport.requests) == 1

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
                resource_label="study-1",
                relation="",
            )

        assert exc_info.value.message == "Missing required field: relation"
        assert exc_info.value.details == {"field": "relation"}

    def test_revoke_rejects_invalid_identity_before_request(self) -> None:
        """Verify an invalid structured identity raises before any HTTP call
        (empty label)."""
        transport = MockTransport(MockResponse(status_code=200, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_label="",
                relation="member",
            )

        # No request sent because identity failed validation.
        assert len(transport.requests) == 0

    def test_revoke_raises_unexpected_error_on_500(self) -> None:
        """Verify 500 raises UnexpectedError immediately."""
        error_body = json.dumps({"message": "Internal server error"}).encode()
        transport = MockTransport(MockResponse(status_code=500, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_label="study-1",
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
                resource_label="study-1",
                relation="member",
            )

        assert exc_info.value.status_code == 409

    def test_revoke_retries_on_503(self) -> None:
        """Verify 503 triggers retry and succeeds on subsequent attempt."""
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(
                status_code=200,
                body=_revoke_response_body(resource_id="study-1"),
            ),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.revoke(
            user_id="user@example.com",
            resource_type="study",
            resource_label="study-1",
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
                resource_label="study-1",
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
                resource_label="study-1",
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
                resource_label="study-1",
                relation="member",
            )

        # Should only make one request (no retry)
        assert len(transport.requests) == 1
