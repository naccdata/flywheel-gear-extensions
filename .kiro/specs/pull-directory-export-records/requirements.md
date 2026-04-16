# Requirements Document

## Introduction

The pull-directory gear currently retrieves user directory data from REDCap using `REDCapReportConnection.get_report_records()`, which pulls a pre-configured report. This report does not include all fields that `DirectoryAuthorizations` expects to parse (e.g., CLARiTI role checkbox fields, `signed_agreement_status_num_ct`). The gear needs to be refactored to use `REDCapProject.export_records()` with an explicit list of all expected fields, and then filter the results client-side to keep only entries where `permissions_approval == '1'`.

## Glossary

- **Pull_Directory_Gear**: The Flywheel gear (`gear/pull_directory`) that retrieves user permission data from the NACC Directory REDCap project and converts it to a YAML file consumed by the user management gear.
- **DirectoryAuthorizations**: A Pydantic model (`common/src/python/users/nacc_directory.py`) that deserializes REDCap record data into structured user authorization objects. It defines all expected fields via aliases.
- **REDCapReportConnection**: A class in the `redcap_api` package that connects to a REDCap project and retrieves records from a specific pre-configured report by report ID.
- **REDCapProject**: A class in the `redcap_api` package that provides `export_records()` for exporting records from a REDCap project with explicit field lists, filters, and other parameters.
- **REDCapConnection**: The base connection class in the `redcap_api` package that provides HTTP request methods for communicating with the REDCap API. Parent class of `REDCapReportConnection`.
- **ParameterStore**: The AWS SSM parameter store wrapper (`common/src/python/inputs/parameter_store.py`) that retrieves REDCap connection credentials (URL, token, and optionally report ID).
- **DirectoryPullVisitor**: The gear execution visitor class in `run.py` that orchestrates the pull-directory gear lifecycle.
- **Expected_Fields**: The complete set of REDCap field names (aliases) that `DirectoryAuthorizations` requires for deserialization, including identity fields, access level fields, CLARiTI role checkbox fields, and approval fields.

## Requirements

### Requirement 1: Replace Report-Based Data Retrieval with Field-Based Export

**User Story:** As a platform administrator, I want the pull-directory gear to export records using explicit field names, so that all fields required by DirectoryAuthorizations are included in the data retrieval.

#### Acceptance Criteria

1. WHEN the Pull_Directory_Gear retrieves user data, THE Pull_Directory_Gear SHALL use `REDCapProject.export_records()` with an explicit list of Expected_Fields instead of `REDCapReportConnection.get_report_records()`.
2. THE Pull_Directory_Gear SHALL request all fields defined as aliases in the DirectoryAuthorizations model, including: `firstname`, `lastname`, `email`, `fw_email`, `archive_contact`, `contact_company_name`, `adcid`, `web_report_access`, `study_selections`, `p30_naccid_enroll_access_level`, `p30_clin_forms_access_level`, `p30_imaging_access_level`, `p30_flbm_access_level`, `p30_genetic_access_level`, `affiliated_study`, `leads_naccid_enroll_access_level`, `leads_clin_forms_access_level`, `dvcid_naccid_enroll_access_level`, `dvcid_clin_forms_access_level`, `allftd_naccid_enroll_access_level`, `allftd_clin_forms_access_level`, `dlbc_naccid_enroll_access_level`, `dlbc_clin_forms_access_level`, `cl_clin_forms_access_level`, `cl_imaging_access_level`, `cl_flbm_access_level`, `cl_pay_access_level`, `cl_ror_access_level`, `scan_dashboard_access_level`, `loc_clariti_role___u01copi`, `loc_clariti_role___pi`, `loc_clariti_role___piadmin`, `loc_clariti_role___copi`, `loc_clariti_role___subawardadmin`, `loc_clariti_role___addlsubaward`, `loc_clariti_role___studycoord`, `loc_clariti_role___mpi`, `loc_clariti_role___orecore`, `loc_clariti_role___crl`, `loc_clariti_role___advancedmri`, `loc_clariti_role___physicist`, `loc_clariti_role___addlimaging`, `loc_clariti_role___reg`, `ind_clar_core_role___admin`, `signed_agreement_status_num_ct`, `permissions_approval`, `permissions_approval_date`, `permissions_approval_name`.
3. IF `REDCapProject.export_records()` raises a REDCapConnectionError, THEN THE Pull_Directory_Gear SHALL raise a GearExecutionError with a descriptive message.

### Requirement 2: Filter Records by Permissions Approval

**User Story:** As a platform administrator, I want only approved users included in the directory output, so that unapproved users are excluded before processing.

#### Acceptance Criteria

1. WHEN the Pull_Directory_Gear receives exported records from REDCap, THE Pull_Directory_Gear SHALL filter the records to retain only those where the `permissions_approval` field equals `'1'`.
2. WHEN a record has a `permissions_approval` value other than `'1'`, THE Pull_Directory_Gear SHALL exclude that record from further processing.
3. THE Pull_Directory_Gear SHALL pass only the filtered records to the `run()` function in `main.py`.

### Requirement 3: Update Connection Setup to Use REDCapConnection and REDCapProject

**User Story:** As a developer, I want the gear to use REDCapConnection instead of REDCapReportConnection, so that the gear no longer depends on a report ID for data retrieval.

#### Acceptance Criteria

1. THE DirectoryPullVisitor SHALL create a `REDCapConnection` (not `REDCapReportConnection`) from the parameter store credentials.
2. THE DirectoryPullVisitor SHALL create a `REDCapProject` instance from the `REDCapConnection`.
3. THE ParameterStore credentials for the pull-directory gear SHALL require only `url` and `token` (not `reportid`).
4. WHEN the ParameterStore retrieves credentials for the pull-directory gear, THE ParameterStore SHALL use `get_redcap_parameters()` or an equivalent method that returns `REDCapParameters` (without report ID).

### Requirement 4: Derive Expected Fields from DirectoryAuthorizations Model

**User Story:** As a developer, I want the list of expected fields to be derived from the DirectoryAuthorizations model definition, so that the field list stays in sync with the model and does not require manual maintenance.

#### Acceptance Criteria

1. THE Pull_Directory_Gear SHALL derive the list of REDCap field names from the DirectoryAuthorizations model field definitions (aliases and field names).
2. WHEN a new field is added to the DirectoryAuthorizations model, THE derived field list SHALL automatically include the new field without requiring changes to the Pull_Directory_Gear.
3. THE field derivation logic SHALL resolve Pydantic `alias`, `validation_alias`, and `AliasChoices` to determine the correct REDCap field name for each model field.

### Requirement 5: Maintain Existing Processing and Output Behavior

**User Story:** As a platform administrator, I want the gear output to remain unchanged after the refactoring, so that downstream consumers (user management gear) continue to work without modification.

#### Acceptance Criteria

1. THE Pull_Directory_Gear SHALL produce the same YAML output format as the current implementation for equivalent input data.
2. THE Pull_Directory_Gear SHALL continue to use the `run()` function in `main.py` for converting records to YAML.
3. THE Pull_Directory_Gear SHALL continue to collect and report errors using the UserEventCollector.
4. THE Pull_Directory_Gear SHALL continue to export error details to a CSV file and send email notifications when errors occur.
