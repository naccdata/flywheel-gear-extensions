from user_test.directory_test_utils import create_directory_entry
from users.authorizations import Activity, DatatypeResource, StudyAuthorizations
from users.nacc_directory import (
    CenterUserEntry,
    DirectoryAuthorizations,
    UserEntry,
)
from users.user_entry import ActiveUserEntry


class TestDirectoryAuthorizations:
    def test_validation(self):
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                scan_dashboard_access_level="ViewAccess",
                p30_clin_forms_access_level="SubmitAudit",
                p30_imaging_access_level="ViewAccess",
                p30_flbm_access_level="ViewAccess",
                p30_genetic_access_level="ViewAccess",
                leads_clin_forms_access_level="SubmitAudit",
                contact_company_name="an institution",
                archive_contact="1",
            ),
            by_alias=True,
        )
        assert auths
        assert auths.inactive

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, UserEntry)

    auths = DirectoryAuthorizations.model_validate(
        create_directory_entry(
            p30_naccid_enroll_access_level="ViewAccess",
            p30_clin_forms_access_level="SubmitAudit",
            p30_imaging_access_level="SubmitAudit",
            p30_flbm_access_level="SubmitAudit",
            p30_genetic_access_level="ViewAccess",
            cl_clin_forms_access_level="NoAccess",
            cl_imaging_access_level="NoAccess",
            cl_flbm_access_level="ViewAccess",
            cl_pay_access_level="NoAccess",
            cl_ror_access_level="NoAccess",
            contact_company_name="an institution",
            archive_contact="0",
        ),
        by_alias=True,
    )
    assert auths
    assert not auths.inactive
    assert auths.dlbc_datatype_form_access_level == "NoAccess"

    user_entry = auths.to_user_entry()
    assert user_entry and isinstance(user_entry, CenterUserEntry)
    assert user_entry.active
    assert user_entry.adcid == 999
    assert len(user_entry.study_authorizations) == 4

    # using dict to manage authorizations to avoid ordering issues in comparing lists
    user_authorizations = {  # noqa: RUF012
        auth.study_id: auth for auth in user_entry.study_authorizations
    }

    assert user_authorizations.get("adrc") == StudyAuthorizations(
        study_id="adrc",
        activities={
            DatatypeResource(datatype="enrollment"): Activity(
                resource=DatatypeResource(datatype="enrollment"), action="view"
            ),
            DatatypeResource(datatype="form"): Activity(
                resource=DatatypeResource(datatype="form"), action="submit-audit"
            ),
            DatatypeResource(datatype="dicom"): Activity(
                resource=DatatypeResource(datatype="dicom"), action="submit-audit"
            ),
        },
    )
    assert user_authorizations.get("clariti") == StudyAuthorizations(
        study_id="clariti",
        activities={
            DatatypeResource(datatype="biomarker"): Activity(
                resource=DatatypeResource(datatype="biomarker"), action="view"
            )
        },
    )
    assert user_authorizations.get("ncrad") == StudyAuthorizations(
        study_id="ncrad",
        activities={
            DatatypeResource(datatype="biomarker"): Activity(
                resource=DatatypeResource(datatype="biomarker"), action="submit-audit"
            ),
            DatatypeResource(datatype="apoe"): Activity(
                resource=DatatypeResource(datatype="apoe"), action="view"
            ),
        },
    )
    assert user_authorizations.get("niagads") == StudyAuthorizations(
        study_id="niagads",
        activities={
            DatatypeResource(datatype="gwas"): Activity(
                resource=DatatypeResource(datatype="gwas"), action="view"
            ),
            DatatypeResource(datatype="genetic-availability"): Activity(
                resource=DatatypeResource(datatype="genetic-availability"),
                action="view",
            ),
            DatatypeResource(datatype="imputation"): Activity(
                resource=DatatypeResource(datatype="imputation"), action="view"
            ),
        },
    )


