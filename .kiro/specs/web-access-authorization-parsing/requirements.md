# Requirements Document

## Introduction

The NACC directory system manages user authorizations for accessing various data types and resources on the Flywheel platform. REDCap directory reports provide user permission data that must be parsed and validated before being converted to Flywheel authorizations.

This feature addresses multiple changes in the REDCap directory report format:

1. The `web_report_access` field changed from a boolean to a checkbox field with multiple values, representing two distinct types of access: general webinars/presentations access and ADRC-specific reports/dashboards access
2. A new `adcid` field was added to provide the center ID separately from `adresearchctr`, with support for "NA" values for users not associated with a specific center (e.g., NACC staff)
3. The system needs to distinguish between different resource types (datatypes, dashboards, webinars) for proper authorization mapping

These changes must be parsed and validated correctly to support current and future authorization mapping to Flywheel projects.

## Glossary

- **Directory_Parser**: The system component that deserializes REDCap directory reports into DirectoryAuthorizations objects
- **REDCap_Report**: A data export from the REDCap directory containing user authorization information
- **Access_Level**: An enumeration with values NoAccess, ViewAccess, or SubmitAudit
- **Web_Access**: Permission to view general webinars and presentations (not study-specific)
- **ADRC_Reports_Access**: Permission to view ADRC program reports and dashboards (ADRC members only)
- **Checkbox_Field**: A REDCap field type that can contain multiple comma-separated values
- **Authorization_Mapping**: The process of converting parsed access levels into Flywheel project permissions
- **Center_ID**: A numeric identifier for an ADRC research center
- **NACC_Staff**: Users associated with NACC organization who are not affiliated with a specific research center
- **Datatype_Resource**: Study-specific data types (enrollment, form, dicom, biomarker, genetic, etc.) that follow the study_datatype_access_level pattern
- **Dashboard_Resource**: Dashboard projects (like ADRC reports) that are project-level resources, not datatypes
- **Webinar_Resource**: General community resources (webinars/presentations) that may not map to Flywheel projects

## Requirements

### Requirement 1: Parse Web Report Access Checkbox Field

**User Story:** As a directory administrator, I want the system to parse the web_report_access checkbox field into separate access levels, so that different types of web access can be managed independently.

#### Acceptance Criteria

1. WHEN the web_report_access field contains an empty string, THE Directory_Parser SHALL set web_access_level to NoAccess
2. WHEN the web_report_access field contains an empty string, THE Directory_Parser SHALL set adrc_reports_access_level to NoAccess
3. WHEN the web_report_access field contains "Web", THE Directory_Parser SHALL set web_access_level to ViewAccess
4. WHEN the web_report_access field contains "Web", THE Directory_Parser SHALL set adrc_reports_access_level to NoAccess
5. WHEN the web_report_access field contains "RepDash", THE Directory_Parser SHALL set web_access_level to NoAccess
6. WHEN the web_report_access field contains "RepDash", THE Directory_Parser SHALL set adrc_reports_access_level to ViewAccess
7. WHEN the web_report_access field contains "Web,RepDash", THE Directory_Parser SHALL set web_access_level to ViewAccess
8. WHEN the web_report_access field contains "Web,RepDash", THE Directory_Parser SHALL set adrc_reports_access_level to ViewAccess

### Requirement 2: Handle Checkbox Field Variations

**User Story:** As a directory administrator, I want the parser to handle variations in checkbox field formatting, so that the system is robust to different data formats.

#### Acceptance Criteria

1. WHEN the web_report_access field contains "RepDash,Web", THE Directory_Parser SHALL set both web_access_level and adrc_reports_access_level to ViewAccess
2. WHEN the web_report_access field contains "Web, RepDash" with a space after the comma, THE Directory_Parser SHALL set both web_access_level and adrc_reports_access_level to ViewAccess
3. WHEN the web_report_access field contains "web" in lowercase, THE Directory_Parser SHALL set web_access_level to NoAccess
4. WHEN the web_report_access field contains "repdash" in lowercase, THE Directory_Parser SHALL set adrc_reports_access_level to NoAccess

### Requirement 3: Validate Access Level Fields

**User Story:** As a system developer, I want both web_access_level and adrc_reports_access_level to be validated as Access_Level types, so that only valid access levels are stored in the system.

#### Acceptance Criteria

1. THE Directory_Parser SHALL validate that web_access_level is one of NoAccess, ViewAccess, or SubmitAudit
2. THE Directory_Parser SHALL validate that adrc_reports_access_level is one of NoAccess, ViewAccess, or SubmitAudit
3. WHEN a DirectoryAuthorizations object is created, THE Directory_Parser SHALL ensure web_access_level has a valid Access_Level value
4. WHEN a DirectoryAuthorizations object is created, THE Directory_Parser SHALL ensure adrc_reports_access_level has a valid Access_Level value

### Requirement 4: Exclude Web Access from Authorization Mapping

