"""Tests that BDS files are not curated for participants with UDS visits."""

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from nacc_attribute_deriver.symbol_table import SymbolTable

from attribute_curator_app.form_curator import FormCurator
from curator.scheduling_models import FileModel

CURATION_TAG = "curated"
BDS_FILENAME = "NACCXXX_BDS-RECORD-2001-01-01_BDS.json"
UDS_FILENAME = "NACCXXX_FORMS-VISIT-1_UDS.json"


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def curator(client: MagicMock) -> FormCurator:
    """Bare FormCurator with a mocked client and execute; not forcing curation,
    so files with the curation tag would normally be skipped without being
    executed."""
    instance = object.__new__(FormCurator)
    instance._Curator__curation_tag = CURATION_TAG  # type: ignore[attr-defined]  # noqa: SLF001
    instance._Curator__force_curate = False  # type: ignore[attr-defined]  # noqa: SLF001
    instance._Curator__sdk_client = client  # type: ignore[attr-defined]  # noqa: SLF001
    instance._Curator__failed_files = []  # type: ignore[attr-defined]  # noqa: SLF001
    instance._Curator__skipped_files = []  # type: ignore[attr-defined]  # noqa: SLF001
    instance.get_table = MagicMock(return_value=SymbolTable({}))  # type: ignore[method-assign]
    instance.execute = MagicMock(return_value=True)  # type: ignore[method-assign]
    return instance


def _file(
    filename: str,
    tags: Optional[List[str]] = None,
    curated_info: Optional[Dict[str, Any]] = None,
) -> FileModel:
    file_info: Dict[str, Any] = {"forms": {"json": {"visitdate": "2001-01-01"}}}
    file_info.update(curated_info or {})
    return FileModel(
        filename=filename,
        file_id=f"{filename}-id",
        file_info=file_info,
        file_tags=tags or [],
        session_id="session-id",
        modified_date=date(2001, 1, 1),
    )


def _subject_table(uds_visitdates: Optional[List[str]] = None) -> SymbolTable:
    if uds_visitdates is None:
        return SymbolTable({})

    return SymbolTable(
        {"working": {"cross-sectional": {"uds-visitdates": uds_visitdates}}}
    )


@pytest.mark.parametrize(
    "uds_visitdates,expected",
    [(["2020-01-01"], True), ([], False), (None, False)],
)
def test_subject_has_uds(uds_visitdates: Optional[List[str]], expected: bool) -> None:
    assert FormCurator.subject_has_uds(_subject_table(uds_visitdates)) is expected


def test_bds_skipped_when_subject_has_uds(
    curator: FormCurator, client: MagicMock
) -> None:
    """A BDS file curated in an earlier run is cleaned up and skipped, even
    though it has the curation tag and curation is not forced."""
    bds = _file(
        BDS_FILENAME,
        tags=[CURATION_TAG],
        curated_info={
            "derived": {"naccdage": 86},
            "resolved": {"sex": 1},
            "affiliate": 0,
        },
    )

    result = curator.curate_file(
        SimpleNamespace(label="NACC000001"),  # type: ignore[arg-type]
        _subject_table(["2020-01-01"]),
        bds,
    )

    # not processed, but not a failure either
    assert result is False
    curator.execute.assert_not_called()  # type: ignore[attr-defined]
    assert list(curator.skipped_files) == [BDS_FILENAME]
    assert not curator.failed_files

    # earlier curation and the curation tag are removed
    file_entry = client.get_file.return_value
    file_entry.delete_info.assert_called_once_with("derived", "resolved", "affiliate")
    file_entry.delete_tag.assert_called_once_with(CURATION_TAG)
    assert CURATION_TAG not in bds.file_tags


def test_uncurated_bds_skip_does_not_call_flywheel(
    curator: FormCurator, client: MagicMock
) -> None:
    """A BDS file with no earlier curation needs no Flywheel updates."""
    result = curator.curate_file(
        SimpleNamespace(label="NACC000001"),  # type: ignore[arg-type]
        _subject_table(["2020-01-01"]),
        _file(BDS_FILENAME),
    )

    assert result is False
    client.get_file.assert_not_called()
    assert list(curator.skipped_files) == [BDS_FILENAME]


def test_bds_curated_when_subject_has_no_uds(curator: FormCurator) -> None:
    result = curator.curate_file(
        SimpleNamespace(label="NACC000001"),  # type: ignore[arg-type]
        _subject_table(),
        _file(BDS_FILENAME),
    )

    assert result is True
    curator.execute.assert_called_once()  # type: ignore[attr-defined]
    assert not curator.skipped_files


def test_other_files_curated_when_subject_has_uds(curator: FormCurator) -> None:
    result = curator.curate_file(
        SimpleNamespace(label="NACC000001"),  # type: ignore[arg-type]
        _subject_table(["2020-01-01"]),
        _file(UDS_FILENAME),
    )

    assert result is True
    curator.execute.assert_called_once()  # type: ignore[attr-defined]
    assert not curator.skipped_files
