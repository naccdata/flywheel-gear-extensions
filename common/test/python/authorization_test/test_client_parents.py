"""Tests for AuthorizationClient.set_resource_parents method."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import ParentRelationshipModel, ResourceParents

from .conftest import MockResponse, MockTransport, no_sleep


class TestSetResourceParents:
    """Tests for the set_resource_parents method."""

    def test_sends_put_to_correct_path(self) -> None:
        """Verify set_resource_parents sends PUT to.

        /resources/{type}/{id}/parents.
        """
        response_body = json.dumps(
            {
                "type": "study",
                "resourceId": "study-123",
                "parents": [
                    {
                        "structuralRelation": "parent_center",
                        "parentType": "research_center",
                        "parentId": "center-1",
                    }
                ],
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        parents = [
            ParentRelationshipModel(
                structural_relation="parent_center",
                parent_type="research_center",
                parent_id="center-1",
            )
        ]
        client.set_resource_parents(
            resource_type="study",
            resource_id="study-123",
            parents=parents,
        )

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "PUT"
        assert path == "/resources/study/study-123/parents"
        assert query_params is None

        # Verify the request body contains the correct fields
        assert body is not None
        request_data = json.loads(body)
        assert len(request_data["parents"]) == 1
        parent = request_data["parents"][0]
        assert parent["structuralRelation"] == "parent_center"
        assert parent["parentType"] == "research_center"
        assert parent["parentId"] == "center-1"

    def test_returns_resource_parents_on_200(self) -> None:
        """Verify 200 response is parsed into ResourceParents."""
        response_body = json.dumps(
            {
                "type": "study",
                "resourceId": "study-456",
                "parents": [
                    {
                        "structuralRelation": "parent_center",
                        "parentType": "research_center",
                        "parentId": "center-2",
                    },
                    {
                        "structuralRelation": "parent_community",
                        "parentType": "community",
                        "parentId": "comm-1",
                    },
                ],
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        parents = [
            ParentRelationshipModel(
                structural_relation="parent_center",
                parent_type="research_center",
                parent_id="center-2",
            ),
            ParentRelationshipModel(
                structural_relation="parent_community",
                parent_type="community",
                parent_id="comm-1",
            ),
        ]
        result = client.set_resource_parents(
            resource_type="study",
            resource_id="study-456",
            parents=parents,
        )

        assert isinstance(result, ResourceParents)
        assert result.type == "study"
        assert result.resource_id == "study-456"
        assert len(result.parents) == 2
        assert result.parents[0].structural_relation == "parent_center"
        assert result.parents[0].parent_type == "research_center"
        assert result.parents[0].parent_id == "center-2"
        assert result.parents[1].structural_relation == "parent_community"
        assert result.parents[1].parent_type == "community"
        assert result.parents[1].parent_id == "comm-1"

    def test_raises_validation_error_on_400(self) -> None:
        """Verify 400 raises ValidationError with API message."""
        error_body = json.dumps(
            {
                "error": "validation_error",
                "message": "Invalid parent type",
                "details": {"field": "parentType"},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=400, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        parents = [
            ParentRelationshipModel(
                structural_relation="parent_center",
                parent_type="invalid_type",
                parent_id="center-1",
            )
        ]

        with pytest.raises(ValidationError) as exc_info:
            client.set_resource_parents(
                resource_type="study",
                resource_id="study-1",
                parents=parents,
            )

        assert exc_info.value.message == "Invalid parent type"
        assert exc_info.value.details == {"field": "parentType"}

    def test_retries_on_503(self) -> None:
        """Verify 503 triggers retry and succeeds on subsequent attempt."""
        success_body = json.dumps(
            {
                "type": "study",
                "resourceId": "study-1",
                "parents": [],
            }
        ).encode()
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(status_code=200, body=success_body),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.set_resource_parents(
            resource_type="study",
            resource_id="study-1",
            parents=[],
        )

        assert isinstance(result, ResourceParents)
        # Initial request + 1 retry
        assert len(transport.requests) == 2

    def test_raises_service_unavailable_after_retries_exhausted(self) -> None:
        """Verify ServiceUnavailableError when all retries fail with 503."""
        transport = MockTransport(MockResponse(status_code=503, body=b""))
        client = AuthorizationClient(transport=transport, max_retries=2, sleep=no_sleep)

        with pytest.raises(ServiceUnavailableError):
            client.set_resource_parents(
                resource_type="study",
                resource_id="study-1",
                parents=[],
            )

        # Initial request + 2 retries = 3 total
        assert len(transport.requests) == 3

    def test_raises_unexpected_error_on_500(self) -> None:
        """Verify 500 raises UnexpectedError immediately."""
        error_body = json.dumps({"message": "Internal server error"}).encode()
        transport = MockTransport(MockResponse(status_code=500, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.set_resource_parents(
                resource_type="study",
                resource_id="study-1",
                parents=[],
            )

        assert exc_info.value.status_code == 500
        assert "Internal server error" in exc_info.value.message

    def test_raises_unexpected_error_on_403(self) -> None:
        """Verify 403 raises UnexpectedError (not retried)."""
        error_body = json.dumps({"message": "Forbidden"}).encode()
        transport = MockTransport(MockResponse(status_code=403, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.set_resource_parents(
                resource_type="study",
                resource_id="study-1",
                parents=[],
            )

        assert exc_info.value.status_code == 403
        # Should only make one request (no retry)
        assert len(transport.requests) == 1

    def test_raises_parse_error_on_invalid_response(self) -> None:
        """Verify ParseError when 200 response has invalid JSON."""
        transport = MockTransport(MockResponse(status_code=200, body=b"not valid json"))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.set_resource_parents(
                resource_type="study",
                resource_id="study-1",
                parents=[],
            )

        assert exc_info.value.raw_content == b"not valid json"

    def test_sends_empty_parents_list(self) -> None:
        """Verify empty parents list is sent correctly."""
        response_body = json.dumps(
            {
                "type": "study",
                "resourceId": "study-1",
                "parents": [],
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.set_resource_parents(
            resource_type="study",
            resource_id="study-1",
            parents=[],
        )

        assert isinstance(result, ResourceParents)
        assert result.parents == []

        # Verify request body
        _, _, body, _ = transport.requests[0]
        assert body is not None
        request_data = json.loads(body)
        assert request_data["parents"] == []
