# Requirements Document

## Introduction

The `gather-submission-status` gear processes QC log files to produce submission status and error reports. Currently, `ProjectReportVisitor.visit_project()` iterates project-level files sequentially — each matching file requires a `file.reload()` API call to populate `file.info.qc`. For centers with hundreds or thousands of QC log files across multiple projects, this sequential reload is the performance bottleneck.

This spec refactors the gear's `main.py` to bypass `ProjectReportVisitor.visit_project()` and instead orchestrate file reloading concurrently using a `ThreadPoolExecutor`, following the same pattern applied to `gather_form_data` and `center_form_export`. The `nacc-common` library (including `ProjectReportVisitor`, `FileQCReportVisitor`, `FileQCModel`) remains unchanged.

## Glossary

- **Gather_Submission_Status_Gear**: The Flywheel gear that reads a CSV of (adcid, ptid) rows, resolves projects per ADCID, and gathers QC submission status or error data from QC log files
- **QC_Log_File**: A project-level file matching the pattern `{ptid}_{date}_{module}_qc-status.log` that contains QC metadata in `file.info.qc`
- **StatusRequestClusteringVisitor**: The CSV visitor that reads (adcid, ptid) rows, clusters requests by ADCID, and resolves projects per ADCID using `proxy.get_pipeline(adcid)` filtered by project name
- **ProjectReportVisitor**: The nacc-common class that iterates project files, matches QC filenames, reloads files, validates QC info, and applies a `FileQCReportVisitor` to each file (NOT modified by this spec)
- **FileQCReportVisitor**: The nacc-common visitor that processes a single file's QC model and produces report table rows (NOT modified by this spec)
- **FileQCModel**: The nacc-common pydantic model that validates and wraps `file.info.qc` data (NOT modified by this spec)
- **Reload_Workers**: A configurable parameter controlling the number of concurrent threads used to reload file metadata (default 10)
- **QC_Filename_Pattern**: The regex `^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$` used to identify QC log files
- **Error_Writer**: The component that collects per-request errors for inclusion in QC metadata
- **WriterTableVisitor**: The nacc-common visitor that writes report table rows to a DictWriter

## Requirements

### Requirement 1: Concurrent File Reloading

**User Story:** As a data manager, I want QC log file reloads to happen concurrently, so that the gear completes in minutes rather than hours for centers with many QC files.

#### Acceptance Criteria

1. WHEN processing a project's files, THE Gather_Submission_Status_Gear SHALL filter project-level files by QC_Filename_Pattern, ptid_set, and module set before reloading
2. WHEN matching files are identified for a project, THE Gather_Submission_Status_Gear SHALL reload all matching files concurrently using a ThreadPoolExecutor with Reload_Workers threads
3. WHEN files are reloaded, THE Gather_Submission_Status_Gear SHALL process each reloaded file single-threaded through the existing FileQCReportVisitor and FileQCModel path
4. IF a file reload raises an exception, THEN THE Gather_Submission_Status_Gear SHALL log a warning identifying the file and continue processing remaining files

### Requirement 2: Preserved Output Format and Content

**User Story:** As a downstream consumer of this gear's output, I want the output CSV format and content to remain identical, so that no downstream pipelines break.

#### Acceptance Criteria

1. THE Gather_Submission_Status_Gear SHALL produce CSV output with the same columns as the current implementation for both status and error query types
2. THE Gather_Submission_Status_Gear SHALL produce the same row data as the current sequential implementation for identical input, independent of row ordering
3. WHEN query_type is "status", THE Gather_Submission_Status_Gear SHALL use the StatusReportModel fieldnames and status_report_visitor_builder, identical to the current implementation
4. WHEN query_type is "error", THE Gather_Submission_Status_Gear SHALL use the ErrorReportModel fieldnames and error_report_visitor_builder, identical to the current implementation

### Requirement 3: Preserved Error Reporting and QC Metadata

**User Story:** As a data manager, I want error reporting and QC metadata to remain unchanged, so that I can identify issues the same way as before.

#### Acceptance Criteria

1. WHEN the CSV input fails header validation or contains malformed rows, THE Gather_Submission_Status_Gear SHALL report errors via the Error_Writer with the same error codes and message format as the current implementation
2. WHEN an ADCID has no matching projects, THE Gather_Submission_Status_Gear SHALL report a "no-projects" error via the Error_Writer identifying that ADCID, consistent with the current behavior
3. WHEN a file does not have QC info after reload, THE Gather_Submission_Status_Gear SHALL log a warning identifying the file and skip processing, consistent with the current behavior
4. WHEN processing completes, THE Gather_Submission_Status_Gear SHALL attach QC metadata to the input file with state "PASS" if processing succeeded or "FAIL" if errors occurred
5. WHEN processing completes, THE Gather_Submission_Status_Gear SHALL tag the input file with the gear name, consistent with the current behavior

### Requirement 4: Preserved Input Contract

**User Story:** As an existing user of this gear, I want the input contract (CSV file with adcid and ptid columns) and all existing config options to continue working unchanged.

#### Acceptance Criteria

1. THE Gather_Submission_Status_Gear SHALL accept the same input file format (CSV with adcid and ptid column headers, case-insensitive) as the current implementation
2. THE Gather_Submission_Status_Gear SHALL continue to accept all existing configuration fields (admin_group, project_names, modules, query_type, study_id, output_file, dry_run, apikey_path_prefix) with identical semantics
3. THE StatusRequestClusteringVisitor SHALL remain unchanged in behavior, continuing to cluster requests by ADCID and resolve projects via proxy.get_pipeline

### Requirement 5: Configurable Performance Parameter

**User Story:** As a system operator, I want reload_workers to be a configurable gear parameter, so that I can tune concurrency without code changes.

#### Acceptance Criteria

1. THE Gather_Submission_Status_Gear SHALL expose a `reload_workers` configuration field with a default value of 10
2. IF reload_workers is set to a non-positive integer, THEN THE Gather_Submission_Status_Gear SHALL raise a gear execution error before processing begins
3. THE Gather_Submission_Status_Gear SHALL pass the configured reload_workers value to the ThreadPoolExecutor max_workers parameter

### Requirement 6: No Changes to nacc-common

**User Story:** As a library maintainer, I want the nacc-common package to remain unchanged, so that other gears using ProjectReportVisitor are unaffected.

#### Acceptance Criteria

1. THE Gather_Submission_Status_Gear SHALL NOT modify any files in the nacc-common package
2. THE Gather_Submission_Status_Gear SHALL reuse the existing FileQCReportVisitor, FileQCModel, WriterTableVisitor, and extract_visit_keys functions from nacc-common without modification
3. THE Gather_Submission_Status_Gear SHALL replicate the file-filtering and QC-validation logic currently in ProjectReportVisitor.visit_project within its own main.py, using the same QC_Filename_Pattern and filter conditions
