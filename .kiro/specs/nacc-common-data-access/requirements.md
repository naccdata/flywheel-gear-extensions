# Requirements Document

## Introduction

The `nacc-common` package (v3.0.0) serves as the abstraction layer between Alzheimer's Disease Research Centers and the NACC Data Platform (built on Flywheel). Centers use `nacc-common` through the [data-platform-demos](https://github.com/naccdata/data-platform-demos) as templates for their own automation scripts. The goal is to minimize direct Flywheel SDK coupling so that a future platform migration does not break center scripts.

The existing public API in `error_data.py` (`get_error_data`, `get_status_data`) establishes the right pattern: accept a Flywheel `Project`, hide internal visitor/QC-model machinery, and return plain dicts. This feature extends that pattern by exposing additional capabilities already implemented in `nacc-common` internals through similarly simple, dict-returning functions. It also adds PTID filtering to the existing functions.

Centers should think in terms of "submissions" — identified by PTID, date, and module — rather than implementation-specific storage details. The underlying storage mechanism (currently file-based) is an internal detail that may be refactored in the future.

## Glossary

- **Project**: A Flywheel `Project` object representing a center's pipeline project, obtained via `get_project()` in `pipeline.py`
- **Submission**: A logical unit of data submitted by a center, uniquely identified by the combination of PTID, date, and module. The underlying storage representation is an internal implementation detail
- **QCStatus**: A string literal type with values `"PASS"`, `"FAIL"`, or `"IN REVIEW"`, representing the validation state of a pipeline stage or submission
- **PTID**: A participant identifier (center-assigned), matching the pattern `[!-~]{1,10}` (printable non-whitespace characters, 1-10 chars)
- **Module**: A data module identifier (e.g., UDS, LBD, FTLD, NP), always stored and compared in uppercase
- **Stage**: The name of a processing step in the pipeline (e.g., `"form_qc_checker"`)
- **Submission_Identifier**: An opaque identifier for a specific submission within a project, used to look up per-submission details. Centers receive these identifiers from listing functions and pass them to detail functions without needing to understand the identifier format
- **FileQCModel**: Internal Pydantic model (`error_models.py`) representing the QC data structure, containing per-stage validation results (internal, not exposed to centers)
- **DataIdentification**: Internal Pydantic model (`data_identification.py`) representing composed visit metadata (participant, date, visit, form/image data) with a flattened serialization (internal, not exposed to centers)
- **FileError**: Internal Pydantic model representing a single error found during pipeline processing, with fields for type, code, message, location, and context (internal, not exposed to centers)
- **ProjectReportVisitor**: Internal visitor class (`qc_report.py`) that traverses submissions in a project, already supporting `ptid_set` and `modules` filtering (internal, not exposed to centers)

## Requirements

### Requirement 1: PTID Filtering for Error Data

**User Story:** As a center developer, I want to filter error data by participant ID, so that I can retrieve errors for specific participants without downloading the entire project's error set.

#### Acceptance Criteria

1. WHEN `get_error_data` is called with a `ptids` parameter containing a set of PTID strings, THE Error_Data_Module SHALL return only error records for submissions whose PTID is in the provided set
2. WHEN `get_error_data` is called without a `ptids` parameter, THE Error_Data_Module SHALL return error records for all submissions, preserving the existing behavior
3. WHEN `get_error_data` is called with both `modules` and `ptids` parameters, THE Error_Data_Module SHALL return only error records matching both filters
4. THE Error_Data_Module SHALL pass the `ptids` parameter through to the internal filtering mechanism

### Requirement 2: PTID Filtering for Status Data

**User Story:** As a center developer, I want to filter status data by participant ID, so that I can retrieve QC status for specific participants without downloading the entire project's status set.

#### Acceptance Criteria

1. WHEN `get_status_data` is called with a `ptids` parameter containing a set of PTID strings, THE Status_Data_Module SHALL return only status records for submissions whose PTID is in the provided set
2. WHEN `get_status_data` is called without a `ptids` parameter, THE Status_Data_Module SHALL return status records for all submissions, preserving the existing behavior
3. WHEN `get_status_data` is called with both `modules` and `ptids` parameters, THE Status_Data_Module SHALL return only status records matching both filters
4. THE Status_Data_Module SHALL pass the `ptids` parameter through to the internal filtering mechanism

### Requirement 3: Per-Submission QC Summary

**User Story:** As a center developer, I want to get a plain-dict QC summary for a specific submission, so that I can check "what happened to my submission?" without working with Flywheel or QC model objects directly.

#### Acceptance Criteria