class TestCLARiTIRoleDeserialization:
    """Tests for CLARiTI role field deserialization."""

    def test_clariti_checkbox_value_1(self):
        """Test that checkbox value "1" deserializes to True."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{
                    "loc_clariti_role___u01copi": "1",
                    "loc_clariti_role___pi": "1",
                    "ind_clar_core_role___admin": "1",
                }
            ),
            by_alias=True,
        )
        assert auths.loc_clariti_role___u01copi is True
        assert auths.loc_clariti_role___pi is True
        assert auths.ind_clar_core_role___admin is True

    def test_clariti_checkbox_value_0(self):
        """Test that checkbox value "0" deserializes to None."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{
                    "loc_clariti_role___u01copi": "0",
                    "loc_clariti_role___pi": "0",
                    "ind_clar_core_role___admin": "0",
                }
            ),
            by_alias=True,
        )
        assert auths.loc_clariti_role___u01copi is None
        assert auths.loc_clariti_role___pi is None
        assert auths.ind_clar_core_role___admin is None

    def test_clariti_checkbox_empty_string(self):
        """Test that empty string deserializes to None."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{
                    "loc_clariti_role___u01copi": "",
                    "loc_clariti_role___pi": "",
                    "ind_clar_core_role___admin": "",
                }
            ),
            by_alias=True,
        )
        assert auths.loc_clariti_role___u01copi is None
        assert auths.loc_clariti_role___pi is None
        assert auths.ind_clar_core_role___admin is None

    def test_clariti_missing_fields(self):
        """Test that missing CLARiTI fields default to None."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(),
            by_alias=True,
        )
        # All CLARiTI role fields should default to None
        assert auths.loc_clariti_role___u01copi is None
        assert auths.loc_clariti_role___pi is None
        assert auths.loc_clariti_role___piadmin is None
        assert auths.loc_clariti_role___copi is None
        assert auths.loc_clariti_role___subawardadmin is None
        assert auths.loc_clariti_role___addlsubaward is None
        assert auths.loc_clariti_role___studycoord is None
        assert auths.loc_clariti_role___mpi is None
        assert auths.loc_clariti_role___orecore is None
        assert auths.loc_clariti_role___crl is None
        assert auths.loc_clariti_role___advancedmri is None
        assert auths.loc_clariti_role___physicist is None
        assert auths.loc_clariti_role___addlimaging is None
        assert auths.loc_clariti_role___reg is None
        assert auths.ind_clar_core_role___admin is None

    def test_clariti_mixed_with_non_clariti_fields(self):
        """Test that CLARiTI fields work alongside existing fields."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                web_report_access___web="1",
                scan_dashboard_access_level="ViewAccess",
                p30_naccid_enroll_access_level="ViewAccess",
                p30_clin_forms_access_level="SubmitAudit",
                cl_clin_forms_access_level="ViewAccess",
                cl_pay_access_level="ViewAccess",
                **{
                    "loc_clariti_role___u01copi": "1",
                    "loc_clariti_role___mpi": "1",
                    "ind_clar_core_role___admin": "1",
                },
            ),
            by_alias=True,
        )
        # Verify CLARiTI fields
        assert auths.loc_clariti_role___u01copi is True
        assert auths.loc_clariti_role___mpi is True
        assert auths.ind_clar_core_role___admin is True
        # Verify existing fields still work
        assert auths.adrc_datatype_enrollment_access_level == "ViewAccess"
        assert auths.adrc_datatype_form_access_level == "SubmitAudit"
        assert auths.clariti_datatype_form_access_level == "ViewAccess"
        assert auths.clariti_dashboard_pay_access_level == "ViewAccess"

    def test_backward_compatibility_without_clariti_fields(self):
        """Test that REDCap reports without CLARiTI fields still work."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                p30_naccid_enroll_access_level="ViewAccess",
                p30_clin_forms_access_level="SubmitAudit",
                p30_imaging_access_level="SubmitAudit",
                p30_flbm_access_level="SubmitAudit",
                p30_genetic_access_level="ViewAccess",
                contact_company_name="an institution",
                archive_contact="0",
            ),
            by_alias=True,
        )
        assert auths
        assert not auths.inactive
        # All CLARiTI fields should be None
        assert auths.loc_clariti_role___u01copi is None
        assert auths.ind_clar_core_role___admin is None
        # Existing functionality should work
        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, CenterUserEntry)
        assert user_entry.active
        assert user_entry.adcid == 999

    def test_all_organizational_roles(self):
        """Test all 14 organizational role fields."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{
                    "loc_clariti_role___u01copi": "1",
                    "loc_clariti_role___pi": "1",
                    "loc_clariti_role___piadmin": "1",
                    "loc_clariti_role___copi": "1",
                    "loc_clariti_role___subawardadmin": "1",
                    "loc_clariti_role___addlsubaward": "1",
                    "loc_clariti_role___studycoord": "1",
                    "loc_clariti_role___mpi": "1",
                    "loc_clariti_role___orecore": "1",
                    "loc_clariti_role___crl": "1",
                    "loc_clariti_role___advancedmri": "1",
                    "loc_clariti_role___physicist": "1",
                    "loc_clariti_role___addlimaging": "1",
                    "loc_clariti_role___reg": "1",
                }
            ),
            by_alias=True,
        )
        # Verify all 14 organizational roles
        assert auths.loc_clariti_role___u01copi is True
        assert auths.loc_clariti_role___pi is True
        assert auths.loc_clariti_role___piadmin is True
        assert auths.loc_clariti_role___copi is True
        assert auths.loc_clariti_role___subawardadmin is True
        assert auths.loc_clariti_role___addlsubaward is True
        assert auths.loc_clariti_role___studycoord is True
        assert auths.loc_clariti_role___mpi is True
        assert auths.loc_clariti_role___orecore is True
        assert auths.loc_clariti_role___crl is True
        assert auths.loc_clariti_role___advancedmri is True
        assert auths.loc_clariti_role___physicist is True
        assert auths.loc_clariti_role___addlimaging is True
        assert auths.loc_clariti_role___reg is True


class TestCLARiTIStudyAccessMapIntegration:
    """Integration tests for CLARiTI role mapping with StudyAccessMap."""

    def test_clariti_activities_added_to_study_map(self):
        """Test that CLARiTI activities are added to study_map with
        study_id='clariti'."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{"loc_clariti_role___u01copi": "1"},
            ),
            by_alias=True,
        )

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = None
        for auth in user_entry.study_authorizations:
            if auth.study_id == "clariti":
                clariti_auth = auth
                break

        assert clariti_auth is not None
        assert clariti_auth.study_id == "clariti"
        # Should have both payment-tracker and enrollment activities
        # (u01copi is both a payment role and an organizational role)
        assert len(clariti_auth.activities) == 2

        from users.authorizations import DashboardResource

        # Check for payment-tracker activity
        payment_tracker_resource = DashboardResource(dashboard="payment-tracker")
        assert payment_tracker_resource in clariti_auth.activities
        assert clariti_auth.activities[payment_tracker_resource].action == "view"

        # Check for enrollment activity
        enrollment_resource = DashboardResource(dashboard="enrollment")
        assert enrollment_resource in clariti_auth.activities
        assert clariti_auth.activities[enrollment_resource].action == "view"

    def test_multiple_clariti_activities_added_correctly(self):
        """Test that multiple CLARiTI activities are added correctly."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                **{
                    "loc_clariti_role___u01copi": "1",
                    "loc_clariti_role___mpi": "1",
                },
            ),
            by_alias=True,
        )

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, CenterUserEntry)

        # Find CLARiTI study authorizations
        clariti_auth = None
        for auth in user_entry.study_authorizations:
            if auth.study_id == "clariti":
                clariti_auth = auth
                break

        assert clariti_auth is not None
        assert clariti_auth.study_id == "clariti"
        # Should have both payment-tracker and enrollment activities
        assert len(clariti_auth.activities) == 2

        from users.authorizations import DashboardResource

        # Check for payment-tracker activity
        payment_tracker_resource = DashboardResource(dashboard="payment-tracker")
        assert payment_tracker_resource in clariti_auth.activities
        assert clariti_auth.activities[payment_tracker_resource].action == "view"

        # Check for enrollment activity
        enrollment_resource = DashboardResource(dashboard="enrollment")
        assert enrollment_resource in clariti_auth.activities
        assert clariti_auth.activities[enrollment_resource].action == "view"

    def test_empty_activity_list_no_study_entry(self):
        """Test that empty activity list doesn't create study entry."""
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(),
            by_alias=True,
        )

        user_entry = auths.to_user_entry()
        assert user_entry and isinstance(user_entry, CenterUserEntry)

        # Should not have CLARiTI study authorizations
        clariti_auth = None
        for auth in user_entry.study_authorizations:
            if auth.study_id == "clariti":
                clariti_auth = auth
                break

        assert clariti_auth is None


