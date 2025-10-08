"""Tests for user directory."""

from typing import Any

import yaml
from pydantic import ValidationError
from users.authorizations import Activity, StudyAuthorizations
from users.nacc_directory import (
    ActiveUserEntry,
    DirectoryAuthorizations,
    PersonName,
    UserEntry,
)
from users.user_entry import UserEntryList


def create_user_entry(entry: dict[str, Any]) -> UserEntry:
    if entry.get("active"):
        try:
            return ActiveUserEntry.model_validate(entry)
        except ValidationError as error:
            raise AssertionError(error) from error

    try:
        return UserEntry.model_validate(entry)
    except ValidationError as error:
        raise AssertionError(error) from error


# pylint: disable=(no-self-use,too-few-public-methods)
class TestUserEntry:
    """Tests for UserEntry."""

    def test_inactive(self):
        """Tests for creating inactive objects."""
        entry = UserEntry(
            name=PersonName(first_name="ooly", last_name="puppy"),
            email="ools@that.org",
            auth_email="ools@that.org",
            active=False,
            approved=True,
        )
        try:
            dir_record = DirectoryAuthorizations.model_validate(
                {
                    "contact_company_name": "the center",
                    "adresearchctr": "0",
                    "firstname": "ooly",
                    "lastname": "puppy",
                    "email": "ools@that.org",
                    "fw_email": "ools@that.org",
                    "nacc_data_platform_access_information_complete": "2",
                    "archive_contact": "1",
                    "p30_naccid_enroll_access_level": "ViewAccess",
                    "web_report_access": "1",
                    "study_selections": "P30,AffiliatedStudy",
                    "scan_dashboard_access_level": "ViewAccess",
                    "p30_clin_forms_access_level": "SubmitAudit",
                    "p30_imaging_access_level": "SubmitAudit",
                    "p30_flbm_access_level": "SubmitAudit",
                    "p30_genetic_access_level": "ViewAccess",
                    "affiliated_study": "CLARiTI",
                    "leads_naccid_enroll_access_level": "",
                    "leads_clin_forms_access_level": "",
                    "dvcid_naccid_enroll_access_level": "",
                    "dvcid_clin_forms_access_level": "",
                    "allftd_naccid_enroll_access_level": "",
                    "allftd_clin_forms_access_level": "",
                    "dlbc_naccid_enroll_access_level": "",
                    "dlbc_clin_forms_access_level": "",
                    "cl_clin_forms_access_level": "NoAccess",
                    "cl_imaging_access_level": "NoAccess",
                    "cl_flbm_access_level": "ViewAccess",
                    "cl_pay_access_level": "NoAccess",
                    "cl_ror_access_level": "NoAccess",
                    "permissions_approval": "1",
                    "permissions_approval_date": "2025-08-13",
                    "permissions_approval_name": "disapprover",
                },
                by_alias=True,
            )
        except ValidationError as error:
            raise AssertionError(error) from error

        entry2 = dir_record.to_user_entry()
        assert entry == entry2
        entry_yaml = yaml.safe_dump(entry.as_dict())
        entry_object = yaml.safe_load(entry_yaml)
        print(entry_object)
        entry3 = create_user_entry(entry_object)
        assert entry == entry3

    def test_active(self):
        """Tests around creating objects."""
        entry = ActiveUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=[
                StudyAuthorizations(
                    study_id="adrc",
                    activities={
                        "enrollment": Activity(
                            datatype="enrollment", action="submit-audit"
                        ),
                        "form": Activity(datatype="form", action="submit-audit"),
                        "scan-analysis": Activity(
                            datatype="scan-analysis", action="view"
                        ),
                    },
                )
            ],
            active=True,
            approved=True,
            auth_email="chip_auth@theorg.org",
        )

        assert "submit-audit-form" in entry.authorizations[0]  # type: ignore

        # assumes study_id is adrc
        try:
            dir_record = DirectoryAuthorizations.model_validate(
                {
                    "contact_company_name": "the center",
                    "adresearchctr": "0",
                    "firstname": "chip",
                    "lastname": "puppy",
                    "email": "chip@theorg.org",
                    "fw_email": "chip_auth@theorg.org",
                    "archive_contact": "0",
                    "flywheel_access": "1",
                    "web_report_access": "1",
                    "study_selections": "P30,AffliatedStudy",
                    "scan_dashboard_access_level": "ViewAccess",
                    "p30_naccid_enroll_access_level": "SubmitAudit",
                    "p30_clin_forms_access_level": "SubmitAudit",
                    "p30_imaging_access_level": "NoAccess",
                    "p30_flbm_access_level": "NoAccess",
                    "p30_genetic_access_level": "NoAccess",
                    "affiliated_study": "CLARiTI",
                    "leads_naccid_enroll_access_level": "",
                    "leads_clin_forms_access_level": "",
                    "dvcid_naccid_enroll_access_level": "",
                    "dvcid_clin_forms_access_level": "",
                    "allftd_naccid_enroll_access_level": "",
                    "allftd_clin_forms_access_level": "",
                    "dlbc_naccid_enroll_access_level": "",
                    "dlbc_clin_forms_access_level": "",
                    "cl_clin_forms_access_level": "NoAccess",
                    "cl_imaging_access_level": "NoAccess",
                    "cl_flbm_access_level": "NoAccess",
                    "cl_pay_access_level": "NoAccess",
                    "cl_ror_access_level": "NoAccess",
                    "permissions_approval": "1",
                    "permissions_approval_date": "2025-08-13",
                    "permissions_approval_name": "approver",
                    "nacc_data_platform_access_information_complete": "2",
                },
                by_alias=True,
            )
        except ValidationError as error:
            raise AssertionError(error) from error

        entry2 = dir_record.to_user_entry()
        assert entry == entry2

        entry_yaml = yaml.safe_dump(entry.as_dict())
        entry_object = yaml.safe_load(entry_yaml)
        print(entry_object)
        entry3 = create_user_entry(entry_object)
        assert entry == entry3

    def test_list_serialization(self):
        user_list = UserEntryList([])

        entry1 = UserEntry(
            name=PersonName(first_name="ooly", last_name="puppy"),
            email="ools@that.org",
            auth_email="ools@that.org",
            active=False,
            approved=True,
        )
        user_list.append(entry1)
        entry2 = ActiveUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=[
                StudyAuthorizations(
                    study_id="dummy",
                    activities={
                        "form": Activity(datatype="form", action="submit-audit"),
                        "enrollment": Activity(
                            datatype="enrollment", action="submit-audit"
                        ),
                    },
                )
            ],
            active=True,
            approved=True,
            auth_email="chip_auth@theorg.org",
        )
        user_list.append(entry2)
        assert user_list.model_dump(serialize_as_any=True) == [
            entry1.model_dump(serialize_as_any=True),
            entry2.model_dump(serialize_as_any=True),
        ]
