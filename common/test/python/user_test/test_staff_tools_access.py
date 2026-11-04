"""Test that NACC staff get the general staff-tools page.

The directory marks NACC staff with code 14 in the
``ad_community_partner_or_ngo`` choice field.
"""

import pytest

from user_test.directory_test_utils import create_directory_entry
from users.authorizations import Activity, PageResource
from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import ActiveUserEntry

STAFF_TOOLS = Activity(resource=PageResource(page="staff-tools"), action="view")


@pytest.mark.parametrize("value", ["14", " 14 ", 14])
def test_staff_code_gives_view_access(value):
    entry = create_directory_entry(ad_community_partner_or_ngo=value)
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_staff_tools_access_level == "ViewAccess"


@pytest.mark.parametrize("value", ["", "1", "13", "140", "NACC", None, 1, True])
def test_other_values_give_no_access(value):
    entry = create_directory_entry(ad_community_partner_or_ngo=value)
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_staff_tools_access_level == "NoAccess"


def test_missing_field_gives_no_access():
    entry = create_directory_entry()
    del entry["ad_community_partner_or_ngo"]
    auth = DirectoryAuthorizations.model_validate(entry, by_alias=True)

    assert auth.general_page_staff_tools_access_level == "NoAccess"


@pytest.mark.parametrize("adcid", ["999", ""])
def test_staff_gets_general_staff_tools_page(adcid):
    """Staff tools is a general grant, with or without a center."""
    entry = create_directory_entry(ad_community_partner_or_ngo="14", adcid=adcid)
    user_entry = DirectoryAuthorizations.model_validate(
        entry, by_alias=True
    ).to_user_entry()

    assert isinstance(user_entry, ActiveUserEntry)
    assert STAFF_TOOLS in user_entry.authorizations
    assert str(STAFF_TOOLS) == "view-page-staff-tools"
    assert all(
        PageResource(page="staff-tools") not in study.activities
        for study in getattr(user_entry, "study_authorizations", [])
    )


def test_non_staff_has_no_staff_tools_page():
    entry = create_directory_entry(ad_community_partner_or_ngo="3")
    user_entry = DirectoryAuthorizations.model_validate(
        entry, by_alias=True
    ).to_user_entry()

    assert isinstance(user_entry, ActiveUserEntry)
    assert STAFF_TOOLS not in user_entry.authorizations