class TestToUserEntryInactiveBypass:
    """Tests for to_user_entry() inactive bypass behavior.

    Validates Requirements 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3.
    """

    def test_archived_record_with_both_flags_false_produces_user_entry(self):
        """Archived record with both flags false produces UserEntry with
        active=False (not None).

        Validates: Requirements 3.1, 5.1, 5.2, 5.3
        """
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                archive_contact="1",
                permissions_approval="0",
                signed_agreement_status_num_ct="0",
            ),
            by_alias=True,
        )
        assert auths.inactive
        assert not auths.permissions_approval
        assert not auths.signed_user_agreement

        user_entry = auths.to_user_entry()
        assert user_entry is not None
        assert isinstance(user_entry, UserEntry)
        assert user_entry.active is False
        assert user_entry.name.first_name == "Test"
        assert user_entry.name.last_name == "User"
        assert user_entry.email == "user@institution.edu"
        assert user_entry.auth_email == "user@institution.edu"
        assert user_entry.approved is False

    def test_archived_record_produces_base_user_entry(self):
        """Archived record produces UserEntry (not ActiveUserEntry or
        CenterUserEntry).

        Validates: Requirements 3.1, 5.1
        """
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                archive_contact="1",
                permissions_approval="1",
                signed_agreement_status_num_ct="1",
                contact_company_name="an institution",
            ),
            by_alias=True,
        )
        assert auths.inactive

        user_entry = auths.to_user_entry()
        assert user_entry is not None
        assert type(user_entry) is UserEntry
        assert not isinstance(user_entry, ActiveUserEntry)
        assert not isinstance(user_entry, CenterUserEntry)
        assert user_entry.active is False

    def test_non_archived_with_flags_true_and_adcid_produces_center_user_entry(self):
        """Non-archived record with both flags true and adcid produces
        CenterUserEntry.

        Validates: Requirements 3.4
        """
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                archive_contact="0",
                permissions_approval="1",
                signed_agreement_status_num_ct="1",
                contact_company_name="an institution",
                adcid="999",
            ),
            by_alias=True,
        )
        assert not auths.inactive
        assert auths.permissions_approval
        assert auths.signed_user_agreement

        user_entry = auths.to_user_entry()
        assert user_entry is not None
        assert isinstance(user_entry, CenterUserEntry)
        assert user_entry.active is True
        assert user_entry.adcid == 999

    def test_non_archived_with_flags_true_and_no_adcid_produces_active_user_entry(
        self,
    ):
        """Non-archived record with both flags true and no adcid produces
        ActiveUserEntry.

        Validates: Requirements 3.4
        """
        auths = DirectoryAuthorizations.model_validate(
            create_directory_entry(
                archive_contact="0",
                permissions_approval="1",
                signed_agreement_status_num_ct="1",
                adcid="",
            ),
            by_alias=True,
        )
        assert not auths.inactive
        assert auths.permissions_approval
        assert auths.signed_user_agreement

        user_entry = auths.to_user_entry()
        assert user_entry is not None
        assert isinstance(user_entry, ActiveUserEntry)
        assert not isinstance(user_entry, CenterUserEntry)
        assert user_entry.active is True
