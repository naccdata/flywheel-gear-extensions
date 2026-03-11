# Implementation Plan: CLARiTI Role Mapping

## Overview

This implementation adds support for mapping CLARiTI roles from the NACC directory REDCap report to Activity objects in the user management gear. The implementation follows a 3-phase approach: data model extension, mapping function creation, and integration with existing systems.

The implementation uses Python and extends existing models in the `common` package, with no changes required to the user management gear itself.

**IMPORTANT**: When implementing these tasks, follow the coding guidelines in the workspace steering documents:
- `.kiro/steering/coding-style.md` - Python coding conventions, import organization, gear architecture patterns, dependency injection principles, and testing guidelines
- `.kiro/steering/structure.md` - Project structure, package organization, and file naming conventions
- `.kiro/steering/tech.md` - Technology stack, build system (Pants), and development workflow

## Tasks

- [x] 1. Extend DirectoryAuthorizations data model with CLARiTI role fields
  - [x] 1.1 Add 14 organizational role fields to DirectoryAuthorizations model
    - Add optional boolean fields for loc_clariti_role___u01copi, loc_clariti_role___pi, loc_clariti_role___piadmin, loc_clariti_role___copi, loc_clariti_role___subawardadmin, loc_clariti_role___addlsubaward, loc_clariti_role___studycoord, loc_clariti_role___mpi, loc_clariti_role___orecore, loc_clariti_role___crl, loc_clariti_role___advancedmri, loc_clariti_role___physicist, loc_clariti_role___addlimaging, loc_clariti_role___reg
    - Use Field with alias parameter to match REDCap field names
    - Set default=None for all fields
    - _Requirements: 7.1, 1.1-1.14_

  - [x] 1.2 Add individual role field to DirectoryAuthorizations model
    - Add optional boolean field for ind_clar_core_role___admin
    - Use Field with alias parameter
    - Set default=None
    - _Requirements: 7.2, 2.1_

  - [x] 1.3 Add field validator for REDCap checkbox conversion
    - Create @field_validator for all 15 CLARiTI checkbox fields
    - Convert "1" to True, "0" or "" to None
    - Handle boolean and None values passthrough
    - Use mode="before" for pre-validation conversion
    - _Requirements: 7.4_

  - [x] 1.4 Write unit tests for DirectoryAuthorizations deserialization
    - Test deserialization with all checkbox values ("1", "0", "", None)
    - Test deserialization with missing CLARiTI fields
    - Test deserialization with mixed CLARiTI and non-CLARiTI fields
    - Test backward compatibility with REDCap reports without CLARiTI fields
    - _Requirements: 7.4, 10.1_

- [x] 2. Create CLARiTI role mapping function
  - [x] 2.1 Create new clariti_roles.py module
    - Create file at common/src/python/users/clariti_roles.py
    - Add module docstring explaining CLARiTI role mapping
    - Import required types: DirectoryAuthorizations, Activity, DashboardResource
    - _Requirements: 8.1_

  - [x] 2.2 Implement map_clariti_roles_to_activities() function
    - Accept DirectoryAuthorizations parameter
    - Return list[Activity]
    - Check for payment roles (7 fields) and cl_pay_access_level="ViewAccess"
    - Check for organizational roles (14 fields)
    - Check for admin core member role
    - Build set of Activity objects for deduplication
    - Return list of unique activities
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 2.3 Write unit tests for mapping function
    - Test payment role mapping (single role, multiple roles)
    - Test organizational role mapping (single role, multiple roles)
    - Test admin core member mapping
    - Test cl_pay_access_level="ViewAccess" mapping
    - Test empty DirectoryAuthorizations (no CLARiTI roles)
    - Test deduplication with overlapping roles
    - Test edge cases: all roles set, no roles set, mixed scenarios
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 2.4 Write property test for payment role parsing (Property 1)
    - **Property 1: Payment Role Field Parsing**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**
    - Generate DirectoryAuthorizations with random payment role combinations
    - Verify all payment role fields parse correctly as boolean
    - Use hypothesis with min_size=1 for at least one payment role
    - Minimum 100 iterations

  - [ ]* 2.5 Write property test for organizational role parsing (Property 2)
    - **Property 2: Organizational Role Field Parsing**
    - **Validates: Requirements 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14**
    - Generate DirectoryAuthorizations with random organizational role combinations
    - Verify all organizational role fields parse correctly as boolean
    - Use hypothesis with min_size=1 for at least one organizational role
    - Minimum 100 iterations

  - [ ]* 2.6 Write property test for admin core member parsing (Property 3)
    - **Property 3: Admin Core Member Parsing**
    - **Validates: Requirements 2.1**
    - Generate DirectoryAuthorizations with ind_clar_core_role___admin=True
    - Verify field parses correctly as boolean
    - Minimum 100 iterations

  - [ ]* 2.7 Write property test for payment access level parsing (Property 4)
    - **Property 4: Payment Access Level Parsing**
    - **Validates: Requirements 3.1**
    - Generate DirectoryAuthorizations with clariti_dashboard_pay_access_level="ViewAccess"
    - Verify field parses correctly and grants payment tracker access
    - Minimum 100 iterations

  - [ ]* 2.8 Write property test for payment role to activity mapping (Property 5)
    - **Property 5: Payment Role to Activity Mapping**
    - **Validates: Requirements 4.1, 8.2**
    - Generate DirectoryAuthorizations with at least one payment role
    - Verify mapping function returns payment-tracker view activity
    - Minimum 100 iterations

  - [ ]* 2.9 Write property test for payment access level to activity mapping (Property 6)
    - **Property 6: Payment Access Level to Activity Mapping**
    - **Validates: Requirements 4.2**
    - Generate DirectoryAuthorizations with clariti_dashboard_pay_access_level="ViewAccess"
    - Verify mapping function returns payment-tracker view activity
    - Minimum 100 iterations

  - [x] 2.10 Write property test for activity deduplication (Property 7)
    - **Property 7: Activity Deduplication**
    - **Validates: Requirements 4.3, 5.2, 6.3, 6.4, 8.6**
    - Generate DirectoryAuthorizations with multiple overlapping roles
    - Verify exactly one activity per dashboard regardless of role count
    - Test with payment roles + admin + cl_pay_access_level combinations
    - Test with organizational roles + admin combinations
    - Minimum 100 iterations

  - [ ]* 2.11 Write property test for organizational role to activity mapping (Property 8)
    - **Property 8: Organizational Role to Activity Mapping**
    - **Validates: Requirements 5.1, 8.3**
    - Generate DirectoryAuthorizations with at least one organizational role
    - Verify mapping function returns enrollment view activity
    - Minimum 100 iterations

  - [ ]* 2.12 Write property test for admin role to payment tracker mapping (Property 9)
    - **Property 9: Admin Role to Payment Tracker Mapping**
    - **Validates: Requirements 6.1, 8.4**
    - Generate DirectoryAuthorizations with ind_clar_core_role___admin=True
    - Verify mapping function returns payment-tracker view activity
    - Minimum 100 iterations

  - [ ]* 2.13 Write property test for admin role to enrollment mapping (Property 10)
    - **Property 10: Admin Role to Enrollment Mapping**
    - **Validates: Requirements 6.2, 8.4**
    - Generate DirectoryAuthorizations with ind_clar_core_role___admin=True
    - Verify mapping function returns enrollment view activity
    - Minimum 100 iterations

  - [ ]* 2.14 Write property test for REDCap checkbox deserialization (Property 11)
    - **Property 11: REDCap Checkbox Deserialization**
    - **Validates: Requirements 7.4**
    - Generate valid REDCap report JSON with random CLARiTI checkbox values
    - Verify deserialization succeeds and produces boolean values
    - Test with "1", "0", "", and missing fields
    - Minimum 100 iterations

  - [ ]* 2.15 Write property test for access level deserialization (Property 12)
    - **Property 12: Access Level Deserialization**
    - **Validates: Requirements 7.5**
    - Generate valid REDCap report JSON with cl_pay_access_level field
    - Verify deserialization succeeds and produces AuthorizationAccessLevel value
    - Test with "ViewAccess", "NoAccess", and empty values
    - Minimum 100 iterations

