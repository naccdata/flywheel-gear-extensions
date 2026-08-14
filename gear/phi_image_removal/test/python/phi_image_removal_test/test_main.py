"""Unit tests for the PHI Image Removal main.run orchestration."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from phi_image_removal_app.main import run
from phi_image_removal_app.processor import Outcome


def _run(file: object, acquisition: object, dry_run: bool = False) -> bool:
    return run(
        file=file,  # type: ignore[arg-type]
        acquisition=acquisition,  # type: ignore[arg-type]
        gear_name="phi-image-removal",
        gear_version="0.0.1",
        confirmed_tag="PHI-Confirmed",
        tombstone_tag="PHI-Tombstone",
        dry_run=dry_run,
    )


@patch("phi_image_removal_app.main.PHIImageRemovalProcessor")
def test_returns_true_on_success(processor_cls: Mock) -> None:
    processor_cls.return_value.process.return_value = Outcome.REMOVED

    assert _run(SimpleNamespace(name="x.dicom.zip"), Mock()) is True
    processor_cls.return_value.process.assert_called_once()


@patch("phi_image_removal_app.main.PHIImageRemovalProcessor")
def test_returns_false_when_process_raises(processor_cls: Mock) -> None:
    processor_cls.return_value.process.side_effect = RuntimeError("boom")

    assert _run(SimpleNamespace(name="x.dicom.zip"), Mock()) is False
