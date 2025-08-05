"""Tests for the legacy-identifier-transfer gear."""

import logging
from typing import Mapping
from unittest.mock import MagicMock, Mock, PropertyMock, create_autospec

import pytest
from enrollment.enrollment_project import EnrollmentProject
from identifiers.model import IdentifierObject
from keys.keys import FieldNames
from legacy_identifier_transfer_app.main import (
    LegacyEnrollmentCollection,
    process_legacy_identifiers,
)
from pydantic import ValidationError
from test_mocks.mock_forms_store import MockFormsStore

# global date field
DATE_FIELD = FieldNames.DATE_COLUMN


class TestLegacyEnrollmentBatch:
    def test_add_record_with_naccid(self):
        batch = LegacyEnrollmentCollection()
        record = MagicMock()
        record.naccid = "12345"
        batch.add(record)
        assert len(batch) == 1
        assert next(iter(batch)) == record

    def test_add_record_without_naccid(self, caplog):
        batch = LegacyEnrollmentCollection()
        record = MagicMock()
        record.naccid = None
        with caplog.at_level(logging.WARNING):
            batch.add(record)
        assert len(batch) == 0
        assert "Skipping record with missing NACCID" in caplog.text

    def test_len(self):
        batch = LegacyEnrollmentCollection()
        assert len(batch) == 0
        record1 = MagicMock()
        record1.naccid = "12345"
        record2 = MagicMock()
        record2.naccid = "67890"
        batch.add(record1)
        batch.add(record2)
        assert len(batch) == 2

    def test_iter(self):
        batch = LegacyEnrollmentCollection()
        record1 = MagicMock()
        record1.naccid = "12345"
        record2 = MagicMock()
        record2.naccid = "67890"
        batch.add(record1)
        batch.add(record2)
        records = list(batch)
        assert records == [record1, record2]


@pytest.fixture
def mock_enrollment_project():
    # Create mock with all required methods
    mock = Mock(spec=EnrollmentProject)
    # Add get_subject_by_identifier to available methods
    mock.get_subject_by_identifier = Mock(return_value=None)
    return mock


@pytest.fixture
def mock_form_store():
    forms_store = MockFormsStore(date_field=DATE_FIELD)

    for i in range(1, 5):
        record = {
            FieldNames.MODULE: "uds",
            FieldNames.FORMVER: "3.0",
            FieldNames.VISITNUM: "1",
            FieldNames.NACCID: f"NACC{100000 + i}",
            FieldNames.PTID: f"PTID{i}",
            FieldNames.PACKET: "I",
            DATE_FIELD: "2025-01-01",
        }

        forms_store.add_subject(
            subject_lbl=record[FieldNames.NACCID],
            form_data=record,
            file_name=f"{record[FieldNames.NACCID]}.json",
        )

    return forms_store


def test_process_success(mock_enrollment_project, mock_form_store):
    # Setup
    mock_enrollment_project.find_subject.return_value = None

    identifiers = {
        "NACC100001": IdentifierObject(
            naccid="NACC100001", adcid=123, ptid="PTID1", guid="GUID1", naccadc=123
        )
    }

    # Execute
    result = process_legacy_identifiers(
        identifiers=identifiers,
        forms_store=mock_form_store,
        enrollment_project=mock_enrollment_project,
        failed_ids=[],
    )

    # Assert
    assert result is True


def test_process_validation_error(mock_enrollment_project, mock_form_store):
    # Setup
    mock_identifier = Mock()
    mock_identifier.configure_mock(**{"naccid": "NACC100002", "ptid": "PTID2"})
    mock_enrollment_project.find_subject.return_value = None

    validation_error = ValidationError.from_exception_data(
        title="Validation Error",
        line_errors=[
            {
                "type": "value_error",
                "loc": ("adcid",),
                "input": None,
                "ctx": {
                    "error": "field required",
                },
            }
        ],
    )

    type(mock_identifier).adcid = PropertyMock(side_effect=validation_error)

    identifiers = {"NACC100002": mock_identifier}

    # Execute
    result = process_legacy_identifiers(
        identifiers=identifiers,
        forms_store=mock_form_store,
        enrollment_project=mock_enrollment_project,
        failed_ids=[],
    )

    # Assert
    assert result is False


def test_process_dry_run(mock_enrollment_project, mock_form_store):
    # Setup
    mock_enrollment_project.find_subject.return_value = None

    mock_identifier = create_autospec(IdentifierObject)
    mock_identifier.configure_mock(
        **{"naccid": "NACC100003", "adcid": 123, "ptid": "PTID3", "guid": "GUID3"}
    )

    identifiers: Mapping[str, IdentifierObject] = {"NACC100003": mock_identifier}

    # Execute
    result = process_legacy_identifiers(
        identifiers=identifiers,
        forms_store=mock_form_store,
        enrollment_project=mock_enrollment_project,
        failed_ids=[],
        dry_run=True,
    )

    # Assert
    assert result is True
    assert not mock_enrollment_project.add_subject.called
