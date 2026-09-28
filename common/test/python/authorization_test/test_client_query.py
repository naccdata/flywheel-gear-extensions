"""Tests for AuthorizationClient.get_user_permissions method."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
)
from authorization.models import UserPermissions

from .conftest import MockResponse, MockTransport, no_sleep


class TestGetUserPermissions:
    """Tests for the get_user_permissions method."""

    def test_sends_get_to_users_permissions_path(self) -> None:
        """Verify GET request to /users/{userId}/permissions."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        client.get_user_permissions(user_id="user@example.com", type_filter="study")

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "GET"
        assert path == "/users/user@example.com/permissions"
        assert body is None
        assert query_params == {"type": "study"}

    def test_includes_type_query_param_when_provided(self) -> None:
        """Verify type filter is passed as query parameter."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        client.get_user_permissions(user_id="user@example.com", type_filter="study")

        _, _, _, query_params = transport.requests[0]
        assert query_params == {"type": "study"}

    def test_includes_relation_query_param_when_provided(self) -> None:
        """Verify relation filter is passed as query parameter."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        client.get_user_permissions(
            user_id="user@example.com",
            type_filter="study",
            relation_filter="member",
        )

        _, _, _, query_params = transport.requests[0]
        assert query_params == {"type": "study", "relation": "member"}

    def test_includes_both_query_params_when_provided(self) -> None:
        """Verify both type and relation filters are passed."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {},
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        client.get_user_permissions(
            user_id="user@example.com",
            type_filter="study",
            relation_filter="admin",
        )

        _, _, _, query_params = transport.requests[0]
        assert query_params == {"type": "study", "relation": "admin"}

    def test_returns_user_permissions_on_200(self) -> None:
        """Verify 200 response is parsed into UserPermissions model.

        Identity is read from the structured ``resource`` object, not a
        flat top-level ``resourceId``.
        """
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {
                    "study": [
                        {
                            "resource": {"type": "study", "label": "study-1"},
                            "relation": "member",
                        }
                    ],
                    "research_center": [
                        {
                            "resource": {
                                "type": "research_center",
                                "label": "center-1",
                            },
                            "relation": "admin",
                        }
                    ],
                },
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        result = client.get_user_permissions(
            user_id="user@example.com", type_filter="study"
        )

        assert isinstance(result, UserPermissions)
        assert result.user_id == "user@example.com"
        assert len(result.permissions) == 2
        assert len(result.permissions["study"]) == 1
        study_entry = result.permissions["study"][0]
        assert study_entry.resource is not None
        assert study_entry.resource.type == "study"
        assert study_entry.resource.label == "study-1"
        assert study_entry.relation == "member"
        assert study_entry.access is None
        center_entry = result.permissions["research_center"][0]
        assert center_entry.resource is not None
        assert center_entry.resource.type == "research_center"
        assert center_entry.resource.label == "center-1"
        assert center_entry.relation == "admin"

    def test_parses_resource_with_parent_fields(self) -> None:
        """Verify a structured resource carrying parent fields parses.

        A ``data_pipeline`` resource carries ``study`` + ``center``
        parents, read directly from the structured ``resource`` object.
        """
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {
                    "data_pipeline": [
                        {
                            "resource": {
                                "type": "data_pipeline",
                                "label": "ingest-form",
                                "study": "study-1",
                                "center": "center-1",
                            },
                            "relation": "submitter",
                        }
                    ],
                },
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        result = client.get_user_permissions(
            user_id="user@example.com", type_filter="data_pipeline"
        )

        entry = result.permissions["data_pipeline"][0]
        assert entry.resource is not None
        assert entry.resource.type == "data_pipeline"
        assert entry.resource.label == "ingest-form"
        assert entry.resource.study == "study-1"
        assert entry.resource.center == "center-1"
        assert entry.relation == "submitter"

    def test_absent_resource_yields_no_identity(self) -> None:
        """Verify an entry without a ``resource`` parses with no identity.

        A catalog-gap entry has no ``resource`` field. It must parse
        with ``resource is None`` rather than failing.
        """
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {
                    "study": [
                        {
                            "relation": "member",
                        }
                    ],
                },
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        result = client.get_user_permissions(
            user_id="user@example.com", type_filter="study"
        )

        entry = result.permissions["study"][0]
        assert entry.resource is None
        assert entry.relation == "member"

    def test_top_level_resource_id_is_ignored_no_fallback(self) -> None:
        """Verify a top-level ``resourceId`` is dropped, never used.

        Under the structured contract, identity comes solely from
        ``resource``. A stray top-level ``resourceId`` in the body must
        not become the entry's identity: ``extra="ignore"`` drops it and
        the entry has ``resource is None``.
        """
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {
                    "study": [
                        {
                            "resourceId": "study-legacy",
                            "relation": "member",
                        }
                    ],
                },
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport)

        result = client.get_user_permissions(
            user_id="user@example.com", type_filter="study"
        )

        entry = result.permissions["study"][0]
        assert entry.resource is None
        assert not hasattr(entry, "resource_id")
        assert entry.relation == "member"

    def test_retries_on_503(self) -> None:
        """Verify 503 triggers retry and succeeds on subsequent 200."""
        success_body = json.dumps(
            {
                "userId": "user@example.com",
                "permissions": {},
            }
        ).encode()
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(status_code=200, body=success_body),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        result = client.get_user_permissions(
            user_id="user@example.com", type_filter="study"
        )

        assert isinstance(result, UserPermissions)
        # Initial request + 1 retry
        assert len(transport.requests) == 2

    def test_raises_service_unavailable_when_retries_exhausted(self) -> None:
        """Verify ServiceUnavailableError after all retries fail."""
        responses = [MockResponse(status_code=503, body=b"")] * 5
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=2, sleep=no_sleep)

        with pytest.raises(ServiceUnavailableError):
            client.get_user_permissions(user_id="user@example.com", type_filter="study")

    def test_raises_unexpected_error_on_non_200_non_503(self) -> None:
        """Verify non-200/non-503 status raises UnexpectedError."""
        response = MockResponse(status_code=500, body=b'{"message": "Internal error"}')
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        with pytest.raises(UnexpectedError) as exc_info:
            client.get_user_permissions(user_id="user@example.com", type_filter="study")

        assert exc_info.value.status_code == 500

    def test_raises_parse_error_on_invalid_json(self) -> None:
        """Verify malformed response body raises ParseError."""
        response = MockResponse(status_code=200, body=b"not valid json")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        with pytest.raises(ParseError) as exc_info:
            client.get_user_permissions(user_id="user@example.com", type_filter="study")

        assert exc_info.value.raw_content == b"not valid json"

    def test_does_not_retry_on_non_503_errors(self) -> None:
        """Verify non-503 errors fail immediately without retry."""
        response = MockResponse(status_code=403, body=b'{"message": "Forbidden"}')
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError):
            client.get_user_permissions(user_id="user@example.com", type_filter="study")

        # Only one request, no retries
        assert len(transport.requests) == 1
