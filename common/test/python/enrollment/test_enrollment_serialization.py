"""Tests serialization of enrollment/transfer form data."""

from datetime import datetime
from typing import Dict

import pytest
from dates.form_dates import (
    DATE_FORMATS,
    DateFormatException,
    parse_date,
)
from enrollment.enrollment_transfer import (
    Demographics,
    EnrollmentRecord,
    TransferRecord,
)
from identifiers.model import CenterIdentifiers
from pydantic import ValidationError


@pytest.fixture
def bad_date_row():
    yield {
        "adcid": 0,
        "ptid": "123456",
        "naccid": "000000",
        "frmdate_enrl": "10062024",
        "guid": "(*#$@@##)",
    }


# pylint: disable=(too-few-public-methods)


class TestEnrollmentSerialization:
    """Tests for enrollment serialization."""

    # pylint: disable=(no-self-use)
    def test_create(self):
        """Test create_from method."""
        row: Dict[str, int | str] = {
            "adcid": 0,
            "ptid": "123456",
            "frmdate_enrl": "2024-06-10",
            "guid": "",
        }
        guid = row.get("guid")
        try:
            enroll_date = parse_date(
                date_string=str(row["frmdate_enrl"]), formats=DATE_FORMATS
            )
        except DateFormatException:
            assert False, "date should be OK"  # noqa: B011
        try:
            record = EnrollmentRecord(
                center_identifier=CenterIdentifiers(
                    adcid=int(row["adcid"]), ptid=str(row["ptid"])
                ),
                guid=str(guid) if guid else None,
                naccid=None,
                start_date=enroll_date,
            )
            assert record
        except ValidationError:
            assert False, "row should be valid, got {str(e)}"  # noqa: B011

    def test_create_error(self, bad_date_row):
        """Test create_from method."""
        row = bad_date_row
        guid = row.get("guid", None)
        try:
            parse_date(date_string=row["frmdate_enrl"], formats=DATE_FORMATS)
        except DateFormatException:
            assert True, "date is invalid"

        try:
            EnrollmentRecord(
                center_identifier=CenterIdentifiers(
                    adcid=row["adcid"], ptid=row["ptid"]
                ),
                guid=guid if guid else None,
                naccid=None,
                start_date=row["frmdate_enrl"],
            )
            assert False, "date is invalid should fail"  # noqa: B011
        except ValidationError as e:
            assert True, "date is invalid"
            assert e.error_count() == 1
            for error in e.errors():
                print(error)
                assert (
                    error["type"] == "string_pattern_mismatch"
                    or error["type"] == "datetime_from_date_parsing"
                )
                if error["type"] == "string_pattern_mismatch":
                    assert error["loc"][0] == "guid"


class TestTransferRecord:
    def test_complete_record(self):
        row = {
            "adcid": 1,
            "ptid": "11111",
            "frmdate_enrl": "2025-01-10",
            "initials_enrl": "bk",
            "enrltype": 2,
            "enrleduc": 10,
            "enrlbirthyr": 2,
            "enrlbirthmo": 10,
            "guid": "TESTGUID1234",
            "naccid": "NACC000000",
            "oldadcid": 0,
            "oldptid": "22222",
            "enrlgenman": 1,
        }
        try:
            enroll_date = parse_date(
                date_string=str(row["frmdate_enrl"]), formats=DATE_FORMATS
            )
        except DateFormatException:
            assert False, "date should be OK"  # noqa: B011

        try:
            TransferRecord(
                status="pending",
                request_date=enroll_date,
                updated_date=datetime.now(),
                submitter="testuser@uw.edu",
                center_identifiers=CenterIdentifiers(
                    adcid=row["adcid"], ptid=row["ptid"]
                ),
                initials=row.get("initials_enrl"),
                previous_adcid=row["oldadcid"],
                previous_ptid=row.get("oldptid"),
                naccid=row.get("naccid"),
                guid=row.get("guid"),
                demographics=Demographics.create_from(row=row),
            )
        except ValidationError:
            assert False, "transfer record validation failed"  # noqa: B011

    def test_incomplete_record(self):
        row = {
            "adcid": 1,
            "ptid": "11111",
            "frmdate_enrl": "2025-01-10",
            "initials_enrl": "bk",
            "enrltype": 2,
            "enrleduc": 10,
            "enrlbirthyr": 2,
            "enrlbirthmo": 10,
            "guid": "",
            "naccid": "",
            "oldadcid": 0,
            "oldptid": "",
            "enrlgenman": 1,
            "enrlgenwoman": "",
        }

        try:
            enroll_date = parse_date(
                date_string=str(row["frmdate_enrl"]), formats=DATE_FORMATS
            )
        except DateFormatException:
            assert False, "date should be OK"  # noqa: B011

        try:
            TransferRecord(
                status="pending",
                request_date=enroll_date,
                updated_date=datetime.now(),
                submitter="testuser@uw.edu",
                center_identifiers=CenterIdentifiers(
                    adcid=row["adcid"], ptid=row["ptid"]
                ),
                initials=row.get("initials_enrl"),
                previous_adcid=row["oldadcid"],
                previous_ptid=row.get("oldptid"),
                naccid=row.get("naccid"),
                guid=row.get("guid"),
                demographics=Demographics.create_from(row=row),
            )
        except ValidationError:
            assert False, "transfer record validation failed"  # noqa: B011
