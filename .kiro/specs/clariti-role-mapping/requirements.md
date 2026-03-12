# Requirements Document: CLARiTI Role Mapping

## Introduction

This feature adds support for mapping CLARiTI roles from the NACC directory REDCap report to Activity objects in the user management gear. CLARiTI (Clinical Research in Alzheimer's and Related Dementias Imaging and Translational Informatics) is a program that requires role-based authorization for accessing payment tracking and enrollment dashboards.

The user management gear currently handles site-level permissions for NACC centers. This feature extends the authorization system to support CLARiTI-specific roles while maintaining compatibility with the existing Activity model structure.

## Glossary

- **CLARiTI**: Clinical Research in Alzheimer's and Related Dementias Imaging and Translational Informatics program
- **REDCap_Report**: The NACC directory report from REDCap containing user role information
- **Activity**: An authorization object combining an action and a resource (format: "{action}-{resource-prefix}-{resource-name}")
- **DashboardResource**: A resource type representing dashboard access
- **Site**: A NACC research center where resources exist
- **Organizational_Role**: A CLARiTI role assigned at the organizational level (loc_clariti_role___* fields in REDCap)
- **Individual_Role**: A CLARiTI role assigned to an individual (ind_clar_core_role___* fields in REDCap)
- **Payment_Role**: An organizational role that grants payment tracker access (u01copi, pi, piadmin, copi, subawardadmin, addlsubaward, studycoord)
- **Admin_Core_Member**: An individual role that grants enhanced cross-site permissions
- **User_Management_Gear**: The Flywheel gear that processes user authorizations and assigns roles
- **Authorization_System**: The existing system using Activity objects for permission management
- **DirectoryAuthorizations**: The data model for deserializing user permissions from REDCap reports

## Requirements

### Requirement 1: Parse CLARiTI Organizational Roles

**User Story:** As a system administrator, I want the User_Management_Gear to parse CLARiTI organizational roles from the REDCap_Report, so that users receive appropriate site-level permissions.

#### Acceptance Criteria

1. WHEN the REDCap_Report contains loc_clariti_role___u01copi with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
2. WHEN the REDCap_Report contains loc_clariti_role___pi with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
3. WHEN the REDCap_Report contains loc_clariti_role___piadmin with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
4. WHEN the REDCap_Report contains loc_clariti_role___copi with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
5. WHEN the REDCap_Report contains loc_clariti_role___subawardadmin with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
6. WHEN the REDCap_Report contains loc_clariti_role___addlsubaward with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
7. WHEN the REDCap_Report contains loc_clariti_role___studycoord with value "1", THE User_Management_Gear SHALL parse it as a Payment_Role
8. WHEN the REDCap_Report contains loc_clariti_role___mpi with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
9. WHEN the REDCap_Report contains loc_clariti_role___orecore with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
10. WHEN the REDCap_Report contains loc_clariti_role___crl with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
11. WHEN the REDCap_Report contains loc_clariti_role___advancedmri with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
12. WHEN the REDCap_Report contains loc_clariti_role___physicist with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
13. WHEN the REDCap_Report contains loc_clariti_role___addlimaging with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role
14. WHEN the REDCap_Report contains loc_clariti_role___reg with value "1", THE User_Management_Gear SHALL parse it as an Organizational_Role

### Requirement 2: Parse CLARiTI Individual Roles

**User Story:** As a system administrator, I want the User_Management_Gear to parse CLARiTI individual roles from the REDCap_Report, so that admin users receive enhanced permissions.

#### Acceptance Criteria

1. WHEN the REDCap_Report contains ind_clar_core_role___admin with value "1", THE User_Management_Gear SHALL parse it as an Admin_Core_Member role
2. WHEN the REDCap_Report contains ind_clar_core_role___admin with value "0", THE User_Management_Gear SHALL NOT grant Admin_Core_Member permissions
3. WHEN the REDCap_Report does not contain the ind_clar_core_role___admin field, THE User_Management_Gear SHALL NOT grant Admin_Core_Member permissions

### Requirement 3: Parse CLARiTI Permission Fields

**User Story:** As a system administrator, I want the User_Management_Gear to parse individual permission fields from the REDCap_Report, so that users with explicit access grants receive appropriate permissions.

#### Acceptance Criteria

1. WHEN the REDCap_Report contains cl_pay_access_level with value "ViewAccess", THE User_Management_Gear SHALL grant payment tracker view access
2. WHEN the REDCap_Report contains cl_pay_access_level with value "NoAccess", THE User_Management_Gear SHALL NOT grant payment tracker access
3. WHEN the REDCap_Report contains cl_pay_access_level with an empty value, THE User_Management_Gear SHALL NOT grant payment tracker access
4. WHEN the REDCap_Report does not contain the cl_pay_access_level field, THE User_Management_Gear SHALL NOT grant payment tracker access

### Requirement 4: Map Payment Roles to Site-Level Payment Tracker Activity

**User Story:** As a CLARiTI user with a payment role, I want to access my site's payment tracker dashboard, so that I can view payment information for my center.

#### Acceptance Criteria

1. WHEN a user has any Payment_Role, THE Authorization_System SHALL create an Activity with action "view" and DashboardResource with dashboard "payment-tracker"
2. WHEN a user has cl_pay_access_level set to "ViewAccess", THE Authorization_System SHALL create an Activity with action "view" and DashboardResource with dashboard "payment-tracker"
3. WHEN a user has both a Payment_Role and cl_pay_access_level set to "ViewAccess", THE Authorization_System SHALL create exactly one Activity for payment tracker access
4. WHEN a user has neither a Payment_Role nor cl_pay_access_level set to "ViewAccess", THE Authorization_System SHALL NOT create a payment tracker Activity

### Requirement 5: Map All CLARiTI Roles to Site-Level Enrollment Dashboard Activity

**User Story:** As a CLARiTI user with any organizational role, I want to access my site's enrollment dashboard, so that I can view enrollment information for my center.

#### Acceptance Criteria

1. WHEN a user has any Organizational_Role, THE Authorization_System SHALL create an Activity with action "view" and DashboardResource with dashboard "enrollment"
2. WHEN a user has multiple Organizational_Role values, THE Authorization_System SHALL create exactly one Activity for enrollment dashboard access
3. WHEN a user has no Organizational_Role values, THE Authorization_System SHALL NOT create an enrollment dashboard Activity

### Requirement 6: Map Admin Core Member to Enhanced Site-Level Activities

**User Story:** As a CLARiTI admin core member, I want to access both payment tracker and enrollment dashboards for my site, so that I can perform administrative oversight.

#### Acceptance Criteria

1. WHEN a user has the Admin_Core_Member role, THE Authorization_System SHALL create an Activity with action "view" and DashboardResource with dashboard "payment-tracker"
2. WHEN a user has the Admin_Core_Member role, THE Authorization_System SHALL create an Activity with action "view" and DashboardResource with dashboard "enrollment"
3. WHEN a user has the Admin_Core_Member role and also has Payment_Role values, THE Authorization_System SHALL create exactly one Activity for payment tracker access
4. WHEN a user has the Admin_Core_Member role and also has Organizational_Role values, THE Authorization_System SHALL create exactly one Activity for enrollment dashboard access

### Requirement 7: Extend DirectoryAuthorizations Model

**User Story:** As a developer, I want the DirectoryAuthorizations model to include CLARiTI role fields, so that the User_Management_Gear can deserialize CLARiTI roles from REDCap reports.

#### Acceptance Criteria

1. THE DirectoryAuthorizations model SHALL include fields for all 14 organizational role checkboxes (loc_clariti_role___*)
2. THE DirectoryAuthorizations model SHALL include a field for the admin core member checkbox (ind_clar_core_role___admin)
3. THE DirectoryAuthorizations model SHALL include a field for the payment access level (cl_pay_access_level)
4. WHEN deserializing a REDCap_Report, THE DirectoryAuthorizations model SHALL parse checkbox values as boolean or string types
5. WHEN deserializing a REDCap_Report, THE DirectoryAuthorizations model SHALL parse cl_pay_access_level as a string type

### Requirement 8: Create CLARiTI Authorization Mapping Logic

**User Story:** As a developer, I want a mapping function that converts CLARiTI roles to Activity objects, so that the authorization logic is centralized and maintainable.

#### Acceptance Criteria

1. THE User_Management_Gear SHALL provide a function that accepts DirectoryAuthorizations and returns a list of Activity objects
2. WHEN the function receives DirectoryAuthorizations with Payment_Role values, THE function SHALL return an Activity for payment tracker view access
3. WHEN the function receives DirectoryAuthorizations with Organizational_Role values, THE function SHALL return an Activity for enrollment dashboard view access
4. WHEN the function receives DirectoryAuthorizations with Admin_Core_Member role, THE function SHALL return Activity objects for both payment tracker and enrollment dashboard view access
5. WHEN the function receives DirectoryAuthorizations with no CLARiTI roles, THE function SHALL return an empty list
6. THE function SHALL NOT create duplicate Activity objects when multiple roles map to the same permission

### Requirement 9: Integrate CLARiTI Activities into Study Authorizations

**User Story:** As a system administrator, I want CLARiTI activities to be included in study authorizations, so that users receive appropriate Flywheel roles for their CLARiTI permissions.

#### Acceptance Criteria

1. WHEN generating study authorizations for a user with CLARiTI roles, THE User_Management_Gear SHALL include CLARiTI Activity objects in the StudyAuthorizations for study_id "clariti"
2. WHEN a user has both ADRC and CLARiTI roles, THE User_Management_Gear SHALL create separate StudyAuthorizations objects for each study
3. WHEN a user has CLARiTI roles but no ADRC roles, THE User_Management_Gear SHALL create a StudyAuthorizations object only for study_id "clariti"
4. THE User_Management_Gear SHALL apply the same authorization-to-role mapping logic for CLARiTI activities as for other study activities

### Requirement 10: Maintain Backward Compatibility

**User Story:** As a system administrator, I want the CLARiTI role mapping to work alongside existing authorization logic, so that non-CLARiTI users are not affected.

#### Acceptance Criteria

1. WHEN processing a REDCap_Report without CLARiTI role fields, THE User_Management_Gear SHALL process existing authorization fields without errors
2. WHEN processing a REDCap_Report with CLARiTI role fields set to "0" or empty, THE User_Management_Gear SHALL NOT create CLARiTI Activity objects
3. THE User_Management_Gear SHALL continue to process ADRC, NCRAD, NIAGADS, LEADS, and DVCID authorizations independently of CLARiTI authorizations
4. THE Authorization_System SHALL support Activity objects with DashboardResource for both CLARiTI and non-CLARiTI dashboards

