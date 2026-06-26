"""Shared fixtures for center_form_export tests."""

from contextlib import contextmanager
from io import StringIO
from unittest.mock import MagicMock

import pytest
from gear_execution.gear_execution import ClientWrapper


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock ClientWrapper."""
    return MagicMock(spec=ClientWrapper)


@pytest.fixture
def mock_proxy(mock_client: MagicMock) -> MagicMock:
    """Create a mock FlywheelProxy returned by the client."""
    proxy = MagicMock()
    mock_client.get_proxy.return_value = proxy
    return proxy


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock GearContext with open_output support."""
    context = MagicMock()

    @contextmanager
    def fake_open_output(filename, mode="w", encoding="utf-8"):
        buf = StringIO()
        yield buf
        context.output_files[filename] = buf.getvalue()

    context.output_files = {}
    context.open_output.side_effect = fake_open_output
    return context
