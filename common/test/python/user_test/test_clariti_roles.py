"""Unit tests for CLARiTI role mapping functionality."""

import pytest
from user_test.directory_test_utils import create_directory_entry
from users.authorizations import Activity, DashboardResource
from users.clariti_roles import map_clariti_roles_to_activities
from users.nacc_directory import DirectoryAuthorizations


class TestCLARiTIRoleMapping:
    """Test suite for map_clariti_roles_to_activities function."""

    @pytest.fixture
    def base_directory_auth(self):
        """Create a base DirectoryAuthorizations object with required
        fields."""
        return DirectoryAuthorizations.model_validate(
            create_directory_entry(
                web_report_access="NoAccess",
                scan_dashboard_access_level="NoAccess",
                p30_naccid_enroll_access_level="NoAccess",
                p30_clin_forms_access_level="NoAccess",
                p30_imaging_access_level="NoAccess",
                p30_flbm_access_level="NoAccess",
                p30_genetic_access_level="NoAccess",
                leads_naccid_enroll_access_level="NoAccess",
                leads_clin_forms_access_level="NoAccess",
                dvcid_naccid_enroll_access_level="NoAccess",
                dvcid_clin_forms_access_level="NoAccess",
                allftd_naccid_enroll_access_level="NoAccess",
                allftd_clin_forms_access_level="NoAccess",
                dlbc_naccid_enroll_access_level="NoAccess",
                dlbc_clin_forms_access_level="NoAccess",
                cl_clin_forms_access_level="NoAccess",
                cl_imaging_access_level="NoAccess",
                cl_flbm_access_level="NoAccess",
                cl_pay_access_level="NoAccess",
                cl_ror_access_level="NoAccess",
                permissions_approval_date="2025-01-01",
                permissions_approval_name="Test Approver",
            ),
            by_alias=True,
        )

    def test_empty_directory_authorizations(self, base_directory_auth):
        """Test mapping with no CLARiTI roles set."""
        activities = map_clariti_roles_to_activities(base_directory_auth)
        assert activities == []

    def test_single_payment_role(self, base_directory_auth):
        """Test mapping with a single payment role."""
        base_directory_auth.loc_clariti_role___u01copi = True
        activities = map_clariti_roles_to_activities(base_directory_auth)

        assert len(activities) == 2  # payment-tracker + enrollment
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_multiple_payment_roles(self, base_directory_auth):
        """Test mapping with multiple payment roles."""
        base_directory_auth.loc_clariti_role___u01copi = True
        base_directory_auth.loc_clariti_role___pi = True
        base_directory_auth.loc_clariti_role___piadmin = True

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to single payment-tracker activity
        assert len(activities) == 2  # payment-tracker + enrollment
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_organizational_role_only(self, base_directory_auth):
        """Test mapping with only organizational role (not payment role)."""
        base_directory_auth.loc_clariti_role___mpi = True
        activities = map_clariti_roles_to_activities(base_directory_auth)

        assert len(activities) == 1
        assert str(activities[0]) == "view-dashboard-enrollment"

    def test_multiple_organizational_roles(self, base_directory_auth):
        """Test mapping with multiple organizational roles."""
        base_directory_auth.loc_clariti_role___mpi = True
        base_directory_auth.loc_clariti_role___orecore = True
        base_directory_auth.loc_clariti_role___crl = True

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to single enrollment activity
        assert len(activities) == 1
        assert str(activities[0]) == "view-dashboard-enrollment"

    def test_cl_pay_access_level_view_access(self, base_directory_auth):
        """Test mapping with cl_pay_access_level set to ViewAccess."""
        base_directory_auth.clariti_dashboard_pay_access_level = "ViewAccess"
        activities = map_clariti_roles_to_activities(base_directory_auth)

        assert len(activities) == 1
        assert str(activities[0]) == "view-dashboard-payment-tracker"

    def test_admin_core_member(self, base_directory_auth):
        """Test mapping with admin core member role."""
        base_directory_auth.ind_clar_core_role___admin = True
        activities = map_clariti_roles_to_activities(base_directory_auth)

        assert len(activities) == 2
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_deduplication_payment_role_and_access_level(self, base_directory_auth):
        """Test deduplication when both payment role and access level grant
        access."""
        base_directory_auth.loc_clariti_role___pi = True
        base_directory_auth.clariti_dashboard_pay_access_level = "ViewAccess"

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to single payment-tracker activity
        assert len(activities) == 2  # payment-tracker + enrollment
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_deduplication_admin_and_payment_role(self, base_directory_auth):
        """Test deduplication when admin and payment role both grant access."""
        base_directory_auth.ind_clar_core_role___admin = True
        base_directory_auth.loc_clariti_role___pi = True

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to single activity per dashboard
        assert len(activities) == 2
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_deduplication_admin_and_org_role(self, base_directory_auth):
        """Test deduplication when admin and organizational role both grant
        access."""
        base_directory_auth.ind_clar_core_role___admin = True
        base_directory_auth.loc_clariti_role___mpi = True

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to single activity per dashboard
        assert len(activities) == 2
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_all_roles_set(self, base_directory_auth):
        """Test mapping with all CLARiTI roles set."""
        # Set all payment roles
        base_directory_auth.loc_clariti_role___u01copi = True
        base_directory_auth.loc_clariti_role___pi = True
        base_directory_auth.loc_clariti_role___piadmin = True
        base_directory_auth.loc_clariti_role___copi = True
        base_directory_auth.loc_clariti_role___subawardadmin = True
        base_directory_auth.loc_clariti_role___addlsubaward = True
        base_directory_auth.loc_clariti_role___studycoord = True

        # Set all organizational roles
        base_directory_auth.loc_clariti_role___mpi = True
        base_directory_auth.loc_clariti_role___orecore = True
        base_directory_auth.loc_clariti_role___crl = True
        base_directory_auth.loc_clariti_role___advancedmri = True
        base_directory_auth.loc_clariti_role___physicist = True
        base_directory_auth.loc_clariti_role___addlimaging = True
        base_directory_auth.loc_clariti_role___reg = True

        # Set admin role
        base_directory_auth.ind_clar_core_role___admin = True

        # Set access level
        base_directory_auth.clariti_dashboard_pay_access_level = "ViewAccess"

        activities = map_clariti_roles_to_activities(base_directory_auth)

        # Should deduplicate to exactly 2 activities
        assert len(activities) == 2
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_mixed_scenario_payment_and_org(self, base_directory_auth):
        """Test mixed scenario with payment and organizational roles."""
        base_directory_auth.loc_clariti_role___pi = True
        base_directory_auth.loc_clariti_role___crl = True

        activities = map_clariti_roles_to_activities(base_directory_auth)

        assert len(activities) == 2
        activity_strs = {str(a) for a in activities}
        assert "view-dashboard-payment-tracker" in activity_strs
        assert "view-dashboard-enrollment" in activity_strs

    def test_activity_objects_are_correct_type(self, base_directory_auth):
        """Test that returned activities have correct types."""
        base_directory_auth.loc_clariti_role___pi = True
        activities = map_clariti_roles_to_activities(base_directory_auth)

        for activity in activities:
            assert isinstance(activity, Activity)
            assert isinstance(activity.resource, DashboardResource)
            assert activity.action == "view"

    def test_no_roles_set_returns_empty_list(self, base_directory_auth):
        """Test that no roles returns empty list, not None."""
        activities = map_clariti_roles_to_activities(base_directory_auth)
        assert activities == []
        assert isinstance(activities, list)

    def test_payment_role_fields_coverage(self, base_directory_auth):
        """Test each payment role field individually."""
        payment_roles = [
            "loc_clariti_role___u01copi",
            "loc_clariti_role___pi",
            "loc_clariti_role___piadmin",
            "loc_clariti_role___copi",
            "loc_clariti_role___subawardadmin",
            "loc_clariti_role___addlsubaward",
            "loc_clariti_role___studycoord",
        ]

        for role_field in payment_roles:
            # Create a fresh copy by setting the field directly
            auth = DirectoryAuthorizations.model_validate(
                {
                    "firstname": "Test",
                    "lastname": "User",
                    "email": "test@example.com",
                    "fw_email": "test@example.com",
                    "archive_contact": "0",
                    "contact_company_name": "Test Institution",
                    "adcid": "999",
                    "web_report_access": "NoAccess",
                    "study_selections": "",
                    "scan_dashboard_access_level": "NoAccess",
                    "p30_naccid_enroll_access_level": "NoAccess",
                    "p30_clin_forms_access_level": "NoAccess",
                    "p30_imaging_access_level": "NoAccess",
                    "p30_flbm_access_level": "NoAccess",
                    "p30_genetic_access_level": "NoAccess",
                    "affiliated_study": "",
                    "leads_naccid_enroll_access_level": "NoAccess",
                    "leads_clin_forms_access_level": "NoAccess",
                    "dvcid_naccid_enroll_access_level": "NoAccess",
                    "dvcid_clin_forms_access_level": "NoAccess",
                    "allftd_naccid_enroll_access_level": "NoAccess",
                    "allftd_clin_forms_access_level": "NoAccess",
                    "dlbc_naccid_enroll_access_level": "NoAccess",
                    "dlbc_clin_forms_access_level": "NoAccess",
                    "cl_clin_forms_access_level": "NoAccess",
                    "cl_imaging_access_level": "NoAccess",
                    "cl_flbm_access_level": "NoAccess",
                    "cl_pay_access_level": "NoAccess",
                    "cl_ror_access_level": "NoAccess",
                    "permissions_approval": "1",
                    "permissions_approval_date": "2025-01-01",
                    "permissions_approval_name": "Test Approver",
                    role_field: "1",  # Set the specific role field
                },
                by_alias=True,
            )

            activities = map_clariti_roles_to_activities(auth)

            # Each payment role should grant both dashboards
            assert len(activities) == 2
            activity_strs = {str(a) for a in activities}
            assert "view-dashboard-payment-tracker" in activity_strs
            assert "view-dashboard-enrollment" in activity_strs

    def test_organizational_role_fields_coverage(self, base_directory_auth):
        """Test each organizational role field individually."""
        org_roles = [
            "loc_clariti_role___u01copi",
            "loc_clariti_role___pi",
            "loc_clariti_role___piadmin",
            "loc_clariti_role___copi",
            "loc_clariti_role___subawardadmin",
            "loc_clariti_role___addlsubaward",
            "loc_clariti_role___studycoord",
            "loc_clariti_role___mpi",
            "loc_clariti_role___orecore",
            "loc_clariti_role___crl",
            "loc_clariti_role___advancedmri",
            "loc_clariti_role___physicist",
            "loc_clariti_role___addlimaging",
            "loc_clariti_role___reg",
        ]

        for role_field in org_roles:
            # Create a fresh copy by setting the field directly
            auth = DirectoryAuthorizations.model_validate(
                {
                    "firstname": "Test",
                    "lastname": "User",
                    "email": "test@example.com",
                    "fw_email": "test@example.com",
                    "archive_contact": "0",
                    "contact_company_name": "Test Institution",
                    "adcid": "999",
                    "web_report_access": "NoAccess",
                    "study_selections": "",
                    "scan_dashboard_access_level": "NoAccess",
                    "p30_naccid_enroll_access_level": "NoAccess",
                    "p30_clin_forms_access_level": "NoAccess",
                    "p30_imaging_access_level": "NoAccess",
                    "p30_flbm_access_level": "NoAccess",
                    "p30_genetic_access_level": "NoAccess",
                    "affiliated_study": "",
                    "leads_naccid_enroll_access_level": "NoAccess",
                    "leads_clin_forms_access_level": "NoAccess",
                    "dvcid_naccid_enroll_access_level": "NoAccess",
                    "dvcid_clin_forms_access_level": "NoAccess",
                    "allftd_naccid_enroll_access_level": "NoAccess",
                    "allftd_clin_forms_access_level": "NoAccess",
                    "dlbc_naccid_enroll_access_level": "NoAccess",
                    "dlbc_clin_forms_access_level": "NoAccess",
                    "cl_clin_forms_access_level": "NoAccess",
                    "cl_imaging_access_level": "NoAccess",
                    "cl_flbm_access_level": "NoAccess",
                    "cl_pay_access_level": "NoAccess",
                    "cl_ror_access_level": "NoAccess",
                    "permissions_approval": "1",
                    "permissions_approval_date": "2025-01-01",
                    "permissions_approval_name": "Test Approver",
                    role_field: "1",  # Set the specific role field
                },
                by_alias=True,
            )

            activities = map_clariti_roles_to_activities(auth)

            # Each organizational role should grant enrollment dashboard
            activity_strs = {str(a) for a in activities}
            assert "view-dashboard-enrollment" in activity_strs


