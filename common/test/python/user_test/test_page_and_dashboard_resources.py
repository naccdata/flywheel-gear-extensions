"""Test page and dashboard resource parsing in DirectoryAuthorizations.

Tests the __parse_fields() method's handling of page and dashboard
resources using the actual fields defined in the model.
"""

from users.authorizations import (
    DashboardResource,
    DatatypeResource,
    PageResource,
)
from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import CenterUserEntry


def create_test_entry(**overrides):
    """Create a minimal test directory entry."""
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


class TestGeneralPageCommunityResourcesAccess:
    """Tests for general_page_community_resources_access_level field."""

    def test_general_page_community_resources_creates_page_resource(self):
        """Test that general_page_community_resources_access_level with 'Web'
        creates PageResource in general authorizations.

        This tests that the __parse_fields() method correctly:
        - Parses the field name pattern:
          general_page_community_resources_access_level
        - Identifies scope='general', resource_type='page',
          resource_name='community-resources'
        - Creates a PageResource and adds it to general authorizations
        """
        entry = create_test_entry(
            web_report_access="Web",
            study_selections="P30",
            p30_naccid_enroll_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # The general_page_community_resources_access_level field should create
        # a PageResource
        community_resources_resource = PageResource(page="community-resources")
        assert community_resources_resource in user_entry.authorizations.activities

        activity = user_entry.authorizations.activities[community_resources_resource]
        assert activity.action == "view"
        assert activity.resource == community_resources_resource

    def test_general_page_community_resources_no_access_ignored(self):
        """Test that NoAccess doesn't create page resource."""
        entry = create_test_entry(
            web_report_access="",  # Empty string converts to NoAccess
            study_selections="P30",
            p30_naccid_enroll_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # NoAccess should not create any resource
        web_resource = PageResource(page="web")
        assert web_resource not in user_entry.authorizations.activities


class TestAdrcDashboardReportsAccess:
    """Tests for adrc_dashboard_reports_access_level field."""

    def test_adrc_dashboard_reports_creates_dashboard_resource(self):
        """Test that adrc_dashboard_reports_access_level with 'RepDash' creates
        DashboardResource in ADRC study authorizations.

        This tests that the __parse_fields() method correctly:
        - Parses the field name pattern: adrc_dashboard_reports_access_level
        - Identifies scope='adrc', resource_type='dashboard', resource_name='reports'
        - Creates a DashboardResource and adds it to ADRC study authorizations
        """
        entry = create_test_entry(
            web_report_access="RepDash",
            study_selections="P30",
            p30_naccid_enroll_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find ADRC study authorizations
        adrc_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "adrc"
            ),
            None,
        )
        assert adrc_auth is not None

        # The adrc_dashboard_reports_access_level field should create a
        # DashboardResource
        reports_resource = DashboardResource(dashboard="reports")
        assert reports_resource in adrc_auth.activities

        activity = adrc_auth.activities[reports_resource]
        assert activity.action == "view"

    def test_adrc_dashboard_reports_no_access_ignored(self):
        """Test that NoAccess doesn't create dashboard resource."""
        entry = create_test_entry(
            web_report_access="",  # Empty string converts to NoAccess
            study_selections="P30",
            p30_naccid_enroll_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find ADRC study authorizations
        adrc_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "adrc"
            ),
            None,
        )
        assert adrc_auth is not None

        # NoAccess should not create any resource
        reports_resource = DashboardResource(dashboard="reports")
        assert reports_resource not in adrc_auth.activities


