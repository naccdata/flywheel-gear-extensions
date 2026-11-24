"""Tests how curator.Curator records failed and skipped files."""

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from curator.curator import Curator
from curator.scheduling_models import FileModel


class DummyCurator(Curator):
    """Minimal concrete curator."""

    def execute(self, subject, file_model, table, scope) -> bool:  # type: ignore
        return True


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def curator(client: MagicMock) -> DummyCurator:
    instance = DummyCurator(dataview=None, curation_tag="curated")  # type: ignore[arg-type]
    instance._Curator__sdk_client = client  # type: ignore[attr-defined]  # noqa: SLF001
    return instance


def _file(tags: list[str]) -> FileModel:
    return FileModel(
        filename="NACCXXX_BDS-RECORD-2001-01-01_BDS.json",
        file_id="file-id",
        file_info={},
        file_tags=tags,
        session_id="session-id",
        modified_date=date(2001, 1, 1),
    )


def test_failed_file_reported(curator: DummyCurator) -> None:
    file_model = _file(["curated"])
    curator.handle_curation_failure(file_model, "boom")

    assert list(curator.failed_files) == [
        {"name": file_model.filename, "id": "file-id", "reason": "boom"}
    ]
    assert "curated" not in file_model.file_tags
    assert not curator.skipped_files


def test_failed_subject_reported(curator: DummyCurator) -> None:
    subject = SimpleNamespace(label="NACC000001", id="subject-id")
    curator.handle_curation_failure(subject, "boom")  # type: ignore[arg-type]

    assert list(curator.failed_files) == [
        {"name": "NACC000001", "id": "subject-id", "reason": "boom"}
    ]


def test_skipped_file_logged_not_reported(
    curator: DummyCurator, client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A skipped file is not a failure: it is logged and counted, but not
    written to the failure report."""
    file_model = _file(["curated", "other"])

    with caplog.at_level(logging.WARNING):
        curator.handle_curation_skipped(file_model, "not needed")

    assert list(curator.skipped_files) == [file_model.filename]
    assert not curator.failed_files
    assert f"Skipping {file_model.filename}: not needed" in caplog.text

    # curation tag removed both locally and in Flywheel
    assert file_model.file_tags == ["other"]
    client.get_file.return_value.delete_tag.assert_called_once_with("curated")


def test_skipped_untagged_file_does_not_call_flywheel(
    curator: DummyCurator, client: MagicMock
) -> None:
    curator.handle_curation_skipped(_file([]), "not needed")

    client.get_file.assert_not_called()
    assert len(curator.skipped_files) == 1