1. WHEN `get_submission_qc_summary` is called with a project and a Submission_Identifier that resolves to an existing submission, THE QC_Summary_Function SHALL return a dict containing the key `"identifier"` with the Submission_Identifier value
2. WHEN `get_submission_qc_summary` is called with a valid Submission_Identifier, THE QC_Summary_Function SHALL return a dict containing the key `"overall_status"` with the aggregate QC status (one of `"PASS"`, `"FAIL"`, or `"IN REVIEW"`)
3. WHEN `get_submission_qc_summary` is called with a valid Submission_Identifier, THE QC_Summary_Function SHALL return a dict containing the key `"stages"` with a dict mapping each stage name to a dict with keys `"status"` (the stage's QCStatus) and `"error_count"` (the number of errors for that stage)
4. WHEN `get_submission_qc_summary` is called with a Submission_Identifier that does not resolve to an existing submission, THE QC_Summary_Function SHALL return `None`
5. WHEN `get_submission_qc_summary` is called with a Submission_Identifier that resolves to a submission with no QC data, THE QC_Summary_Function SHALL return `None`
6. THE QC_Summary_Function SHALL return a plain `dict`, not a Pydantic model or Flywheel object

### Requirement 4: Per-Submission Error Details

**User Story:** As a center developer, I want to get a flat list of all errors for a specific submission, so that I can inspect individual submission errors without working with Flywheel or QC model objects directly.

#### Acceptance Criteria

1. WHEN `get_submission_errors` is called with a project and a Submission_Identifier that resolves to an existing submission with errors, THE Submission_Error_Function SHALL return a list of dicts, each containing the key `"stage"` with the stage name
2. WHEN `get_submission_errors` is called with a valid Submission_Identifier, THE Submission_Error_Function SHALL include error detail fields (type, code, message, location, and context) in each error dict
3. WHEN `get_submission_errors` is called with a Submission_Identifier that does not resolve to an existing submission, THE Submission_Error_Function SHALL return an empty list
4. WHEN `get_submission_errors` is called with a Submission_Identifier that resolves to a submission with no errors, THE Submission_Error_Function SHALL return an empty list
5. THE Submission_Error_Function SHALL collect errors from all stages, producing a flat list across all stages
6. THE Submission_Error_Function SHALL return a list of plain `dict` objects, not Pydantic models or Flywheel objects

### Requirement 5: Per-Submission Visit Metadata

**User Story:** As a center developer, I want to retrieve visit metadata for a specific submission, so that I can inspect participant and visit information without working with Flywheel objects or internal data models directly.

#### Acceptance Criteria

1. WHEN `get_submission_visit_metadata` is called with a project and a Submission_Identifier that resolves to an existing submission with visit metadata, THE Visit_Metadata_Function SHALL return a plain dict containing the visit metadata fields (participant identifiers, date, visit number, module, and packet as applicable)
2. WHEN `get_submission_visit_metadata` is called with a Submission_Identifier that does not resolve to an existing submission, THE Visit_Metadata_Function SHALL return `None`
3. WHEN `get_submission_visit_metadata` is called with a Submission_Identifier that resolves to a submission with no visit metadata, THE Visit_Metadata_Function SHALL return `None`
4. THE Visit_Metadata_Function SHALL return a plain `dict`, not a Pydantic model or Flywheel object

### Requirement 6: Submission Listing

**User Story:** As a center developer, I want to list all submissions in a project with optional filtering, so that I can understand what submissions exist without working with Flywheel objects or understanding the underlying storage format.

#### Acceptance Criteria

1. WHEN `list_submissions` is called with a `modules` parameter, THE Submission_Listing_Function SHALL include only submissions whose module (compared case-insensitively) is in the provided set
2. WHEN `list_submissions` is called with a `ptids` parameter, THE Submission_Listing_Function SHALL include only submissions whose PTID is in the provided set
3. WHEN `list_submissions` is called with both `modules` and `ptids` parameters, THE Submission_Listing_Function SHALL include only submissions matching both filters
4. WHEN `list_submissions` is called without `modules` or `ptids` parameters, THE Submission_Listing_Function SHALL include all submissions in the project
5. THE Submission_Listing_Function SHALL return a list of dicts, each containing `"identifier"` (the Submission_Identifier), `"ptid"`, `"date"`, and `"module"`
6. THE Submission_Listing_Function SHALL include `"overall_status"` in each dict, set to the aggregate QC status or `None` if the submission has no QC data
7. THE Submission_Listing_Function SHALL return a list of plain `dict` objects, not Pydantic models or Flywheel objects

### Requirement 7: Backward Compatibility

**User Story:** As a center developer with existing scripts, I want the new version of `nacc-common` to be fully backward compatible, so that my existing code continues to work without modification.

#### Acceptance Criteria

1. THE Error_Data_Module SHALL accept calls to `get_error_data` with only `project` and optional `modules` parameters, producing identical results to the current v3.0.0 behavior
2. THE Status_Data_Module SHALL accept calls to `get_status_data` with only `project` and optional `modules` parameters, producing identical results to the current v3.0.0 behavior
3. THE nacc_common Package SHALL not remove, rename, or change the return type of any existing public function
4. THE nacc_common Package SHALL not change the structure of dicts returned by existing functions

### Requirement 8: Plain Dict Return Type Contract

**User Story:** As a center developer, I want all public data access functions to return plain Python dicts and lists, so that I can serialize results to JSON or CSV without depending on nacc-common internal types.

#### Acceptance Criteria

1. THE nacc_common Public_API SHALL return `list[dict[str, Any]]` or `Optional[dict[str, Any]]` from all data access functions
2. THE nacc_common Public_API SHALL not expose Pydantic model instances, Flywheel SDK objects, or internal types in return values
3. THE nacc_common Public_API SHALL produce return values that are directly serializable via `json.dumps()` without custom encoders
