"""Unit tests for PHITaskProcessor."""

from unittest.mock import Mock

import pytest
from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from phi_coordinator_app.processor import Outcome, PHITaskProcessor
from reader_tasks.reader_task_client import (
    FormResponseModel,
    ReaderTaskClient,
    ReaderTaskModel,
)

CONFIRMED = "PHI-Confirmed"
NOT_FOUND = "PHI-Not-Found"
FOUND = "PHI-Found"
MARK = "phi-coordinator"


def make_task(tags: list[str] | None = None, with_file: bool = True) -> ReaderTaskModel:
    data: dict = {
        "_id": "t1",
        "task_id": "R-1-1",
        "status": "Complete",
        "protocol_id": "p1",
        "form_id": "f1",
        "tags": tags or [],
    }
    if with_file:
        data["parent"] = {"id": "file1", "type": "file"}
        data["parents"] = {"file": "file1", "acquisition": "acq1"}
    return ReaderTaskModel.model_validate(data)


def make_response(data: dict, revision: int = 1) -> FormResponseModel:
    return FormResponseModel.model_validate(
        {
            "_id": "r1",
            "task_id": "t1",
            "form_id": "f1",
            "response_data": data,
            "revision": revision,
        }
    )


# A 'yes' answer is only confirmed when the acknowledgment checkbox is checked.
YES = {"phi_radio": "yes", "delete_ack": True}
NO = {"phi_radio": "no"}


def make_file(tags: list[str]) -> Mock:
    file = Mock(spec=FileEntry)
    file.name = "image.dicom.zip"
    file.tags = list(tags)
    return file


def make_processor(
    proxy: Mock,
    reader_tasks: Mock,
    *,
    reset: bool = True,
    dry_run: bool = False,
    ack_key: str = "delete_ack",
) -> PHITaskProcessor:
    return PHITaskProcessor(
        proxy=proxy,
        reader_tasks=reader_tasks,
        answer_key="phi_radio",
        ack_key=ack_key,
        found_tag=FOUND,
        confirmed_tag=CONFIRMED,
        not_found_tag=NOT_FOUND,
        coordinated_tag=MARK,
        reset_on_missing_data=reset,
        dry_run=dry_run,
    )


@pytest.fixture
def proxy() -> Mock:
    return Mock(spec=FlywheelProxy)


@pytest.fixture
def reader_tasks() -> Mock:
    return Mock(spec=ReaderTaskClient)


def test_yes_confirms_and_marks_task_last(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(YES)]

    manager = Mock()
    manager.attach_mock(file, "file")
    manager.attach_mock(reader_tasks, "rt")

    outcome = make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    assert outcome is Outcome.CONFIRMED
    file.add_tag.assert_called_once_with(CONFIRMED)
    file.delete_tag.assert_called_once_with(FOUND)
    reader_tasks.add_task_tag.assert_called_once()
    # Marker must be written only AFTER the file tag changes.
    names = [c[0] for c in manager.mock_calls]
    assert names.index("rt.add_task_tag") > names.index("file.add_tag")
    assert names.index("rt.add_task_tag") > names.index("file.delete_tag")


def test_no_adds_not_found(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(NO)]

    outcome = make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    assert outcome is Outcome.NOT_FOUND
    file.add_tag.assert_called_once_with(NOT_FOUND)
    file.delete_tag.assert_called_once_with(FOUND)


def test_opposite_resolution_tag_removed(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND, NOT_FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(YES)]

    make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    file.add_tag.assert_called_once_with(CONFIRMED)
    assert {c.args[0] for c in file.delete_tag.call_args_list} == {FOUND, NOT_FOUND}


def test_already_resolved_makes_no_file_writes_but_marks(
    proxy: Mock, reader_tasks: Mock
) -> None:
    file = make_file([CONFIRMED])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(YES)]

    outcome = make_processor(proxy, reader_tasks).resolve(make_task())

    assert outcome is Outcome.CONFIRMED
    file.add_tag.assert_not_called()
    file.delete_tag.assert_not_called()
    reader_tasks.add_task_tag.assert_called_once()


