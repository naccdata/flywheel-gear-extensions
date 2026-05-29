"""Unit tests for AuthorizationClient user profile methods."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import NotFoundError
from authorization.models import UserProfile, UserProfileRequest

from .conftest import MockResponse, MockTransport, no_sleep


class TestPutUserProfile:
    """Tests for the put_user_profile method."""

    def test_put_user_profile_returns_parsed_user_profile_on_200(self) -> None:
        """Verify put_user_profile returns a parsed UserProfile on 200.

        Validates: Requirements 1.5
        """
        response_body = json.dumps(
            {
                "userId": "Registry000001@naccdata.org",
                "firstName": "Alice",
                "lastName": "Smith",
                "email": "alice@example.com",
                "authEmail": "alice@institution.edu",
                "active": True,
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        request = UserProfileRequest(
            first_name="Alice",
            last_name="Smith",
            email="alice@example.com",
            auth_email="alice@institution.edu",
            active=True,
        )
        result = client.put_user_profile(
            profile_user_id="Registry000001@naccdata.org",
            request=request,
        )

        assert isinstance(result, UserProfile)
        assert result.user_id == "Registry000001@naccdata.org"
        assert result.first_name == "Alice"
        assert result.last_name == "Smith"
        assert result.email == "alice@example.com"
        assert result.auth_email == "alice@institution.edu"
        assert result.active is True


class TestGetUserProfile:
    """Tests for the get_user_profile method."""

    def test_get_user_profile_raises_not_found_error_on_404(self) -> None:
        """Verify get_user_profile raises NotFoundError on 404.

        Validates: Requirements 1.7
        """
        transport = MockTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with pytest.raises(NotFoundError) as exc_info:
            client.get_user_profile(
                profile_user_id="Registry000001@naccdata.org",
            )

        assert "Registry000001@naccdata.org" in exc_info.value.message


class TestDeleteUserProfile:
    """Tests for the delete_user_profile method."""

    def test_delete_user_profile_returns_none_on_204(self) -> None:
        """Verify delete_user_profile returns None on 204.

        Validates: Requirements 1.8
        """
        transport = MockTransport(MockResponse(status_code=204, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        # delete_user_profile returns None; just verify no exception
        client.delete_user_profile(
            profile_user_id="Registry000001@naccdata.org",
        )

    def test_delete_user_profile_returns_none_on_404(self) -> None:
        """Verify delete_user_profile returns None on 404 (idempotent).

        Validates: Requirements 1.9
        """
        transport = MockTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        # delete_user_profile returns None; just verify no exception
        client.delete_user_profile(
            profile_user_id="Registry000001@naccdata.org",
        )


class TestRetryOn503:
    """Tests for retry-on-503 integration with profile methods."""

    def test_put_user_profile_retries_on_503_then_succeeds(self) -> None:
        """Verify put_user_profile retries on 503 and succeeds on 200.

        Validates: Requirements 1.10
        """
        success_body = json.dumps(
            {
                "userId": "Registry000001@naccdata.org",
                "firstName": "Bob",
                "lastName": "Jones",
                "email": None,
                "authEmail": "bob@institution.edu",
                "active": True,
            }
        ).encode()
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(status_code=200, body=success_body),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        request = UserProfileRequest(
            first_name="Bob",
            last_name="Jones",
            auth_email="bob@institution.edu",
            active=True,
        )
        result = client.put_user_profile(
            profile_user_id="Registry000001@naccdata.org",
            request=request,
        )

        assert isinstance(result, UserProfile)
        assert result.user_id == "Registry000001@naccdata.org"
        assert result.first_name == "Bob"
        # Initial request + 1 retry = 2 total
        assert len(transport.requests) == 2
