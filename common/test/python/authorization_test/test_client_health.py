"""Tests for AuthorizationClient.health_check method."""

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ParseError, UnexpectedError
from authorization.models import HealthResult

from .conftest import MockResponse, MockTransport


class TestHealthCheck:
    """Tests for the health_check method."""

    def test_health_check_sends_get_to_health(self) -> None:
        """Verify health_check sends GET to /health."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "healthy", "authorizationEngine": "connected"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        client.health_check()

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "GET"
        assert path == "/health"
        assert body is None
        assert query_params is None

    def test_health_check_returns_health_result_on_200(self) -> None:
        """Verify 200 response is parsed into HealthResult."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "healthy", "authorizationEngine": "connected"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        result = client.health_check()

        assert isinstance(result, HealthResult)
        assert result.status == "healthy"
        assert result.authorization_engine == "connected"

    def test_health_check_returns_unhealthy_on_503(self) -> None:
        """Verify 503 returns HealthResult(status='unhealthy') without
        exception."""
        response = MockResponse(status_code=503, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        result = client.health_check()

        assert isinstance(result, HealthResult)
        assert result.status == "unhealthy"

    def test_health_check_raises_unexpected_error_on_other_status(self) -> None:
        """Verify non-200/non-503 status raises UnexpectedError."""
        response = MockResponse(status_code=500, body=b"Internal Server Error")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        with pytest.raises(UnexpectedError) as exc_info:
            client.health_check()

        assert exc_info.value.status_code == 500

    def test_health_check_raises_parse_error_on_invalid_json(self) -> None:
        """Verify malformed response body raises ParseError."""
        response = MockResponse(status_code=200, body=b"not valid json")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        with pytest.raises(ParseError) as exc_info:
            client.health_check()

        assert exc_info.value.raw_content == b"not valid json"

    def test_health_check_does_not_retry_on_503(self) -> None:
        """Verify health_check does NOT retry on 503 (unlike other methods)."""
        response = MockResponse(status_code=503, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport)

        client.health_check()

        # Should only make one request, no retries
        assert len(transport.requests) == 1
