"""Unit tests for client instantiation and configuration via factory.

Tests explicit URL parameter and empty URL raises ConfigurationError.
Tests default and custom max_retries/base_backoff.

Requirements: 1.1, 1.3
"""

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import ConfigurationError, ServiceUnavailableError
from authorization.factory import create_authorization_client

from .conftest import MockResponse


class TestFactoryExplicitUrl:
    """Tests for factory with explicit base_url parameter."""

    def test_explicit_url_creates_client(self) -> None:
        """Factory with explicit URL returns a configured client.

        Validates: Requirement 1.1
        """
        client = create_authorization_client(base_url="https://api.example.com/v1")
        assert isinstance(client, AuthorizationClient)


class TestFactoryMissingUrl:
    """Tests for factory when no URL is provided."""

    def test_empty_string_url_raises_configuration_error(self) -> None:
        """Factory raises ConfigurationError for empty string URL.

        Validates: Requirement 1.3
        """
        with pytest.raises(ConfigurationError):
            create_authorization_client(base_url="")


class TestFactoryRetryConfiguration:
    """Tests for custom max_retries and base_backoff values."""

    def test_default_retry_values(self) -> None:
        """Factory uses default max_retries=3 and base_backoff=1.0.

        Validates: Requirement 1.1
        """
        client = create_authorization_client(base_url="https://api.example.com")
        assert isinstance(client, AuthorizationClient)

    def test_custom_max_retries_affects_behavior(self) -> None:
        """Factory passes custom max_retries to client.

        Verifies by injecting a mock transport and observing retry count.

        Validates: Requirement 1.1
        """

        class CountingTransport:
            def __init__(self) -> None:
                self.call_count = 0

            def request(
                self,
                method: str,
                path: str,
                body: bytes | None = None,
                query_params: dict[str, str] | None = None,
            ) -> MockResponse:
                self.call_count += 1
                return MockResponse(status_code=503, body=b"")

        transport = CountingTransport()
        client = AuthorizationClient(
            transport=transport,
            max_retries=5,
            base_backoff=0.01,
            sleep=lambda _: None,
        )

        with pytest.raises(ServiceUnavailableError):
            client.grant(
                user_id="u",
                resource_type="study",
                resource_id="r",
                relation="member",
            )

        # Initial request + 5 retries = 6 total
        assert transport.call_count == 6

    def test_custom_base_backoff_affects_behavior(self) -> None:
        """Factory passes custom base_backoff to client.

        Verifies by capturing sleep durations.

        Validates: Requirement 1.1
        """

        class AlwaysFailTransport:
            def request(
                self,
                method: str,
                path: str,
                body: bytes | None = None,
                query_params: dict[str, str] | None = None,
            ) -> MockResponse:
                return MockResponse(status_code=503, body=b"")

        sleep_durations: list[float] = []

        def capture_sleep(duration: float) -> None:
            sleep_durations.append(duration)

        client = AuthorizationClient(
            transport=AlwaysFailTransport(),
            max_retries=3,
            base_backoff=2.0,
            sleep=capture_sleep,
        )

        with pytest.raises(ServiceUnavailableError):
            client.grant(
                user_id="u",
                resource_type="study",
                resource_id="r",
                relation="member",
            )

        # Backoff pattern: 2.0 * 2^0, 2.0 * 2^1, 2.0 * 2^2 = 2.0, 4.0, 8.0
        assert sleep_durations == [2.0, 4.0, 8.0]
