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
    """Create a mock FlywheelProxy returned by the client.

    The destination container resolves into "test-group" by default, so
    that the cross-group guard passes for the default visitor. Tests
    covering the guard override this via ``set_destination_group``.
    """
    proxy = MagicMock()
    mock_client.get_proxy.return_value = proxy
    set_destination_group(proxy, "test-group")
    return proxy


def set_destination_group(mock_proxy: MagicMock, group_id: str) -> None:
    """Wires the mock proxy so the job's destination resolves into
    ``group_id``."""
    destination_container = MagicMock()
    destination_container.parents.group = group_id
    mock_proxy.get_container_by_id.return_value = destination_container


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
    context.manifest.name = "center-form-export"
    context.config.destination = {"type": "project", "id": "dest-project-id"}
    return context
