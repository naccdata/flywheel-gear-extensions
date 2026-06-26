"""Tests for user directory."""

from typing import Any

import yaml
from pydantic import ValidationError
from user_test.directory_test_utils import create_directory_entry
from users.authorizations import (
    Activity,
    Authorizations,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)
from users.nacc_directory import (
    CenterUserEntry,
    DirectoryAuthorizations,
    PersonName,
    UserEntry,
)
from users.user_entry import UserEntryList


def create_user_entry(entry: dict[str, Any]) -> UserEntry:
    if entry.get("active"):
        try:
            return CenterUserEntry.model_validate(entry)
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
                create_directory_entry(
                    contact_company_name="the center",
                    adresearchctr="0",
                    adcid="0",
                    firstname="ooly",
                    lastname="puppy",
                    email="ools@that.org",
                    fw_email="ools@that.org",
                    archive_contact="1",
                    p30_naccid_enroll_access_level="ViewAccess",
                    scan_dashboard_access_level="ViewAccess",
                    p30_clin_forms_access_level="SubmitAudit",
                    p30_imaging_access_level="SubmitAudit",
                    p30_flbm_access_level="SubmitAudit",
                    p30_genetic_access_level="ViewAccess",
                    cl_clin_forms_access_level="NoAccess",
                    cl_imaging_access_level="NoAccess",
                    cl_flbm_access_level="ViewAccess",
                    cl_pay_access_level="NoAccess",
                    cl_ror_access_level="NoAccess",
                    permissions_approval_name="disapprover",
                ),
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
        entry = CenterUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=Authorizations(
                activities={
                    PageResource(page="community-resources"): Activity(
                        resource=PageResource(page="community-resources"),
                        action="view",
                    ),
                },
            ),
            study_authorizations=[
                StudyAuthorizations(
                    study_id="adrc",
                    activities={
                        DatatypeResource(datatype="enrollment"): Activity(
                            resource=DatatypeResource(datatype="enrollment"),
                            action="submit-audit",
                        ),
                        DatatypeResource(datatype="form"): Activity(
                            resource=DatatypeResource(datatype="form"),
                            action="submit-audit",
                        ),
                        DatatypeResource(datatype="scan-analysis"): Activity(
                            resource=DatatypeResource(datatype="scan-analysis"),
                            action="view",
                        ),
                    },
                )
            ],
            active=True,
            approved=True,
            auth_email="chip_auth@theorg.org",
        )

        assert "submit-audit-datatype-form" in entry.study_authorizations[0]  # type: ignore

        # assumes study_id is adrc
        try:
            dir_record = DirectoryAuthorizations.model_validate(
                create_directory_entry(
                    contact_company_name="the center",
                    adresearchctr="0",
                    adcid="0",
                    firstname="chip",
                    lastname="puppy",
                    email="chip@theorg.org",
                    fw_email="chip_auth@theorg.org",
                    archive_contact="0",
                    web_report_access___web="1",
                    scan_dashboard_access_level="ViewAccess",
                    p30_naccid_enroll_access_level="SubmitAudit",
                    p30_clin_forms_access_level="SubmitAudit",
                    p30_imaging_access_level="NoAccess",
                    p30_flbm_access_level="NoAccess",
                    p30_genetic_access_level="NoAccess",
                    cl_clin_forms_access_level="NoAccess",
                    cl_imaging_access_level="NoAccess",
                    cl_flbm_access_level="NoAccess",
                    cl_pay_access_level="NoAccess",
                    cl_ror_access_level="NoAccess",
                    permissions_approval_name="approver",
                ),
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
        entry2 = CenterUserEntry(
            org_name="the center",
            adcid=0,
            name=PersonName(first_name="chip", last_name="puppy"),
            email="chip@theorg.org",
            authorizations=Authorizations(
                activities={
                    PageResource(page="webinars"): Activity(
                        resource=PageResource(page="webinars"),
                        action="view",
                    ),
                },
            ),
            study_authorizations=[
                StudyAuthorizations(
                    study_id="dummy",
                    activities={
                        DatatypeResource(datatype="form"): Activity(
                            resource=DatatypeResource(datatype="form"),
                            action="submit-audit",
                        ),
                        DatatypeResource(datatype="enrollment"): Activity(
                            resource=DatatypeResource(datatype="enrollment"),
                            action="submit-audit",
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
