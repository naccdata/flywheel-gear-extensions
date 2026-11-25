"""Shared fixtures and helpers for the LONI receipt metadata tests."""

import io
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from unittest.mock import Mock

import pytest
from flywheel.rest import ApiException

from loni_receipt_metadata_app.main import ResolvedFile, TargetWriteError
from loni_receipt_metadata_app.receipt import Receipt, parse_receipt
from test_mocks.mock_flywheel import (
    MockAcquisition,
    MockFlywheelProxy,
    MockParents,
    create_mock_acquisition_file,
)

DATA_DIR = Path(__file__).parents[3] / "data"


def file_id(number: int) -> str:
    """Fake 24-hex file ID used in the data fixtures."""
    return f"a1b2c3d4e5f6a1b2c3d4e5{number:02x}"


def load_receipt(name: str) -> Receipt:
    """Parses the named receipt fixture from the gear's data directory."""
    text = (DATA_DIR / name).read_text(encoding="utf-8")
    return parse_receipt(name, io.StringIO(text, newline=""))


class RecordingTarget:
    """AcquisitionTarget that records calls and can fail on request."""

    def __init__(
        self,
        label: str = "acq",
        *,
        fail_write: bool = False,
        fail_copy: bool = False,
    ) -> None:
        self._label = label
        self.fail_write = fail_write
        self.fail_copy = fail_copy
        self.writes: List[Mapping[str, Dict[str, Any]]] = []
        self.copies: List[Tuple[str, str]] = []

    @property
    def label(self) -> str:
        return self._label

    def write_upload_loni(self, entries: Mapping[str, Dict[str, Any]]) -> None:
        if self.fail_write:
            raise TargetWriteError("write failed")
        self.writes.append(entries)

    def attach_receipt_copy(self, name: str, contents: str) -> None:
        if self.fail_copy:
            raise TargetWriteError("copy failed")
        self.copies.append((name, contents))


class FakeResolver:
    """FileResolver backed by a dictionary; unknown IDs do not resolve."""

    def __init__(self) -> None:
        self.__resolved: Dict[str, ResolvedFile] = {}
        self.requested: List[str] = []

    def add(
        self,
        fid: str,
        acquisition_id: str,
        target: RecordingTarget,
        file_name: Optional[str] = None,
    ) -> None:
        self.__resolved[fid] = ResolvedFile(
            file_id=fid,
            file_name=file_name or f"{fid}.dicom.zip",
            acquisition_id=acquisition_id,
            acquisition=target,
        )

    def resolve(self, fid: str) -> Optional[ResolvedFile]:
        self.requested.append(fid)
        return self.__resolved.get(fid)


@pytest.fixture
def resolver() -> FakeResolver:
    return FakeResolver()


def mock_client_with_tags(tags: Optional[List[str]]) -> Mock:
    """Mock client whose receipt has the tags; None makes get_file fail."""
    client = Mock(spec=["get_file", "add_file_tags", "delete_file_tags"])
    if tags is None:
        client.get_file.side_effect = ApiException(status=500, reason="boom")
    else:
        client.get_file.return_value = Mock(tags=list(tags))
    return client


class SharedStateAcquisition(MockAcquisition):
    """Acquisition whose reloaded copies share info and uploads with it.

    Lets tests observe writes made through a reloaded copy.
    """

    def reload(self, *args, **kwargs):
        return self.model_copy()


def create_acquisition(
    proxy: MockFlywheelProxy,
    acquisition_id: str,
    file_ids: Mapping[str, str],
    *,
    in_acquisition: bool = True,
) -> MockAcquisition:
    """Registers an acquisition with files (file ID -> name) on the proxy.

    Files are registered with the proxy; they are listed in the
    acquisition unless in_acquisition is False (a deleted file).
    """
    files = [
        create_mock_acquisition_file(name, fid, acquisition_id)
        for fid, name in file_ids.items()
    ]
    acquisition = SharedStateAcquisition(
        id=acquisition_id,
        label=f"label-{acquisition_id}",
        parents=MockParents(),
        files=files if in_acquisition else [],
    )
    proxy.add_container(acquisition_id, acquisition)
    for file in files:
        proxy.add_file(file)
    return acquisition
