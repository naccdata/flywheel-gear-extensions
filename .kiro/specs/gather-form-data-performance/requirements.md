# Requirements Document

## Introduction

The gather_form_data gear currently processes a CSV file of NACCIDs sequentially — one Flywheel API call per participant per operation — resulting in runtime that scales linearly with participant count and becomes prohibitively slow for large request files. The center_form_export gear has already proven a batched + concurrent approach (`gather_project_data`) in production. This spec refactors gather_form_data to adopt the same two-phase pattern (batch-resolve NACCIDs, then call `gather_project_data` with resolved subject IDs), while preserving per-NACCID error reporting, the existing output format, and the QC/tagging behavior.

## Glossary

- **Gather_Form_Data_Gear**: The Flywheel gear that reads a CSV of NACCIDs, resolves each to a Flywheel subject, and gathers form module data for those subjects
- **Request_CSV**: The input CSV file containing one NACCID per row, specifying which participants to gather data for
- **NACCID**: A unique participant identifier (pattern `NACC\d{6}`) used as the subject label in Flywheel
- **Subject_Resolution**: The process of translating NACCIDs into Flywheel subject IDs, validating that each NACCID exists and belongs to an expected project
- **OR_List_Query**: A Flywheel finder syntax (`label=|[id1,id2,...]`) that matches multiple values in a single API call
- **Batch_Size**: A configurable parameter controlling how many subject IDs are included in a single OR-list query (default 100)
- **Reload_Workers**: A configurable parameter controlling the number of concurrent threads used to reload file metadata (default 10)
- **Module_Data_Gatherer**: The shared library class that collects `file.info` form data for a given module, supporting both per-subject queries (`gather_request_data`) and batched-subject-id queries (`gather_project_data`)
- **Project_Matcher**: A regex pattern that matches expected project names (unqualified and study-id-suffixed variants) used during subject resolution to filter subjects by project membership
- **Error_Writer**: The component that collects per-NACCID errors and warnings for inclusion in QC metadata

## Requirements

### Requirement 1: Batch NACCID Resolution

**User Story:** As a data manager, I want the gear to resolve all NACCIDs in a single pass using batched API calls, so that the resolution phase completes in seconds rather than minutes.

#### Acceptance Criteria

1. WHEN a Request_CSV is read, THE Gather_Form_Data_Gear SHALL collect all NACCIDs from the file, validate each against the NACCID pattern, and report validation errors via the Error_Writer before proceeding to resolution
2. WHEN valid NACCIDs are collected, THE Gather_Form_Data_Gear SHALL resolve them to Flywheel subjects using OR_List_Query syntax (`label=|[id1,id2,...]`) with batches of at most Batch_Size NACCIDs per query, scoped to the expected project (`parents.project=<project_id>`)
3. WHEN a NACCID in the batch response has no matching subject in any expected project, THE Gather_Form_Data_Gear SHALL report a "no-participant" error via the Error_Writer identifying that NACCID, consistent with the current error format
4. WHEN resolution completes, THE Gather_Form_Data_Gear SHALL produce a list of resolved subject IDs corresponding to the matched NACCIDs, with duplicates preserved if a NACCID matches multiple subjects across expected projects

### Requirement 2: Batched Data Gathering via gather_project_data

**User Story:** As a data manager, I want the gear to gather form data using the proven batched + concurrent pattern from center_form_export, so that file queries and reloads are dramatically faster.

#### Acceptance Criteria

1. WHEN subject IDs are resolved, THE Gather_Form_Data_Gear SHALL call `gather_project_data` on each Module_Data_Gatherer with the full list of resolved subject IDs
2. WHEN `gather_project_data` is called, THE Module_Data_Gatherer SHALL partition subject IDs into batches of Batch_Size and issue one Flywheel file query per batch using OR-list syntax on `parents.subject`
3. WHEN a batch's file list is returned, THE Module_Data_Gatherer SHALL reload each file's metadata concurrently using Reload_Workers threads, then merge/write results single-threaded
4. THE Gather_Form_Data_Gear SHALL pass the configured Batch_Size and Reload_Workers values through to each `gather_project_data` call

### Requirement 3: Configurable Performance Parameters

**User Story:** As a system operator, I want batch_size and reload_workers to be configurable gear parameters, so that I can tune performance without code changes.

#### Acceptance Criteria

1. THE Gather_Form_Data_Gear SHALL expose a `batch_size` configuration field with a default value of 100
2. THE Gather_Form_Data_Gear SHALL expose a `reload_workers` configuration field with a default value of 10
3. IF batch_size is set to a non-positive integer, THEN THE Gather_Form_Data_Gear SHALL raise a gear execution error before processing begins
4. IF reload_workers is set to a non-positive integer, THEN THE Gather_Form_Data_Gear SHALL raise a gear execution error before processing begins

### Requirement 4: Preserved Output Format

**User Story:** As a downstream consumer of this gear's output, I want the output CSV format to remain identical, so that no downstream pipelines break.

#### Acceptance Criteria

1. THE Gather_Form_Data_Gear SHALL produce one CSV output file per module, named `{output_prefix}-{module}-{date}.csv`, identical to the current naming convention
2. WHERE formver_split is enabled, THE Gather_Form_Data_Gear SHALL produce one CSV per (module, formver) pair, named `{output_prefix}-{module}-{formver_label}-{date}.csv`
3. THE Gather_Form_Data_Gear SHALL produce CSV content with the same columns and row data as the current sequential implementation for identical input

### Requirement 5: Preserved Error Reporting and QC Metadata

**User Story:** As a data manager, I want per-NACCID error reporting and QC metadata to remain unchanged, so that I can identify missing or invalid participants the same way as before.

#### Acceptance Criteria

1. WHEN one or more NACCIDs fail validation or resolution, THE Gather_Form_Data_Gear SHALL report each failure individually via the Error_Writer with the same error codes and message format as the current implementation
2. WHEN processing completes, THE Gather_Form_Data_Gear SHALL attach QC metadata to the input file with state "PASS" if no errors occurred or "FAIL" if any NACCID was unresolvable or invalid
3. WHEN processing completes, THE Gather_Form_Data_Gear SHALL tag the input file with the gear name, consistent with the current behavior

### Requirement 6: Input Contract Preservation

**User Story:** As an existing user of this gear, I want the input contract (CSV file with NACCID column) and all existing config options to continue working unchanged.

#### Acceptance Criteria

1. THE Gather_Form_Data_Gear SHALL accept the same input file format (CSV with a `naccid` column header, case-insensitive) as the current implementation
2. THE Gather_Form_Data_Gear SHALL continue to accept all existing configuration fields (`project_names`, `modules`, `study_id`, `include_derived`, `formver_split`, `output_file_prefix`) with identical semantics
3. WHEN a Request_CSV contains duplicate NACCIDs, THE Gather_Form_Data_Gear SHALL process each occurrence, matching the current behavior of gathering data for every row
