"""Test that general_page_web_access_level and
adrc_dashboard_reports_access_level are handled correctly in
to_user_entry()."""

from user_test.directory_test_utils import create_directory_entry
from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import CenterUserEntry


def test_web_access_not_in_authorizations():
    """Test that general_page_community_resources_access_level is not included
    in user authorizations.

    The general_page_community_resources_access_level field is for
    general community resources access and doesn't map to a study-
    specific datatype, so it's not included in the authorizations list.
    """
    entry = create_directory_entry(
        web_report_access="Web",
        study_selections="P30",
        p30_naccid_enroll_access_level="ViewAccess",
        p30_clin_forms_access_level="ViewAccess",
    )
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
    entry = create_directory_entry(
        web_report_access="RepDash",
        study_selections="P30",
        p30_naccid_enroll_access_level="ViewAccess",
        p30_clin_forms_access_level="ViewAccess",
    )
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
    entry = create_directory_entry(
        web_report_access="Web,RepDash",
        study_selections="P30",
        p30_naccid_enroll_access_level="ViewAccess",
        p30_clin_forms_access_level="ViewAccess",
    )
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