class TestCLARiTIPropertyTests:
    """Property-based tests for CLARiTI role mapping."""

    def test_property_backward_compatibility(self):
        """Property 16: Backward Compatibility.

        Validates: Requirements 10.1

        For any DirectoryAuthorizations object without CLARiTI role fields,
        deserialization and processing should succeed without errors, and no
        CLARiTI StudyAuthorizations should be created.

        Minimum 100 iterations.
        """
        from hypothesis import given, settings
        from hypothesis import strategies as st

        @given(
            firstname=st.text(min_size=1, max_size=50),
            lastname=st.text(min_size=1, max_size=50),
            email=st.emails(),
            adcid=st.integers(min_value=1, max_value=999),
            web_report_access=st.sampled_from(["", "1", "NoAccess"]),
            study_selections=st.sampled_from(["", "P30", "P30,AffiliatedStudy"]),
            p30_access=st.sampled_from(["NoAccess", "ViewAccess", "SubmitAudit"]),
        )
        @settings(max_examples=100)
        def property_test(
            firstname,
            lastname,
            email,
            adcid,
            web_report_access,
            study_selections,
            p30_access,
        ):
            auth_dict = create_directory_entry(
                firstname=firstname,
                lastname=lastname,
                email=email,
                fw_email=email,
                adcid=str(adcid),
                web_report_access=web_report_access,
                study_selections=study_selections,
                scan_dashboard_access_level="NoAccess",
                p30_naccid_enroll_access_level=p30_access,
                p30_clin_forms_access_level=p30_access,
                p30_imaging_access_level="NoAccess",
                p30_flbm_access_level="NoAccess",
                p30_genetic_access_level="NoAccess",
                leads_naccid_enroll_access_level="NoAccess",
                leads_clin_forms_access_level="NoAccess",
                dvcid_naccid_enroll_access_level="NoAccess",
                dvcid_clin_forms_access_level="NoAccess",
                allftd_naccid_enroll_access_level="NoAccess",
                allftd_clin_forms_access_level="NoAccess",
                dlbc_naccid_enroll_access_level="NoAccess",
                dlbc_clin_forms_access_level="NoAccess",
                cl_clin_forms_access_level="NoAccess",
                cl_imaging_access_level="NoAccess",
                cl_flbm_access_level="NoAccess",
                cl_pay_access_level="NoAccess",
                cl_ror_access_level="NoAccess",
                permissions_approval_date="2025-01-01",
                permissions_approval_name="Test Approver",
            )

            # Deserialization should succeed
            directory_auth = DirectoryAuthorizations.model_validate(
                auth_dict, by_alias=True
            )

            # Processing should succeed without errors
            user_entry = directory_auth.to_user_entry()

            # If user_entry is not None (active user), verify no CLARiTI study
            if user_entry is not None:
                from users.user_entry import CenterUserEntry

                # Only CenterUserEntry has study_authorizations
                if isinstance(user_entry, CenterUserEntry):
                    clariti_study = None
                    for study_auth in user_entry.study_authorizations:
                        if study_auth.study_id == "clariti":
                            clariti_study = study_auth
                            break

                    # No CLARiTI StudyAuthorizations should be created
                    assert clariti_study is None

            # Mapping function should return empty list
            activities = map_clariti_roles_to_activities(directory_auth)
            assert activities == []

        # Run the property test
        property_test()
