"""Test web_report_access field parsing into separate access levels."""

from users.nacc_directory import DirectoryAuthorizations


def create_minimal_entry(**overrides):
    """Create a minimal directory entry for testing."""
    entry = {
        "firstname": "Test",
        "lastname": "User",
        "email": "test@example.com",
        "contact_company_name": "Test Center",
        "adresearchctr": "1",
        "adcid": "1",
        "archive_contact": "0",
        "fw_email": "test@example.com",
        "nacc_data_platform_access_information_complete": "2",
        "web_report_access": "",
        "study_selections": "",
        "p30_naccid_enroll_access_level": "",
        "p30_clin_forms_access_level": "",
        "p30_imaging_access_level": "",
        "scan_dashboard_access_level": "",
        "p30_flbm_access_level": "",
        "p30_genetic_access_level": "",
        "affiliated_study": "",
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
        "permissions_approval_name": "Test Approver",
        "permissions_approval_date": "2025-01-01",
    }
    entry.update(overrides)
    return entry


def test_web_report_access_empty_string():
    """Test that empty web_report_access results in NoAccess for both."""
    entry = create_minimal_entry(web_report_access="")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "NoAccess"
    assert auth.adrc_reports_access_level == "NoAccess"


def test_web_report_access_web_only():
    """Test that 'Web' gives ViewAccess to web, NoAccess to adrc_reports."""
    entry = create_minimal_entry(web_report_access="Web")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "ViewAccess"
    assert auth.adrc_reports_access_level == "NoAccess"


def test_web_report_access_repdash_only():
    """Test that 'RepDash' gives NoAccess to web, ViewAccess to
    adrc_reports."""
    entry = create_minimal_entry(web_report_access="RepDash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "NoAccess"
    assert auth.adrc_reports_access_level == "ViewAccess"


def test_web_report_access_both():
    """Test that 'Web,RepDash' gives ViewAccess to both."""
    entry = create_minimal_entry(web_report_access="Web,RepDash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "ViewAccess"
    assert auth.adrc_reports_access_level == "ViewAccess"


def test_web_report_access_case_sensitive():
    """Test that the parsing is case-sensitive (matches REDCap values)."""
    # Lowercase should not match
    entry = create_minimal_entry(web_report_access="web,repdash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "NoAccess"
    assert auth.adrc_reports_access_level == "NoAccess"


def test_web_report_access_with_spaces():
    """Test that 'Web, RepDash' (with space) still works."""
    entry = create_minimal_entry(web_report_access="Web, RepDash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "ViewAccess"
    assert auth.adrc_reports_access_level == "ViewAccess"


def test_web_report_access_reverse_order():
    """Test that 'RepDash,Web' works the same as 'Web,RepDash'."""
    entry = create_minimal_entry(web_report_access="RepDash,Web")
    auth = DirectoryAuthorizations(**entry)

    assert auth.web_access_level == "ViewAccess"
    assert auth.adrc_reports_access_level == "ViewAccess"
