"""Tests serialization of enrollment/transfer form data."""

from datetime import datetime
from typing import Dict

import pytest
from dates.form_dates import DATE_FORMATS, DateFormatException, parse_date
from enrollment.enrollment_transfer import EnrollmentRecord, TransferRecord
from identifiers.model import CenterIdentifiers
from pydantic import ValidationError


@pytest.fixture
def bad_date_row():
    yield {
        'adcid': 0,
        'ptid': "123456",
        'naccid': "000000",
        'frmdate_enrl': "10062024",
        'guid': '(*#$@@##)'
    }


# pylint: disable=(too-few-public-methods)
class TestEnrollmentSerialization:
    """Tests for enrollment serialization."""

    # pylint: disable=(no-self-use)
    def test_create(self):
        """Test create_from method."""
        row: Dict[str, int | str] = {
            'adcid': 0,
            'ptid': "123456",
            'frmdate_enrl': "2024-06-10",
            'guid': ''
        }
        guid = row.get('guid')
        try:
            enroll_date = parse_date(date_string=str(row['frmdate_enrl']),
                                     formats=DATE_FORMATS)
        except DateFormatException:
            assert False, 'date should be OK'  # noqa: B011
        try:
            record = EnrollmentRecord(center_identifier=CenterIdentifiers(
                adcid=int(row['adcid']), ptid=str(row['ptid'])),
                                      guid=str(guid) if guid else None,
                                      naccid=None,
                                      start_date=enroll_date)
            assert record
        except ValidationError:
            assert False, "row should be valid, got {str(e)}"  # noqa: B011

    def test_create_error(self, bad_date_row):
        """Test create_from method."""
        row = bad_date_row
        guid = row.get('guid', None)
        try:
            parse_date(date_string=row['frmdate_enrl'], formats=DATE_FORMATS)
        except DateFormatException:
            assert True, 'date is invalid'

        try:
            EnrollmentRecord(center_identifier=CenterIdentifiers(
                adcid=row['adcid'], ptid=row['ptid']),
                             guid=guid if guid else None,
                             naccid=None,
                             start_date=row['frmdate_enrl'])
            assert False, "date is invalid should fail"  # noqa: B011
        except ValidationError as e:
            assert True, "date is invalid"
            assert e.error_count() == 1
            for error in e.errors():
                print(error)
                assert error['type'] == 'string_pattern_mismatch' or error[
                    'type'] == 'datetime_from_date_parsing'
                if error['type'] == 'string_pattern_mismatch':
                    assert error['loc'][0] == 'guid'


class TestTransferRecord:

    def test_complete_record(self):
        transfer = {
            "date": datetime.today(),
            "initials": "bk",
            "center_identifiers": {
                "adcid": 0,
                "ptid": "11111"
            },
            "previous_identifiers": {
                "adcid": 0,
                "ptid": "22222"
            },
            "naccid": "NACC000000"
        }
        try:
            assert TransferRecord.model_validate(transfer)
        except ValidationError:
            assert False, "transfer record validation failed"  # noqa: B011

    def test_incomplete_record(self):
        transfer = {
            "date": datetime.today(),
            "initials": "bk",
            "center_identifiers": {
                "adcid": 0,
                "ptid": "11111"
            }
        }
        try:
            assert TransferRecord.model_validate(transfer)
        except ValidationError:
            assert False, "transfer record validation failed"  # noqa: B011
