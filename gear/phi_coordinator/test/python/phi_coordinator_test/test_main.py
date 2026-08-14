"""Unit tests for the PHI Coordinator main.run orchestration."""

from unittest.mock import Mock, patch

import pytest
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from phi_coordinator_app.main import run
from phi_coordinator_app.processor import Outcome
from reader_tasks.reader_task_client import ReaderTaskClient


def _run(proxy: Mock, reader_tasks: Mock, dry_run: bool = False) -> bool:
    return run(
        proxy=proxy,
        reader_tasks=reader_tasks,
        phi_protocol_label="default_image_pii_detector_protocol",
        answer_key="phi_radio",
        ack_key="delete_ack",
        found_tag="PHI-Found",
        confirmed_tag="PHI-Confirmed",
        not_found_tag="PHI-Not-Found",
        coordinated_tag="phi-coordinator",
        reset_on_missing_data=True,
        dry_run=dry_run,
    )


@pytest.fixture
def proxy() -> Mock:
    return Mock(spec=FlywheelProxy)


@pytest.fixture
def reader_tasks() -> Mock:
    return Mock(spec=ReaderTaskClient)


def test_no_protocols_returns_true_and_does_nothing(
    proxy: Mock, reader_tasks: Mock
) -> None:
    reader_tasks.find_protocols.return_value = []

    assert _run(proxy, reader_tasks) is True
    reader_tasks.iter_unprocessed_completed_tasks.assert_not_called()


@patch("phi_coordinator_app.main.PHITaskProcessor")
def test_processes_all_tasks_across_protocols(
    processor_cls: Mock, proxy: Mock, reader_tasks: Mock
) -> None:
    protocol = Mock(id="p1")
    reader_tasks.find_protocols.return_value = [protocol]
    reader_tasks.iter_unprocessed_completed_tasks.return_value = [
        Mock(task_id="R-1-1"),
        Mock(task_id="R-1-2"),
    ]
    processor_cls.return_value.resolve.side_effect = [
        Outcome.CONFIRMED,
        Outcome.NOT_FOUND,
    ]

    assert _run(proxy, reader_tasks) is True
    assert processor_cls.return_value.resolve.call_count == 2
    reader_tasks.iter_unprocessed_completed_tasks.assert_called_once_with(
        "p1", "phi-coordinator"
    )


@patch("phi_coordinator_app.main.PHITaskProcessor")
def test_error_is_isolated_and_returns_false(
    processor_cls: Mock, proxy: Mock, reader_tasks: Mock
) -> None:
    reader_tasks.find_protocols.return_value = [Mock(id="p1")]
    reader_tasks.iter_unprocessed_completed_tasks.return_value = [
        Mock(task_id="R-1-1"),
        Mock(task_id="R-1-2"),
    ]
    processor_cls.return_value.resolve.side_effect = [
        Outcome.CONFIRMED,
        RuntimeError("boom"),
    ]

    # One task fails, but both are attempted and the run reports failure.
    assert _run(proxy, reader_tasks) is False
    assert processor_cls.return_value.resolve.call_count == 2
