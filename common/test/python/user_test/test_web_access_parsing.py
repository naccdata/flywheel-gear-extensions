"""Test web_report_access checkbox field parsing into separate access levels.

REDCap exports checkbox fields as separate columns:
- web_report_access___web: "0" or "1"
- web_report_access___repdash: "0" or "1"
"""

from user_test.directory_test_utils import create_directory_entry
from users.nacc_directory import DirectoryAuthorizations


def test_both_unchecked():
    """Both checkboxes unchecked results in NoAccess for both."""
    entry = create_directory_entry(
        web_report_access___web="0",
        web_report_access___repdash="0",
    )
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_community_resources_access_level == "NoAccess"
    assert auth.adrc_dashboard_reports_access_level == "NoAccess"


def test_web_only():
    """Web checked gives ViewAccess to community resources only."""
    entry = create_directory_entry(
        web_report_access___web="1",
        web_report_access___repdash="0",
    )
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_community_resources_access_level == "ViewAccess"
    assert auth.adrc_dashboard_reports_access_level == "NoAccess"


def test_repdash_only():
    """RepDash checked gives ViewAccess to reports only."""
    entry = create_directory_entry(
        web_report_access___web="0",
        web_report_access___repdash="1",
    )
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_community_resources_access_level == "NoAccess"
    assert auth.adrc_dashboard_reports_access_level == "ViewAccess"


def test_both_checked():
    """Both checked gives ViewAccess to both."""
    entry = create_directory_entry(
        web_report_access___web="1",
        web_report_access___repdash="1",
    )
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_community_resources_access_level == "ViewAccess"
    assert auth.adrc_dashboard_reports_access_level == "ViewAccess"
