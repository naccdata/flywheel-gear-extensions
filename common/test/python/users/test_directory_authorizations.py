from users.authorizations import Activity, StudyAuthorizations
from users.nacc_directory import ActiveUserEntry, DirectoryAuthorizations, UserEntry


class TestDirectoryAuthorizations:
    def test_validation(self):
        auths = DirectoryAuthorizations.model_validate(
            {
                "firstname": "Test",
                "lastname": "User",
                "web_report_access": "",
                "study_selections": "P30,AffiliatedStudy",
                "scan_dashboard_access_level": "ViewAccess",
                "p30_naccid_enroll_access_level": "",
                "p30_clin_forms_access_level": "SubmitAudit",
                "p30_imaging_access_level": "ViewAccess",
                "p30_flbm_access_level": "ViewAccess",
                "p30_genetic_access_level": "ViewAccess",
                "affiliated_study": "CLARiTI,LEADS,DVCID,ALLFTD,DLBC",
                "leads_naccid_enroll_access_level": "",
                "leads_clin_forms_access_level": "SubmitAudit",
                "dvcid_naccid_enroll_access_level": "",
                "dvcid_clin_forms_access_level": "",
                "allftd_naccid_enroll_access_level": "",
                "allftd_clin_forms_access_level": "",
                "dlbc_naccid_enroll_access_level": "",
                "dlbc_clin_forms_access_level": "",
                "cl_clin_forms_access_level": "",
                "cl_imaging_access_level": "",
                "cl_flbm_access_level": "",
                "cl_pay_access_level": "",
                "cl_ror_access_level": "",
                "permissions_approval": "1",
                "permissions_approval_date": "2025-08-13",
                "permissions_approval_name": "",
                "fw_email": "user@institution.edu",
                "email": "user@institution.edu",
                "contact_company_name": "an institution",
                "adresearchctr": "999",
                "archive_contact": "1",
                "nacc_data_platform_access_information_complete": "2",
            },
            by_alias=True,
        )
        assert auths
        assert auths.inactive

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, UserEntry)

    auths = DirectoryAuthorizations.model_validate(
        {
            "firstname": "Test",
            "lastname": "User",
            "web_report_access": "1",
            "study_selections": "P30,AffiliatedStudy",
            "scan_dashboard_access_level": "",
            "p30_naccid_enroll_access_level": "ViewAccess",
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
            "permissions_approval_name": "",
            "fw_email": "user@institution.edu",
            "email": "user@institution.edu",
            "contact_company_name": "an institution",
            "adresearchctr": "999",
            "archive_contact": "0",
            "nacc_data_platform_access_information_complete": "2",
        },
        by_alias=True,
    )
    assert auths
    assert not auths.inactive
    assert auths.complete
    assert "LEADS" not in auths.affiliated_study
    assert auths.dlbc_form_access_level == "NoAccess"

    user_entry = auths.to_user_entry()
    assert user_entry and isinstance(user_entry, ActiveUserEntry)
    assert user_entry.active
    assert user_entry.adcid == 999
    assert len(user_entry.authorizations) == 4

    # using dict to manage authorizations to avoid ordering issues in comparing lists
    user_authorizations = {auth.study_id: auth for auth in user_entry.authorizations}  # noqa: RUF012

    assert user_authorizations.get("adrc") == StudyAuthorizations(
        study_id="adrc",
        activities={
            "enrollment": Activity(datatype="enrollment", action="view"),
            "form": Activity(datatype="form", action="submit-audit"),
            "dicom": Activity(datatype="dicom", action="submit-audit"),
        },
    )
    assert user_authorizations.get("clariti") == StudyAuthorizations(
        study_id="clariti",
        activities={"biomarker": Activity(datatype="biomarker", action="view")},
    )
    assert user_authorizations.get("ncrad") == StudyAuthorizations(
        study_id="ncrad",
        activities={
            "biomarker": Activity(datatype="biomarker", action="submit-audit"),
            "apoe": Activity(datatype="apoe", action="view"),
        },
    )
    assert user_authorizations.get("niagads") == StudyAuthorizations(
        study_id="niagads",
        activities={
            "gwas": Activity(datatype="gwas", action="view"),
            "genetic-availability": Activity(
                datatype="genetic-availability", action="view"
            ),
            "imputation": Activity(datatype="imputation", action="view"),
        },
    )
