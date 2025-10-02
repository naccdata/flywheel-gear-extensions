from users.authorizations import Activity, StudyAuthorizations
from users.nacc_directory import ActiveUserEntry, DirectoryAuthorizations, UserEntry


class TestDirectoryAuthorizations:
    def test_validation(self):
        auths = DirectoryAuthorizations.model_validate(
            {
                "record_id": "1",
                "firstname": "Test",
                "lastname": "User",
                "flywheel_access": "1",
                "web_report_access___web": "1",
                "web_report_access___repdash": "1",
                "study_selections___p30": "1",
                "study_selections___affiliatedstudy": "1",
                "scan_dashboard_access_level": "ViewAccess",
                "p30_naccid_enroll_access_level": "",
                "p30_clin_forms_access_level": "SubmitAudit",
                "p30_imaging_access_level": "ViewAccess",
                "p30_flbm_access_level": "ViewAccess",
                "p30_genetic_access_level": "ViewAccess",
                "affiliated_study___leads": "1",
                "affiliated_study___dvcid": "1",
                "affiliated_study___allftd": "1",
                "affiliated_study___dlbc": "1",
                "affiliated_study___clariti": "1",
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
            },
            by_alias=True,
        )
        assert auths
        assert auths.inactive

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, UserEntry)

    auths = DirectoryAuthorizations.model_validate(
        {
            "record_id": "2",
            "firstname": "Test",
            "lastname": "User",
            "flywheel_access": "1",
            "web_report_access___web": "1",
            "web_report_access___repdash": "1",
            "study_selections___p30": "1",
            "study_selections___affiliatedstudy": "1",
            "scan_dashboard_access_level": "",
            "p30_naccid_enroll_access_level": "ViewAccess",
            "p30_clin_forms_access_level": "SubmitAudit",
            "p30_imaging_access_level": "SubmitAudit",
            "p30_flbm_access_level": "SubmitAudit",
            "p30_genetic_access_level": "ViewAccess",
            "affiliated_study___leads": "0",
            "affiliated_study___dvcid": "0",
            "affiliated_study___allftd": "0",
            "affiliated_study___dlbc": "0",
            "affiliated_study___clariti": "1",
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
            "fw_email": "user@institution.edu",
            "email": "user@institution.edu",
            "contact_company_name": "an institution",
            "adresearchctr": "999",
            "archive_contact": "0",
            "permissions_approval_name": "",
        },
        by_alias=True,
    )
    assert auths
    assert not auths.inactive
    assert not auths.affiliated_study_leads
    assert auths.dlbc_form_access_level == "NoAccess"

    user_entry = auths.to_user_entry()
    assert user_entry and isinstance(user_entry, ActiveUserEntry)
    assert user_entry.active
    assert user_entry.adcid == 999
    assert user_entry.authorizations == [
        StudyAuthorizations(
            study_id="adrc",
            activities={
                "enrollment": Activity(datatype="enrollment", action="view"),
                "form": Activity(datatype="form", action="submit-audit"),
                "dicom": Activity(datatype="dicom", action="submit-audit"),
                "biomarker": Activity(datatype="biomarker", action="submit-audit"),
                "apoe": Activity(datatype="apoe", action="view"),
                "gwas": Activity(datatype="gwas", action="view"),
                "genetic-availability": Activity(
                    datatype="genetic-availability", action="view"
                ),
                "imputation": Activity(datatype="imputation", action="view"),
            },
        ),
        StudyAuthorizations(
            study_id="clariti",
            activities={"biomarker": Activity(datatype="biomarker", action="view")},
        ),
    ]