class TestClaritiDashboardAccess:
    """Tests for CLARiTI dashboard fields."""

    def test_clariti_dashboard_pay_creates_dashboard_resource(self):
        """Test that clariti_dashboard_pay_access_level creates
        DashboardResource in CLARiTI study authorizations.

        This tests that the __parse_fields() method correctly:
        - Parses the field name pattern: clariti_dashboard_pay_access_level
        - Identifies scope='clariti', resource_type='dashboard', resource_name='pay'
        - Creates a DashboardResource and adds it to CLARiTI study authorizations
        """
        entry = create_test_entry(
            cl_pay_access_level="ViewAccess",
            study_selections="AffiliatedStudy",
            affiliated_study="CLARiTI",
            cl_clin_forms_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "clariti"
            ),
            None,
        )
        assert clariti_auth is not None

        # The clariti_dashboard_pay_access_level field should create a DashboardResource
        pay_resource = DashboardResource(dashboard="pay")
        assert pay_resource in clariti_auth.activities

        activity = clariti_auth.activities[pay_resource]
        assert activity.action == "view"

    def test_clariti_participant_summary_creates_datatype_resource(self):
        """Test that clariti_datatype_participant_summary_access_level creates
        DatatypeResource."""
        entry = create_test_entry(
            cl_ror_access_level="ViewAccess",
            study_selections="AffiliatedStudy",
            affiliated_study="CLARiTI",
            cl_clin_forms_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "clariti"
            ),
            None,
        )
        assert clariti_auth is not None

        # The clariti_datatype_participant_summary_access_level field should
        # create a DatatypeResource
        participant_summary_resource = DatatypeResource(datatype="participant-summary")
        assert participant_summary_resource in clariti_auth.activities

    def test_clariti_dashboard_and_datatype_together(self):
        """Test that CLARiTI dashboard and datatype fields work together."""
        entry = create_test_entry(
            cl_pay_access_level="ViewAccess",
            cl_ror_access_level="ViewAccess",
            study_selections="AffiliatedStudy",
            affiliated_study="CLARiTI",
            cl_clin_forms_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "clariti"
            ),
            None,
        )
        assert clariti_auth is not None

        # Dashboard and datatype resources should both be present
        assert DashboardResource(dashboard="pay") in clariti_auth.activities
        assert (
            DatatypeResource(datatype="participant-summary") in clariti_auth.activities
        )

    def test_clariti_dashboard_no_access_ignored(self):
        """Test that NoAccess doesn't create dashboard or datatype
        resources."""
        entry = create_test_entry(
            cl_pay_access_level="NoAccess",
            cl_ror_access_level="NoAccess",
            study_selections="AffiliatedStudy",
            affiliated_study="CLARiTI",
            cl_clin_forms_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "clariti"
            ),
            None,
        )
        assert clariti_auth is not None

        # NoAccess should not create any resources
        assert DashboardResource(dashboard="pay") not in clariti_auth.activities
        assert (
            DatatypeResource(datatype="participant-summary")
            not in clariti_auth.activities
        )


class TestMixedResourceTypes:
    """Tests for users with multiple resource types."""

    def test_user_with_page_dashboard_and_datatype_resources(self):
        """Test user with page, dashboard, and datatype resources together.

        This demonstrates that the __parse_fields() method correctly
        handles multiple resource types (datatype, page, dashboard)
        across different scopes (general, study-specific).
        """
        entry = create_test_entry(
            # General page resource
            web_report_access="Web,RepDash",  # Creates both page and dashboard
            # ADRC study resources
            study_selections="P30,AffiliatedStudy",
            p30_naccid_enroll_access_level="ViewAccess",
            p30_clin_forms_access_level="SubmitAudit",
            # CLARiTI study resources
            affiliated_study="CLARiTI",
            cl_clin_forms_access_level="ViewAccess",
            cl_pay_access_level="ViewAccess",
            cl_ror_access_level="ViewAccess",
        )
        auth = DirectoryAuthorizations(**entry)
        user_entry = auth.to_user_entry()

        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)

        # Check general authorizations have page resource
        assert (
            PageResource(page="community-resources")
            in user_entry.authorizations.activities
        )

        # Check ADRC study has dashboard resource and datatypes
        adrc_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "adrc"
            ),
            None,
        )
        assert adrc_auth is not None
        assert DashboardResource(dashboard="reports") in adrc_auth.activities
        assert DatatypeResource(datatype="enrollment") in adrc_auth.activities
        assert DatatypeResource(datatype="form") in adrc_auth.activities

        # Check CLARiTI study has dashboard resources and datatypes
        clariti_auth = next(
            (
                auth
                for auth in user_entry.study_authorizations
                if auth.study_id == "clariti"
            ),
            None,
        )
        assert clariti_auth is not None
        assert DashboardResource(dashboard="pay") in clariti_auth.activities
        assert (
            DatatypeResource(datatype="participant-summary") in clariti_auth.activities
        )
        assert DatatypeResource(datatype="form") in clariti_auth.activities