**User Story:** As a system developer, I want web_access_level to be excluded from Flywheel authorization mapping, so that general webinar access does not create study-specific permissions.

#### Acceptance Criteria

1. WHEN parsing DirectoryAuthorizations fields for authorization mapping, THE Directory_Parser SHALL skip the web_access_level field
2. WHEN a user has web_access_level set to ViewAccess, THE Directory_Parser SHALL NOT create any Flywheel authorizations for webinar access
3. FOR ALL DirectoryAuthorizations objects with web_access_level set to ViewAccess, converting to UserEntry SHALL NOT include web-related authorizations in the authorizations list

### Requirement 5: Exclude ADRC Reports Access from Current Authorization Mapping

**User Story:** As a system developer, I want adrc_reports_access_level to be excluded from current Flywheel authorization mapping, so that dashboard access can be implemented separately when dashboard projects are available.

#### Acceptance Criteria

1. WHEN parsing DirectoryAuthorizations fields for authorization mapping, THE Directory_Parser SHALL skip the adrc_reports_access_level field
2. WHEN a user has adrc_reports_access_level set to ViewAccess, THE Directory_Parser SHALL NOT create any Flywheel authorizations for dashboard access
3. FOR ALL DirectoryAuthorizations objects with adrc_reports_access_level set to ViewAccess, converting to UserEntry SHALL NOT include reports-related authorizations in the authorizations list

### Requirement 6: Preserve Field Values for Future Use

**User Story:** As a system developer, I want web_access_level and adrc_reports_access_level to be stored in DirectoryAuthorizations objects, so that they can be used for authorization mapping in future implementations.

#### Acceptance Criteria

1. WHEN a DirectoryAuthorizations object is created from a REDCap_Report, THE Directory_Parser SHALL store the parsed web_access_level value
2. WHEN a DirectoryAuthorizations object is created from a REDCap_Report, THE Directory_Parser SHALL store the parsed adrc_reports_access_level value
3. THE Directory_Parser SHALL make web_access_level accessible as a field on DirectoryAuthorizations objects
4. THE Directory_Parser SHALL make adrc_reports_access_level accessible as a field on DirectoryAuthorizations objects

### Requirement 7: Maintain Backward Compatibility

**User Story:** As a system administrator, I want existing authorization parsing to continue working unchanged, so that current user permissions are not affected by the new fields.

#### Acceptance Criteria

1. WHEN parsing study-specific access level fields, THE Directory_Parser SHALL continue to create Flywheel authorizations as before
2. WHEN a DirectoryAuthorizations object contains both web_access_level and study-specific access levels, THE Directory_Parser SHALL create authorizations only for the study-specific fields
3. FOR ALL existing access level fields following the study_datatype_access_level pattern, the parsing behavior SHALL remain unchanged

### Requirement 8: Parse Center ID from adcid Field

**User Story:** As a directory administrator, I want the system to use the new adcid field for center identification, so that center IDs are correctly assigned to users.

#### Acceptance Criteria

1. WHEN a REDCap_Report contains an adcid field with a numeric value, THE Directory_Parser SHALL parse it as the Center_ID
2. WHEN a REDCap_Report contains an adcid field with a numeric string, THE Directory_Parser SHALL convert it to an integer Center_ID
3. THE Directory_Parser SHALL use the adcid field instead of the adresearchctr field for center identification
4. WHEN converting a DirectoryAuthorizations object to an ActiveUserEntry, THE Directory_Parser SHALL use the adcid value for the adcid field

### Requirement 9: Handle NA Center ID Values

**User Story:** As a directory administrator, I want the system to handle "NA" center ID values for NACC staff, so that users not associated with a specific center can be properly represented.

#### Acceptance Criteria

1. WHEN the adcid field contains the string "NA", THE Directory_Parser SHALL parse it as None
2. WHEN the adcid field contains the string "NA", THE Directory_Parser SHALL NOT raise a validation error
3. WHEN a DirectoryAuthorizations object has adcid set to None, THE Directory_Parser SHALL allow conversion to UserEntry
4. THE Directory_Parser SHALL define adcid as an Optional integer type to support None values

### Requirement 10: Distinguish Resource Types

**User Story:** As a system developer, I want the system to distinguish between datatype, dashboard, and webinar resources, so that different resource types can be mapped to appropriate Flywheel structures.

#### Acceptance Criteria

1. WHEN parsing access level fields, THE Directory_Parser SHALL identify fields matching the study_datatype_access_level pattern as Datatype_Resource permissions
2. WHEN parsing the adrc_reports_access_level field, THE Directory_Parser SHALL identify it as a Dashboard_Resource permission
3. WHEN parsing the web_access_level field, THE Directory_Parser SHALL identify it as a Webinar_Resource permission
4. THE Directory_Parser SHALL only create Flywheel authorizations for Datatype_Resource permissions in the current implementation
5. THE Directory_Parser SHALL preserve Dashboard_Resource and Webinar_Resource permissions for future authorization mapping
