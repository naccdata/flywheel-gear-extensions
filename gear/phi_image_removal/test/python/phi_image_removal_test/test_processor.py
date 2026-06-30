"""Unit tests for PHIImageRemovalProcessor."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flywheel import FileEntry
from flywheel.models.acquisition import Acquisition
from phi_image_removal_app.processor import (
    Outcome,
    PHIImageRemovalError,
    PHIImageRemovalProcessor,
)

CONFIRMED = "PHI-Confirmed"
TOMBSTONE = "PHI-Tombstone"


def make_file(tags: list[str]) -> FileEntry:
    return SimpleNamespace(  # type: ignore[return-value]
        name="NACC900026_MR.dicom.zip",
        tags=list(tags),
        file_id="file1",
        size=2048,
        type="dicom",
        mimetype="application/zip",
        modality="MR",
        classification=None,
        hash="deadbeef",
        version=1,
        created=None,
        modified=None,
        origin=None,
        info=None,
        parents=SimpleNamespace(
            group="g1",
            project="p1",
            subject="s1",
            session="ses1",
            acquisition="acq1",
        ),
    )


def make_processor(*, dry_run: bool = False) -> PHIImageRemovalProcessor:
    return PHIImageRemovalProcessor(
        gear_name="phi-image-removal",
        gear_version="0.0.1",
        confirmed_tag=CONFIRMED,
        tombstone_tag=TOMBSTONE,
        dry_run=dry_run,
    )


@pytest.fixture
def acquisition() -> Mock:
    acq = Mock(spec=Acquisition)
    acq.label = "acq-label"
    acq.reload.return_value = acq
    return acq


def test_confirmed_uploads_tags_then_deletes_in_order(acquisition: Mock) -> None:
    tombstone = Mock(spec=FileEntry)
    # First call is the existence check (None), second is post-upload retrieval.
    acquisition.get_file.side_effect = [None, tombstone]

    manager = Mock()
    manager.attach_mock(acquisition, "acq")
    manager.attach_mock(tombstone, "tomb")

    outcome = make_processor().process(
        file=make_file([CONFIRMED]), acquisition=acquisition
    )

    assert outcome is Outcome.REMOVED
    acquisition.upload_file.assert_called_once()
    tombstone.add_tag.assert_called_once_with(TOMBSTONE)
    acquisition.delete_file.assert_called_once_with("NACC900026_MR.dicom.zip")

    names = [call[0] for call in manager.mock_calls]
    assert names.index("acq.upload_file") < names.index("tomb.add_tag")
    assert names.index("tomb.add_tag") < names.index("acq.delete_file")


def test_uploaded_tombstone_named_with_json_extension(acquisition: Mock) -> None:
    tombstone = Mock(spec=FileEntry)
    acquisition.get_file.side_effect = [None, tombstone]

    make_processor().process(file=make_file([CONFIRMED]), acquisition=acquisition)

    file_spec = acquisition.upload_file.call_args.args[0]
    assert file_spec.name == "NACC900026_MR.json"


def test_missing_confirmed_tag_skips(acquisition: Mock) -> None:
    outcome = make_processor().process(
        file=make_file(["PHI-Found"]), acquisition=acquisition
    )

    assert outcome is Outcome.SKIPPED
    acquisition.get_file.assert_not_called()
    acquisition.upload_file.assert_not_called()
    acquisition.delete_file.assert_not_called()


def test_existing_tombstone_skips(acquisition: Mock) -> None:
    acquisition.get_file.return_value = Mock(spec=FileEntry)

    outcome = make_processor().process(
        file=make_file([CONFIRMED]), acquisition=acquisition
    )

    assert outcome is Outcome.SKIPPED
    acquisition.upload_file.assert_not_called()
    acquisition.delete_file.assert_not_called()


def test_dry_run_makes_no_mutations(acquisition: Mock) -> None:
    acquisition.get_file.return_value = None

    outcome = make_processor(dry_run=True).process(
        file=make_file([CONFIRMED]), acquisition=acquisition
    )

    assert outcome is Outcome.REMOVED
    acquisition.upload_file.assert_not_called()
    acquisition.delete_file.assert_not_called()


def test_missing_tombstone_after_upload_raises_and_keeps_original(
    acquisition: Mock,
) -> None:
    # Existence check None, then still None after upload + reload.
    acquisition.get_file.side_effect = [None, None]

    with pytest.raises(PHIImageRemovalError):
        make_processor().process(file=make_file([CONFIRMED]), acquisition=acquisition)

    # The original image is left in place when the tombstone is missing.
    acquisition.delete_file.assert_not_called()
