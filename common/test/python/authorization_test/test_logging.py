"""Unit tests for health check and logging behavior.

Task 7.2: Test health check request construction and response parsing,
503 on health returns unhealthy result, and logging at appropriate levels.

Requirements: 7.1, 7.2, 7.3, 10.1, 10.2, 10.3, 10.4, 10.5
"""

import json
import logging

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ServiceUnavailableError, UnexpectedError
from authorization.models import HealthResult

from .conftest import MockResponse, MockTransport, no_sleep


class TestHealthCheckRequestConstruction:
    """Tests for health check request construction.

    Validates: Requirement 7.1
    """

    def test_health_check_sends_get_to_health_endpoint(self) -> None:
        """Health check sends GET /health with no body or query params."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "healthy", "authorizationEngine": "connected"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        client.health_check()

        assert len(transport.requests) == 1
        method, path, body, query_params = transport.requests[0]
        assert method == "GET"
        assert path == "/health"
        assert body is None
        assert query_params is None


class TestHealthCheckResponseParsing:
    """Tests for health check response parsing.

    Validates: Requirement 7.2
    """

    def test_healthy_response_parsed_correctly(self) -> None:
        """200 with healthy status returns correct HealthResult."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "healthy", "authorizationEngine": "connected"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.health_check()

        assert isinstance(result, HealthResult)
        assert result.status == "healthy"
        assert result.authorization_engine == "connected"

    def test_degraded_response_parsed_correctly(self) -> None:
        """200 with degraded status returns correct HealthResult."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "degraded", "authorizationEngine": "unreachable"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.health_check()

        assert result.status == "degraded"
        assert result.authorization_engine == "unreachable"


class TestHealthCheck503Behavior:
    """Tests for health check 503 behavior.

    Validates: Requirement 7.3
    """

    def test_503_returns_unhealthy_result(self) -> None:
        """503 returns HealthResult(status='unhealthy') without exception."""
        response = MockResponse(status_code=503, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        result = client.health_check()

        assert isinstance(result, HealthResult)
        assert result.status == "unhealthy"

    def test_503_does_not_retry(self) -> None:
        """Health check does NOT retry on 503 (unlike other methods)."""
        response = MockResponse(status_code=503, body=b"")
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, max_retries=3, sleep=no_sleep)

        client.health_check()

        assert len(transport.requests) == 1


class TestLoggingDebugSuccess:
    """Tests for debug-level logging on successful operations.

    Validates: Requirements 10.1, 10.5
    """

    def test_grant_success_logs_at_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful grant logs at DEBUG level."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-1",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=201, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("Grant succeeded" in msg for msg in debug_messages)

    def test_revoke_success_logs_at_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful revoke logs at DEBUG level."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-1",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=200, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("Revoke succeeded" in msg for msg in debug_messages)

    def test_health_check_success_logs_at_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful health check logs at DEBUG level."""
        response = MockResponse(
            status_code=200,
            body=b'{"status": "healthy", "authorizationEngine": "connected"}',
        )
        transport = MockTransport(response)
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.health_check()

        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("Health check succeeded" in msg for msg in debug_messages)


class TestLoggingDebugIdempotent:
    """Tests for debug-level logging on idempotent outcomes.

    Validates: Requirement 10.2
    """

    def test_grant_409_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Grant 409 (already exists) logs at DEBUG level."""
        transport = MockTransport(MockResponse(status_code=409, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("idempotent" in msg.lower() for msg in debug_messages)

    def test_revoke_404_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Revoke 404 (not found) logs at DEBUG level."""
        transport = MockTransport(MockResponse(status_code=404, body=b""))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.revoke(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("idempotent" in msg.lower() for msg in debug_messages)


class TestLoggingWarningRetry:
    """Tests for warning-level logging on retry attempts.

    Validates: Requirement 10.3
    """

    def test_retry_logs_at_warning_with_attempt_and_duration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Retry attempts log at WARNING with attempt number and wait."""
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(status_code=503, body=b""),
            MockResponse(
                status_code=200,
                body=json.dumps(
                    {
                        "userId": "user@example.com",
                        "relation": "member",
                        "type": "study",
                        "resourceId": "study-1",
                    }
                ).encode(),
            ),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(
            transport=transport,
            max_retries=3,
            base_backoff=1.0,
            sleep=no_sleep,
        )

        with caplog.at_level(logging.WARNING, logger="authorization.retry"):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        # Should have 2 retry warnings
        # (first 503 triggers retry 1, second triggers retry 2)
        assert len(warning_messages) >= 2
        # Check that attempt numbers are included
        assert any("1" in msg for msg in warning_messages)
        assert any("2" in msg for msg in warning_messages)

    def test_exhausted_retries_log_all_attempts(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """All retry attempts are logged before raising error."""
        transport = MockTransport(MockResponse(status_code=503, body=b""))
        client = AuthorizationClient(
            transport=transport,
            max_retries=3,
            base_backoff=1.0,
            sleep=no_sleep,
        )

        with (
            caplog.at_level(logging.WARNING, logger="authorization.retry"),
            pytest.raises(ServiceUnavailableError),
        ):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_messages) == 3


class TestLoggingErrorOnFailure:
    """Tests for error-level logging on non-retriable errors.

    Validates: Requirement 10.4
    """

    def test_unexpected_error_logs_at_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-retriable error logs at ERROR level."""
        error_body = json.dumps({"message": "Forbidden"}).encode()
        transport = MockTransport(MockResponse(status_code=403, body=error_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with (
            caplog.at_level(logging.ERROR, logger="authorization.client"),
            pytest.raises(UnexpectedError),
        ):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        error_messages = [
            r.message for r in caplog.records if r.levelno == logging.ERROR
        ]
        assert len(error_messages) >= 1
        assert any(
            "403" in msg or "unexpected" in msg.lower() for msg in error_messages
        )


class TestLoggingUsesNamedLogger:
    """Tests for named logger usage.

    Validates: Requirement 10.5
    """

    def test_client_uses_named_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        """Client logs use the 'authorization.client' logger name."""
        response_body = json.dumps(
            {
                "userId": "user@example.com",
                "relation": "member",
                "type": "study",
                "resourceId": "study-1",
            }
        ).encode()
        transport = MockTransport(MockResponse(status_code=201, body=response_body))
        client = AuthorizationClient(transport=transport, sleep=no_sleep)

        with caplog.at_level(logging.DEBUG, logger="authorization.client"):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        logger_names = {r.name for r in caplog.records}
        assert "authorization.client" in logger_names

    def test_retry_uses_named_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        """Retry logic uses the 'authorization.retry' logger name."""
        responses = [
            MockResponse(status_code=503, body=b""),
            MockResponse(
                status_code=200,
                body=json.dumps(
                    {
                        "userId": "user@example.com",
                        "relation": "member",
                        "type": "study",
                        "resourceId": "study-1",
                    }
                ).encode(),
            ),
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(
            transport=transport,
            max_retries=3,
            base_backoff=1.0,
            sleep=no_sleep,
        )

        with caplog.at_level(logging.WARNING, logger="authorization.retry"):
            client.grant(
                user_id="user@example.com",
                resource_type="study",
                resource_id="study-1",
                relation="member",
            )

        logger_names = {r.name for r in caplog.records}
        assert "authorization.retry" in logger_names