- [x] 3. Integrate CLARiTI mapping with StudyAccessMap
  - [x] 3.1 Modify __parse_fields() in nacc_directory.py
    - Import map_clariti_roles_to_activities function
    - Call mapping function after existing field parsing logic
    - Iterate over returned activities and add to study_map with study_id="clariti"
    - Use access_level="ViewAccess" for all CLARiTI activities
    - _Requirements: 8.1, 9.1_

  - [x] 3.2 Write integration tests for StudyAccessMap
    - Test that CLARiTI activities are added to study_map with study_id="clariti"
    - Test that multiple CLARiTI activities are added correctly
    - Test that empty activity list doesn't create study entry
    - _Requirements: 9.1_

  - [ ]* 3.3 Write property test for CLARiTI study authorizations integration (Property 13)
    - **Property 13: CLARiTI Study Authorizations Integration**
    - **Validates: Requirements 9.1**
    - Generate DirectoryAuthorizations with random CLARiTI roles
    - Call to_user_entry() and verify StudyAuthorizations for "clariti" exists
    - Verify activities match mapped CLARiTI activities
    - Minimum 100 iterations

  - [ ]* 3.4 Write property test for multi-study authorizations (Property 14)
    - **Property 14: Multi-Study Authorizations**
    - **Validates: Requirements 9.2**
    - Generate DirectoryAuthorizations with both ADRC and CLARiTI roles
    - Call to_user_entry() and verify separate StudyAuthorizations for "adrc" and "clariti"
    - Minimum 100 iterations

  - [ ]* 3.5 Write property test for CLARiTI-only authorizations (Property 15)
    - **Property 15: CLARiTI-Only Authorizations**
    - **Validates: Requirements 9.3**
    - Generate DirectoryAuthorizations with CLARiTI roles but no ADRC roles
    - Call to_user_entry() and verify only "clariti" StudyAuthorizations exists
    - Minimum 100 iterations

  - [x] 3.6 Write property test for backward compatibility (Property 16)
    - **Property 16: Backward Compatibility**
    - **Validates: Requirements 10.1**
    - Generate DirectoryAuthorizations without CLARiTI role fields
    - Verify deserialization and processing succeed without errors
    - Verify no CLARiTI StudyAuthorizations are created
    - Minimum 100 iterations

  - [ ]* 3.7 Write property test for independent study processing (Property 17)
    - **Property 17: Independent Study Processing**
    - **Validates: Requirements 10.3**
    - Generate DirectoryAuthorizations with CLARiTI and other study roles
    - Call to_user_entry() and verify StudyAuthorizations for all applicable studies
    - Verify each study's activities are independent
    - Test with combinations of ADRC, NCRAD, NIAGADS, LEADS, DVCID, and CLARiTI
    - Minimum 100 iterations

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties with minimum 100 iterations
- Unit tests validate specific examples and edge cases
- The design uses Python, so all implementation will be in Python
- No changes required to user management gear - integration happens at the common library level
- All CLARiTI fields are optional, ensuring backward compatibility
