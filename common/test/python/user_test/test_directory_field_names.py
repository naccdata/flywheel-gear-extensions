"""Unit tests for get_directory_field_names().

Validates that the field derivation function correctly resolves all
REDCap field names from the DirectoryAuthorizations model, including
alias resolution and deduplication.
"""

from users.nacc_directory import get_directory_field_names

# Expected REDCap field names from Requirement 1.2
EXPECTED_REDCAP_FIELDS = [
    "firstname",
    "lastname",
    "email",
    "fw_email",
    "archive_contact",
    "contact_company_name",
    "adcid",
    "web_report_access___web",
    "web_report_access___repdash",
    "p30_naccid_enroll_access_level",
    "p30_clin_forms_access_level",
    "p30_imaging_access_level",
    "p30_flbm_access_level",
    "p30_genetic_access_level",
    "leads_naccid_enroll_access_level",
    "leads_clin_forms_access_level",
    "dvcid_naccid_enroll_access_level",
    "dvcid_clin_forms_access_level",
    "allftd_naccid_enroll_access_level",
    "allftd_clin_forms_access_level",
    "dlbc_naccid_enroll_access_level",
    "dlbc_clin_forms_access_level",
    "cl_clin_forms_access_level",
    "cl_imaging_access_level",
    "cl_flbm_access_level",
    "cl_pay_access_level",
    "cl_ror_access_level",
    "scan_dashboard_access_level",
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
    "ind_clar_core_role___admin",
    "signed_agreement_status_num_ct",
    "permissions_approval",
    "permissions_approval_date",
    "permissions_approval_name",
]


class TestGetDirectoryFieldNames:
    """Tests for get_directory_field_names()."""

    def test_contains_all_expected_fields(self):
        """Test that the returned list contains all expected REDCap field names
        from Requirement 1.2."""
        result = get_directory_field_names()
        result_set = set(result)
        for field in EXPECTED_REDCAP_FIELDS:
            assert field in result_set, f"Missing expected field: {field}"

    def test_no_duplicates(self):
        """Test that the returned list has no duplicate entries."""
        result = get_directory_field_names()
        assert len(result) == len(set(result)), (
            f"Found duplicates: {[f for f in result if result.count(f) > 1]}"
        )

    def test_count_matches_unique_redcap_fields(self):
        """Test that the count matches the number of unique REDCap field names
        expected from the model."""
        result = get_directory_field_names()
        assert len(result) == len(EXPECTED_REDCAP_FIELDS), (
            f"Expected {len(EXPECTED_REDCAP_FIELDS)} fields, got {len(result)}. "
            f"Extra: {set(result) - set(EXPECTED_REDCAP_FIELDS)}, "
            f"Missing: {set(EXPECTED_REDCAP_FIELDS) - set(result)}"
        )

    def test_exact_field_set_matches(self):
        """Test that the returned set of fields exactly matches the expected
        set."""
        result = get_directory_field_names()
        assert set(result) == set(EXPECTED_REDCAP_FIELDS)

    def test_returns_list_of_strings(self):
        """Test that the function returns a list of strings."""
        result = get_directory_field_names()
        assert isinstance(result, list)
        assert all(isinstance(f, str) for f in result)
