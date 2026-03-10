"""Test that general_page_web_access_level and
adrc_dashboard_reports_access_level are handled correctly in
to_user_entry()."""

from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import CenterUserEntry


def create_test_entry(**overrides):
    """Create a test directory entry."""
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
        "study_selections": "P30",
        "p30_naccid_enroll_access_level": "ViewAccess",
        "p30_clin_forms_access_level": "ViewAccess",
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


def test_web_access_not_in_authorizations():
    """Test that general_page_community_resources_access_level is not included
    in user authorizations.

    The general_page_community_resources_access_level field is for
    general community resources access and doesn't map to a study-
    specific datatype, so it's not included in the authorizations list.
    """
    entry = create_test_entry(web_report_access="Web")
    auth = DirectoryAuthorizations(**entry)

    assert auth.general_page_community_resources_access_level == "ViewAccess"

    user_entry = auth.to_user_entry()
    assert user_entry is not None
    assert user_entry.active

    # The method returns CenterUserEntry for entries with adcid
    assert isinstance(user_entry, CenterUserEntry)

    # general_page_web_access_level should not create any authorizations
    # Only the P30 enrollment and form access should be present
    assert len(user_entry.study_authorizations) == 1
    assert user_entry.study_authorizations[0].study_id == "adrc"

    # Should have enrollment and form datatypes from P30 fields
    activities = user_entry.study_authorizations[0].activities
    from users.authorizations import DatatypeResource

    assert DatatypeResource(datatype="enrollment") in activities
    assert DatatypeResource(datatype="form") in activities


def test_adrc_reports_not_in_authorizations():
    """Test that adrc_dashboard_reports_access_level is not included in user
    authorizations.

    The adrc_dashboard_reports_access_level field is for ADRC
    dashboards/reports access but 'reports' is not a valid datatype in
    DatatypeNameType, so it's ignored by the authorization parsing
    logic.
    """
    entry = create_test_entry(web_report_access="RepDash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.adrc_dashboard_reports_access_level == "ViewAccess"

    user_entry = auth.to_user_entry()
    assert user_entry is not None
    assert user_entry.active

    # The method returns CenterUserEntry for entries with adcid
    assert isinstance(user_entry, CenterUserEntry)

    # adrc_dashboard_reports_access_level should not create authorizations
    # Only the P30 enrollment and form access should be present
    assert len(user_entry.study_authorizations) == 1
    assert user_entry.study_authorizations[0].study_id == "adrc"

    # Should have enrollment and form datatypes from P30 fields
    activities = user_entry.study_authorizations[0].activities
    from users.authorizations import DatatypeResource

    assert DatatypeResource(datatype="enrollment") in activities
    assert DatatypeResource(datatype="form") in activities


def test_both_web_and_reports_not_in_authorizations():
    """Test that both web and reports access don't create authorizations."""
    entry = create_test_entry(web_report_access="Web,RepDash")
    auth = DirectoryAuthorizations(**entry)

    assert auth.general_page_community_resources_access_level == "ViewAccess"
    assert auth.adrc_dashboard_reports_access_level == "ViewAccess"

    user_entry = auth.to_user_entry()
    assert user_entry is not None
    assert user_entry.active

    # The method returns CenterUserEntry for entries with adcid
    assert isinstance(user_entry, CenterUserEntry)

    # Neither web nor reports should create authorizations
    # Only the P30 enrollment and form access should be present
    assert len(user_entry.study_authorizations) == 1
    assert user_entry.study_authorizations[0].study_id == "adrc"

    # Should have enrollment and form datatypes from P30 fields
    activities = user_entry.study_authorizations[0].activities
    from users.authorizations import DatatypeResource

    assert DatatypeResource(datatype="enrollment") in activities
    assert DatatypeResource(datatype="form") in activities
