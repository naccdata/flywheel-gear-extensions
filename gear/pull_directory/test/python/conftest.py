"""Shared fixtures for pull_directory gear tests."""

from io import StringIO
from typing import Any
from unittest.mock import Mock

import pytest
from inputs.parameter_store import ParameterError


class MockParameterStore:
    """Mock ParameterStore for testing.

    Supports configurable REDCap parameters, notification parameters,
    and support emails with sensible defaults.
    """

    def __init__(
        self,
        redcap_params: dict[str, str] | None = None,
        support_emails: list[str] | None = None,
        sender_params: dict[str, str] | None = None,
    ):
        self.redcap_params = redcap_params or {
            "url": "https://redcap.test",
            "token": "test_token",
        }
        self.support_emails = support_emails or ["support@example.com"]
        self.sender_params = sender_params or {"sender": "noreply@example.com"}

    def get_parameters(self, param_type: Any, parameter_path: str) -> dict[str, str]:
        """Mock get_parameters."""
        if not self.redcap_params:
            raise ParameterError("REDCap parameters not found")
        return self.redcap_params

    def get_support_emails(self, path: str) -> list[str]:
        """Mock get_support_emails."""
        if not self.support_emails:
            raise ParameterError("Support emails not found")
        return self.support_emails

    def get_notification_parameters(self, path: str) -> dict[str, str]:
        """Mock get_notification_parameters."""
        if not self.sender_params:
            raise ParameterError("Notification parameters not found")
        return {
            "sender": self.sender_params.get("sender", "noreply@example.com"),
            "support_emails": ",".join(self.support_emails),
        }


class MockGearContext:
    """Mock GearContext for testing.

    Provides mock config, destination, client, and output support.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        destination: dict[str, str] | None = None,
    ):
        self.config_opts = config or {
            "parameter_path": "/directory/test",
            "user_file": "users.yaml",
            "notifications_path": "/prod/notifications",
        }
        self.destination_dict = destination or {
            "type": "project",
            "id": "test_project",
        }
        self.output_content: str | None = None
        self.client = Mock()
        self._config = Mock()
        self._config.opts = self.config_opts
        self._config.destination = self.destination_dict

    @property
    def config(self) -> Mock:
        """Mock config property that returns a Config object."""
        return self._config

    def open_output(
        self, filename: str, mode: str = "w", encoding: str = "utf-8"
    ) -> Any:
        """Mock open_output context manager."""

        class MockFile:
            def __init__(self, context: "MockGearContext"):
                self.context = context
                self.buffer = StringIO()

            def __enter__(self) -> StringIO:
                return self.buffer

            def __exit__(
                self,
                exc_type: Any,
                exc_val: Any,
                exc_tb: Any,
            ) -> None:
                self.context.output_content = self.buffer.getvalue()
                self.buffer.close()

        return MockFile(self)


@pytest.fixture
def mock_parameter_store() -> MockParameterStore:
    """Fixture providing a MockParameterStore with default parameters."""
    return MockParameterStore()


@pytest.fixture
def mock_context() -> MockGearContext:
    """Fixture providing a MockGearContext with default configuration."""
    return MockGearContext()