def test_uses_latest_response_by_revision(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [
        make_response(NO, revision=1),
        make_response(YES, revision=3),
    ]

    outcome = make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    assert outcome is Outcome.CONFIRMED


def test_missing_answer_resets_and_clears(proxy: Mock, reader_tasks: Mock) -> None:
    proxy.get_file.return_value = make_file([FOUND])
    reader_tasks.get_responses.return_value = [make_response({})]

    processor = make_processor(proxy, reader_tasks, reset=True)
    outcome = processor.resolve(make_task([FOUND]))

    assert outcome is Outcome.RESET
    reader_tasks.set_task_status.assert_called_once_with("t1", "Todo")
    reader_tasks.clear_response.assert_called_once_with("r1")
    reader_tasks.add_task_tag.assert_not_called()


def test_missing_answer_skips_when_reset_disabled(
    proxy: Mock, reader_tasks: Mock
) -> None:
    proxy.get_file.return_value = make_file([FOUND])
    reader_tasks.get_responses.return_value = []

    processor = make_processor(proxy, reader_tasks, reset=False)
    outcome = processor.resolve(make_task([FOUND]))

    assert outcome is Outcome.SKIPPED
    reader_tasks.set_task_status.assert_not_called()
    reader_tasks.add_task_tag.assert_not_called()


def test_no_file_id_is_skipped(proxy: Mock, reader_tasks: Mock) -> None:
    reader_tasks.get_responses.return_value = [make_response({"phi_radio": "yes"})]

    outcome = make_processor(proxy, reader_tasks).resolve(make_task(with_file=False))

    assert outcome is Outcome.SKIPPED
    proxy.get_file.assert_not_called()


def test_dry_run_makes_no_mutations(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(YES)]

    processor = make_processor(proxy, reader_tasks, dry_run=True)
    outcome = processor.resolve(make_task([FOUND]))

    assert outcome is Outcome.CONFIRMED
    file.add_tag.assert_not_called()
    file.delete_tag.assert_not_called()
    reader_tasks.add_task_tag.assert_not_called()


def test_file_tag_failure_prevents_marker(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    file.add_tag.side_effect = RuntimeError("api boom")
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response(YES)]

    with pytest.raises(RuntimeError):
        make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    reader_tasks.add_task_tag.assert_not_called()


def test_yes_without_ack_resets_and_clears(proxy: Mock, reader_tasks: Mock) -> None:
    reader_tasks.get_responses.return_value = [make_response({"phi_radio": "yes"})]

    processor = make_processor(proxy, reader_tasks, reset=True)
    outcome = processor.resolve(make_task([FOUND]))

    assert outcome is Outcome.RESET
    # The file is never fetched or tagged when the acknowledgment is missing.
    proxy.get_file.assert_not_called()
    reader_tasks.set_task_status.assert_called_once_with("t1", "Todo")
    reader_tasks.clear_response.assert_called_once_with("r1")
    reader_tasks.add_task_tag.assert_not_called()


def test_yes_with_unchecked_ack_resets(proxy: Mock, reader_tasks: Mock) -> None:
    reader_tasks.get_responses.return_value = [
        make_response({"phi_radio": "yes", "delete_ack": False})
    ]

    outcome = make_processor(proxy, reader_tasks, reset=True).resolve(
        make_task([FOUND])
    )

    assert outcome is Outcome.RESET
    proxy.get_file.assert_not_called()
    reader_tasks.clear_response.assert_called_once_with("r1")


def test_yes_without_ack_skips_when_reset_disabled(
    proxy: Mock, reader_tasks: Mock
) -> None:
    reader_tasks.get_responses.return_value = [make_response({"phi_radio": "yes"})]

    outcome = make_processor(proxy, reader_tasks, reset=False).resolve(
        make_task([FOUND])
    )

    assert outcome is Outcome.SKIPPED
    proxy.get_file.assert_not_called()
    reader_tasks.set_task_status.assert_not_called()
    reader_tasks.add_task_tag.assert_not_called()


def test_ack_accepts_string_true(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [
        make_response({"phi_radio": "yes", "delete_ack": "true"})
    ]

    outcome = make_processor(proxy, reader_tasks).resolve(make_task([FOUND]))

    assert outcome is Outcome.CONFIRMED
    file.add_tag.assert_called_once_with(CONFIRMED)


def test_empty_ack_key_disables_requirement(proxy: Mock, reader_tasks: Mock) -> None:
    file = make_file([FOUND])
    proxy.get_file.return_value = file
    reader_tasks.get_responses.return_value = [make_response({"phi_radio": "yes"})]

    outcome = make_processor(proxy, reader_tasks, ack_key="").resolve(
        make_task([FOUND])
    )

    assert outcome is Outcome.CONFIRMED
    file.add_tag.assert_called_once_with(CONFIRMED)
