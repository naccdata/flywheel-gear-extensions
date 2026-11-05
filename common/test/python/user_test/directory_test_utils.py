"""Shared test utilities for directory authorization tests."""


def create_directory_entry(**overrides) -> dict:
    """Create a base directory entry dict with sensible defaults.

    All access levels default to empty string (NoAccess). Override
    specific fields by passing keyword arguments.
    """
    entry = {
        "firstname": "Test",
        "lastname": "User",
        "email": "user@institution.edu",
        "fw_email": "user@institution.edu",
        "archive_contact": "0",
        "contact_company_name": "Test Institution",
        "adresearchctr": "999",
        "adcid": "999",
        "web_report_access___web": "0",
        "web_report_access___repdash": "0",
        "scan_dashboard_access_level": "",
        "p30_naccid_enroll_access_level": "",
        "p30_clin_forms_access_level": "",
        "p30_imaging_access_level": "",
        "p30_flbm_access_level": "",
        "p30_genetic_access_level": "",
        "leads_naccid_enroll_access_level": "",
        "leads_clin_forms_access_level": "",
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
        "signed_agreement_status_num_ct": "1",
    }
    entry.update(overrides)
    return entry
