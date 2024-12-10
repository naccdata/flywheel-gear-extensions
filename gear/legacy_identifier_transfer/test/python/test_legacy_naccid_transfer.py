"""Tests for the legacy-identifier-transfer gear """
import logging
import pytest
from datetime import datetime
from unittest.mock import Mock, PropertyMock, create_autospec
from pydantic import ValidationError
from identifiers.model import IdentifierObject
from outputs.errors import ErrorWriter
from enrollment.enrollment_project import EnrollmentProject
from legacy_identifier_transfer_app.main import process_legacy_identifiers
from unittest.mock import MagicMock
from legacy_identifier_transfer_app.main import LegacyEnrollmentBatch
from typing import Mapping


class TestLegacyEnrollmentBatch:
    def test_add_record_with_naccid(self):
        batch = LegacyEnrollmentBatch()
        record = MagicMock()
        record.naccid = '12345'
        batch.add(record)
        assert len(batch) == 1
        assert list(batch)[0] == record

    def test_add_record_without_naccid(self, caplog):
        batch = LegacyEnrollmentBatch()
        record = MagicMock()
        record.naccid = None
        with caplog.at_level(logging.WARNING):
            batch.add(record)
        assert len(batch) == 0
        assert 'Skipping record with missing NACCID' in caplog.text

    def test_len(self):
        batch = LegacyEnrollmentBatch()
        assert len(batch) == 0
        record1 = MagicMock()
        record1.naccid = '12345'
        record2 = MagicMock()
        record2.naccid = '67890'
        batch.add(record1)
        batch.add(record2)
        assert len(batch) == 2

    def test_iter(self):
        batch = LegacyEnrollmentBatch()
        record1 = MagicMock()
        record1.naccid = '12345'
        record2 = MagicMock()
        record2.naccid = '67890'
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
def mock_error_writer():
    return Mock(spec=ErrorWriter)


class TestProcessLegacyIdentifiers:
    def test_process_success(self, mock_enrollment_project, mock_error_writer):
        # Setup
        mock_enrollment_project.find_subject.return_value = None

        identifiers = {'NACC123456': IdentifierObject(
            naccid='NACC123456',
            adcid=123,
            ptid='PTID1',
            guid='GUID1',
            naccadc=123
        )}
        enrollment_date = datetime.now()

        # Execute
        result = process_legacy_identifiers(
            identifiers=identifiers,
            enrollment_date=enrollment_date,
            enrollment_project=mock_enrollment_project,
            error_writer=mock_error_writer
        )

        # Assert
        assert result is True
        assert mock_error_writer.write.call_count == 0

    def test_process_naccid_mismatch(self, mock_enrollment_project, mock_error_writer):
        # Setup
        identifiers = {'NACC123456': IdentifierObject(
            naccid='NACC654321', adcid=123, ptid='PTID1', guid='GUID1', naccadc=123)}
        enrollment_date = datetime.now()

        # Execute
        result = process_legacy_identifiers(
            identifiers=identifiers,
            enrollment_date=enrollment_date,
            enrollment_project=mock_enrollment_project,
            error_writer=mock_error_writer
        )

        # Assert
        assert result is False
        mock_error_writer.write.assert_called_once()

    def test_process_validation_error(self, mock_enrollment_project, mock_error_writer):
        # Setup
        mock_identifier = Mock()
        mock_identifier.configure_mock(**{
            'naccid': 'NACC123456',
            'ptid': 'PTID1'
        })

        validation_error = ValidationError.from_exception_data(
            title='Validation Error',
            line_errors=[{
                'type': 'value_error',
                'loc': ('adcid',),
                'input': None,
                'ctx': {
                    'error': 'field required',
                },
            }]
        )

        type(mock_identifier).adcid = PropertyMock(
            side_effect=validation_error)

        identifiers = {'NACC123456': mock_identifier}
        enrollment_date = datetime.now()

        # Execute
        result = process_legacy_identifiers(
            identifiers=identifiers,
            enrollment_date=enrollment_date,
            enrollment_project=mock_enrollment_project,
            error_writer=mock_error_writer
        )

        # Assert
        assert result is False
        mock_error_writer.write.assert_called_once()

    def test_process_dry_run(self, mock_enrollment_project, mock_error_writer):
        # Setup
        mock_enrollment_project.find_subject.return_value = None

        mock_identifier = create_autospec(IdentifierObject)
        mock_identifier.configure_mock(**{
            'naccid': 'NACC654321',
            'adcid': 123,
            'ptid': 'PTID1',
            'guid': 'GUID1'
        })

        identifiers: Mapping[str, IdentifierObject] = {
            'NACC654321': mock_identifier
        }
        enrollment_date = datetime.now()

        # Execute
        result = process_legacy_identifiers(
            identifiers=identifiers,
            enrollment_date=enrollment_date,
            enrollment_project=mock_enrollment_project,
            error_writer=mock_error_writer,
            dry_run=True
        )

        # Assert
        assert result is True
        assert not mock_enrollment_project.add_subject.called
        assert mock_error_writer.write.call_count == 0
