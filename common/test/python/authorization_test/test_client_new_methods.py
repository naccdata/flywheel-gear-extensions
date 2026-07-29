"""Tests for new AuthorizationClient methods.

Covers: get_resource_parents, delete_resource_parents, list_resources,
get_model, check_permission, search_user_profiles.
"""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    NotFoundError,
    ParseError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import (
    AuthorizationModelMetadata,
    ResourceListResponse,
    ResourceParents,
)

from .conftest import MockResponse, MockTransport, no_sleep

# --- get_resource_parents ---


class TestGetResourceParents:
    """Tests for get_resource_parents."""

    def test_sends_get_to_correct_path(self) -> None:
        """Sends GET /resources/{type}/{id}/parents."""
        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "type": "data_pipeline",
                    "resourceId": "pipe-1",
                    "parents": [],
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.get_resource_parents("data_pipeline", "pipe-1")

        method, path, body, _ = transport.requests[0]
        assert method == "GET"
        assert path == "/resources/data_pipeline/pipe-1/parents"
        assert body is None

    def test_returns_resource_parents_on_200(self) -> None:
        """Parses 200 response into ResourceParents."""
        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "type": "data_pipeline",
                    "resourceId": "pipe-1",
                    "parents": [
                        {
                            "structuralRelation": "parent_study",
                            "parentType": "study",
                            "parentId": "study1",
                        }
                    ],
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.get_resource_parents("data_pipeline", "pipe-1")

        assert isinstance(result, ResourceParents)
        assert len(result.parents) == 1
        assert result.parents[0].parent_id == "study1"

    def test_raises_not_found_on_404(self) -> None:
        """Raises NotFoundError on 404."""
        response = MockResponse(
            status_code=404,
            body=b'{"error":"not_found","message":"not found"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(NotFoundError):
            client.get_resource_parents("data_pipeline", "pipe-1")

    def test_raises_validation_error_on_400(self) -> None:
        """Raises ValidationError on 400."""
        response = MockResponse(
            status_code=400,
            body=b'{"error":"validation_error","message":"bad type"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.get_resource_parents("bad_type", "pipe-1")

    def test_raises_unexpected_error_on_500(self) -> None:
        """Raises UnexpectedError on 500."""
        response = MockResponse(status_code=500, body=b"server error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.get_resource_parents("data_pipeline", "pipe-1")


# --- delete_resource_parents ---


class TestDeleteResourceParents:
    """Tests for delete_resource_parents."""

    def test_sends_delete_to_correct_path(self) -> None:
        """Sends DELETE /resources/{type}/{id}/parents."""
        response = MockResponse(status_code=200, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.delete_resource_parents("data_pipeline", "pipe-1")

        method, path, body, _ = transport.requests[0]
        assert method == "DELETE"
        assert path == "/resources/data_pipeline/pipe-1/parents"
        assert body is None

    def test_returns_none_on_200(self) -> None:
        """Returns None on successful deletion."""
        response = MockResponse(status_code=200, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.delete_resource_parents("data_pipeline", "pipe-1")

    def test_returns_none_on_404_idempotent(self) -> None:
        """Returns None on 404 (idempotent)."""
        response = MockResponse(status_code=404, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.delete_resource_parents("data_pipeline", "pipe-1")

    def test_raises_validation_error_on_400(self) -> None:
        """Raises ValidationError on 400."""
        response = MockResponse(
            status_code=400,
            body=b'{"error":"validation_error","message":"invalid"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.delete_resource_parents("bad", "pipe-1")

    def test_raises_unexpected_error_on_500(self) -> None:
        """Raises UnexpectedError on 500."""
        response = MockResponse(status_code=500, body=b"error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.delete_resource_parents("data_pipeline", "pipe-1")


# --- list_resources ---


class TestListResources:
    """Tests for list_resources."""

    def test_sends_get_to_correct_path_unfiltered(self) -> None:
        """Sends GET /resources/{type} with no query params when unfiltered."""
        response = MockResponse(
            status_code=200,
            body=json.dumps({"resources": [], "nextToken": None, "limit": 50}).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.list_resources("data_pipeline")

        method, path, body, query_params = transport.requests[0]
        assert method == "GET"
        assert path == "/resources/data_pipeline"
        assert body is None
        assert query_params is None

    def test_sends_parent_params_when_filtered(self) -> None:
        """Includes parentType and parentId in query params."""
        response = MockResponse(
            status_code=200,
            body=json.dumps({"resources": [], "nextToken": None, "limit": 50}).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.list_resources("data_pipeline", parent_type="study", parent_id="study1")

        _, _, _, query_params = transport.requests[0]
        assert query_params == {"parentType": "study", "parentId": "study1"}

    def test_sends_search_param(self) -> None:
        """Includes search in query params."""
        response = MockResponse(
            status_code=200,
            body=json.dumps({"resources": [], "nextToken": None, "limit": 50}).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.list_resources("data_pipeline", search="clinical")

        _, _, _, query_params = transport.requests[0]
        assert query_params == {"search": "clinical"}

    def test_returns_resource_list_response_on_200(self) -> None:
        """Parses 200 response into ResourceListResponse."""
        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "resources": [
                        {"resourceId": "pipe-1", "structuralRelation": "parent_study"}
                    ],
                    "nextToken": "abc",
                    "limit": 50,
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.list_resources("data_pipeline")

        assert isinstance(result, ResourceListResponse)
        assert len(result.resources) == 1
        assert result.resources[0].resource_id == "pipe-1"
        assert result.next_token == "abc"

    def test_raises_validation_error_on_400(self) -> None:
        """Raises ValidationError on 400."""
        response = MockResponse(
            status_code=400,
            body=b'{"error":"validation_error","message":"partial params"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.list_resources("data_pipeline", parent_type="study")

    def test_raises_not_found_on_404(self) -> None:
        """Raises NotFoundError on 404."""
        response = MockResponse(
            status_code=404,
            body=b'{"error":"not_found","message":"type not found"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(NotFoundError):
            client.list_resources("nonexistent_type")


# --- get_model ---


class TestGetModel:
    """Tests for get_model."""

    def test_sends_get_to_model(self) -> None:
        """Sends GET /model."""
        model_json = {
            "version": "1.0.0",
            "types": {
                "study": {
                    "name": "study",
                    "category": "organization",
                    "relations": {
                        "member": {
                            "name": "member",
                            "assignable": True,
                        }
                    },
                }
            },
        }
        response = MockResponse(status_code=200, body=json.dumps(model_json).encode())
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.get_model()

        method, path, body, _ = transport.requests[0]
        assert method == "GET"
        assert path == "/model"
        assert body is None

    def test_returns_authorization_model_metadata_on_200(self) -> None:
        """Parses 200 response into AuthorizationModelMetadata."""
        model_json = {
            "version": "1.0.0",
            "types": {
                "data_pipeline": {
                    "name": "data_pipeline",
                    "category": "resource",
                    "relations": {
                        "viewer": {
                            "name": "viewer",
                            "assignable": True,
                        },
                        "submitter": {
                            "name": "submitter",
                            "assignable": True,
                        },
                    },
                }
            },
        }
        response = MockResponse(status_code=200, body=json.dumps(model_json).encode())
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.get_model()

        assert isinstance(result, AuthorizationModelMetadata)
        assert result.version == "1.0.0"
        assert "data_pipeline" in result.types
        assert result.types["data_pipeline"].relations["viewer"].assignable is True

    def test_raises_unexpected_error_on_500(self) -> None:
        """Raises UnexpectedError on 500."""
        response = MockResponse(status_code=500, body=b"error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.get_model()

    def test_raises_parse_error_on_bad_json(self) -> None:
        """Raises ParseError on invalid JSON."""
        response = MockResponse(status_code=200, body=b"not json")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError):
            client.get_model()


# --- check_permission ---


class TestCheckPermission:
    """Tests for check_permission."""

    def test_sends_post_to_check(self) -> None:
        """Sends POST /check with correct body."""
        response = MockResponse(status_code=200, body=b'{"allowed": true}')
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.check_permission("alice", "data_pipeline", "pipe-1", "viewer")

        method, path, body, _ = transport.requests[0]
        assert method == "POST"
        assert path == "/check"
        assert body is not None
        parsed = json.loads(body)
        assert parsed["userId"] == "alice"
        assert parsed["type"] == "data_pipeline"
        assert parsed["resourceId"] == "pipe-1"
        assert parsed["relation"] == "viewer"

    def test_returns_true_when_allowed(self) -> None:
        """Returns True when API responds with allowed=true."""
        response = MockResponse(status_code=200, body=b'{"allowed": true}')
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.check_permission("alice", "data_pipeline", "pipe-1", "viewer")

        assert result is True

    def test_returns_false_when_not_allowed(self) -> None:
        """Returns False when API responds with allowed=false."""
        response = MockResponse(status_code=200, body=b'{"allowed": false}')
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.check_permission("alice", "data_pipeline", "pipe-1", "viewer")

        assert result is False

    def test_raises_validation_error_on_400(self) -> None:
        """Raises ValidationError on 400."""
        response = MockResponse(
            status_code=400,
            body=b'{"error":"validation_error","message":"bad relation"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.check_permission("alice", "data_pipeline", "pipe-1", "bad_relation")

    def test_raises_unexpected_error_on_500(self) -> None:
        """Raises UnexpectedError on 500."""
        response = MockResponse(status_code=500, body=b"error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.check_permission("alice", "data_pipeline", "pipe-1", "viewer")


# --- search_user_profiles ---


class TestSearchUserProfiles:
    """Tests for search_user_profiles."""

    def test_sends_get_with_search_param(self) -> None:
        """Sends GET /users?search=...

        with the search query.
        """
        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "users": [],
                    "nextToken": None,
                    "total": 0,
                    "limit": 25,
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.search_user_profiles("jane")

        method, path, body, query_params = transport.requests[0]
        assert method == "GET"
        assert path == "/users"
        assert body is None
        assert query_params == {"search": "jane"}

    def test_sends_limit_and_next_token_params(self) -> None:
        """Includes limit and nextToken in query params when provided."""
        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "users": [],
                    "nextToken": None,
                    "total": 0,
                    "limit": 10,
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.search_user_profiles("smith", limit=10, next_token="cursor123")

        _, _, _, query_params = transport.requests[0]
        assert query_params == {
            "search": "smith",
            "limit": "10",
            "nextToken": "cursor123",
        }

    def test_returns_search_response_on_200(self) -> None:
        """Parses 200 response into UserProfileSearchResponse."""
        from authorization.models import UserProfileSearchResponse

        response = MockResponse(
            status_code=200,
            body=json.dumps(
                {
                    "users": [
                        {
                            "userId": "Registry000001@naccdata.org",
                            "firstName": "Jane",
                            "lastName": "Smith",
                            "authEmail": "jane@example.com",
                            "active": True,
                        }
                    ],
                    "nextToken": "next-page-token",
                    "total": 1,
                    "limit": 25,
                }
            ).encode(),
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.search_user_profiles("jane")

        assert isinstance(result, UserProfileSearchResponse)
        assert len(result.users) == 1
        assert result.users[0].first_name == "Jane"
        assert result.users[0].user_id == "Registry000001@naccdata.org"
        assert result.next_token == "next-page-token"
        assert result.total == 1
        assert result.limit == 25

    def test_raises_validation_error_on_400(self) -> None:
        """Raises ValidationError on 400."""
        response = MockResponse(
            status_code=400,
            body=b'{"error":"validation_error","message":"search too short"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ValidationError):
            client.search_user_profiles("")

    def test_raises_unexpected_error_on_500(self) -> None:
        """Raises UnexpectedError on 500."""
        response = MockResponse(status_code=500, body=b"internal error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.search_user_profiles("jane")

    def test_raises_parse_error_on_bad_json(self) -> None:
        """Raises ParseError on invalid JSON in 200 response."""
        response = MockResponse(status_code=200, body=b"not json")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(ParseError):
            client.search_user_profiles("jane")
