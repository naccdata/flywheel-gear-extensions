# Requirements Document

## Introduction

This feature extracts the "project mode" execution path from the `gather_form_data` gear into a new standalone gear called `center_form_export`. The original gear had two independent execution paths (participant-list mode and project mode) selected by a config flag. Separating them into distinct gears reduces complexity, clarifies each gear's responsibility, and simplifies maintenance.

The new `center_form_export` gear iterates all subjects in a Flywheel group/project and exports form data per module. The `gather_form_data` gear reverts to its original single-mode behavior (participant-list only).

## Glossary

- **Center_Form_Export_Gear**: The new Flywheel gear (`gear/center_form_export/`) that performs project-mode form data gathering and export
- **Gather_Form_Data_Gear**: The existing Flywheel gear (`gear/gather_form_data/`) that gathers form data from a participant list CSV
- **Gear_Manifest**: The `manifest.json` file defining a gear's metadata, inputs, and config fields
- **Project_Mode**: The execution path that resolves a Flywheel group/project, iterates its subjects, and queries each module's files in batches of subject ids (not one query per subject, and not one unscoped query for the whole project)
- **Participant_List_Mode**: The execution path that reads a CSV of NACCIDs and gathers form data for each listed participant
- **Module_Data_Gatherer**: A shared library class in `common/` that collects file.info form data for a given module, via either a per-subject query (`gather_request_data`, used by Participant_List_Mode) or a batched-subject-id query (`gather_project_data`, used by Project_Mode)
- **Data_Request_Match**: A shared library model representing a matched participant with subject_id and project_label; used by Participant_List_Mode only, not by Project_Mode
- **Formver_Split**: An option to split output CSVs by form version, producing one file per (module, formver) pair
- **BUILD_File**: A Pants build system configuration file defining targets for a directory
- **Gear_Directory_Structure**: The standard layout for gears: `src/docker/` (Dockerfile, manifest.json, BUILD), `src/python/app_name/` (Python source), `test/python/` (tests)

## Requirements

### Requirement 1: New Gear Directory Structure

**User Story:** As a developer, I want `center_form_export` to follow the standard gear directory layout, so that it is consistent with existing gears in the monorepo.

#### Acceptance Criteria

1. THE Center_Form_Export_Gear SHALL have a directory structure at `gear/center_form_export/` containing `src/docker/` with a Dockerfile, manifest.json, and BUILD file
2. THE Center_Form_Export_Gear SHALL have a Python source directory at `src/python/center_form_export_app/` containing a BUILD file, `run.py`, and `main.py`
3. THE Center_Form_Export_Gear SHALL have a test directory at `test/python/` containing a BUILD file and at least one test file following the `test_*.py` naming convention
4. THE Center_Form_Export_Gear SHALL have a Dockerfile that sets base image to python:3.12, creates the `/flywheel/v0` working directory, copies the manifest.json to the working directory, copies the PEX binary to `/bin/run`, and sets the entrypoint to `["/bin/run"]`

### Requirement 2: Gear Manifest Definition

**User Story:** As a platform operator, I want the `center_form_export` manifest to declare its own config inputs, so that the gear can be configured independently on Flywheel.

#### Acceptance Criteria

1. THE Gear_Manifest SHALL define a required config field `group_id` of type string with no default value that specifies the Flywheel group ID for the center
2. THE Gear_Manifest SHALL define a required config field `project_name` of type string with no default value that specifies the project label to iterate
3. THE Gear_Manifest SHALL define a config field `modules` of type string with default `"UDS,FTLD,LBD"` that specifies a comma-separated list of module names where each name contains only alphanumeric characters
4. THE Gear_Manifest SHALL define a config field `study_id` of type string with default `"adrc"` that specifies the study identifier
5. THE Gear_Manifest SHALL define a config field `include_derived` of type boolean with default `false` that controls whether derived variables are included
6. THE Gear_Manifest SHALL define a config field `formver_split` of type boolean with default `false` that controls whether output is split by form version
7. THE Gear_Manifest SHALL define an `api-key` input with base `"api-key"` and no other input entries
8. THE Gear_Manifest SHALL NOT define an `input_file` input or an `execution_mode` config field
9. IF `group_id` or `project_name` is empty or blank at gear launch, THEN THE Center_Form_Export_Gear SHALL raise a configuration error before beginning execution

### Requirement 3: Project-Mode Execution Logic

**User Story:** As a data manager, I want the new gear to export form data per module for an entire Flywheel group/project without the number of queries scaling one-to-one with the number of subjects, so that I can extract center-level form data without a participant list and without excessive runtime for large centers.

#### Acceptance Criteria

1. WHEN the Center_Form_Export_Gear is executed, THE Center_Form_Export_Gear SHALL resolve the Flywheel group specified by `group_id` and find the project specified by `project_name` within that group
2. WHEN the group and project are resolved, THE Center_Form_Export_Gear SHALL iterate all subjects in the project and collect their subject ids
3. WHEN subject ids are collected, THE Center_Form_Export_Gear SHALL parse the `modules` config field as a comma-separated list, create a Module_Data_Gatherer for each module name in that list, and call `gather_project_data` on each gatherer with the full list of subject ids
4. WHEN `gather_project_data` is called, THE Module_Data_Gatherer SHALL partition the subject ids into batches (default 100, overridable via `batch_size` param/config field) and issue one Flywheel query per batch using an OR-list filter on subject id (`parents.subject=|[id1,id2,...]`) combined with the module's acquisition label — NOT one query per subject, and NOT a single unscoped query for the whole project
5. WHEN a batch's file list is returned, THE Module_Data_Gatherer SHALL reload each file's `info` concurrently using a single, bounded worker pool shared across all batches in the call (default 10 workers, overridable via `reload_workers` param/config field), rather than reloading files one at a time or constructing a new pool per batch. The merge/write step for each reloaded file SHALL remain single-threaded, since the CSV writer is not thread-safe
6. IF the specified group is not found, THEN THE Center_Form_Export_Gear SHALL raise a gear execution error identifying the missing group
7. IF the specified project is not found within the group, THEN THE Center_Form_Export_Gear SHALL raise a gear execution error identifying the missing project and group
8. IF the project contains no subjects, THEN THE Center_Form_Export_Gear SHALL log a warning identifying the group and project, and complete without producing output files
9. IF a module's batched queries return no files, THEN THE Center_Form_Export_Gear SHALL skip output for that module and log a warning identifying the module name (see Requirement 5.3)
10. IF the `modules` config field is empty or contains no valid module names after parsing, THEN THE Center_Form_Export_Gear SHALL log a warning and complete without producing output files
11. WHEN a module finishes gathering, THE Center_Form_Export_Gear SHALL write that module's output file(s) immediately, before gathering the next module

**Notes:** An unscoped project-wide query (no subject narrowing) was tried first and found to reliably time out on Flywheel's backend for large centers — hence the batching in 3.4. The `batch_size=100` and `reload_workers=10` defaults aren't guesses: concurrency was benchmarked at ~6.7x reload throughput before implementing, and `batch_size` was validated via a sweep (25/100/200) against both a small center and a large one (`retrospective-form`, ~25k files — a large legacy-import center used for testing) — 25 was slower everywhere; 200 was faster on the small center but a wash on the large one (reload volume dominates there, not query count) and, critically, didn't reproduce the timeout, confirming 100 has real margin. See `design.md` for the full history.

### Requirement 4: Resilient File Processing

**User Story:** As a data manager, I want the gear to continue processing remaining files when one file fails, so that a single data issue does not block the entire export.

#### Acceptance Criteria

1. WHEN a Module_Data_Gatherer raises a ModuleDataError while processing a file returned by one of its batched queries, THE Center_Form_Export_Gear SHALL log a warning containing the error message
2. WHEN a Module_Data_Gatherer raises a ModuleDataError for a file, THE Center_Form_Export_Gear SHALL continue processing the remaining files in that batch, the remaining batches for that module, and the remaining modules without interruption
3. WHEN processing of all modules is complete, THE Center_Form_Export_Gear SHALL report successful completion regardless of how many individual ModuleDataError failures occurred
4. IF a Module_Data_Gatherer raises an unexpected error that is not a ModuleDataError, THEN THE Center_Form_Export_Gear SHALL propagate the error and halt processing
5. THE Center_Form_Export_Gear SHALL log progress at least once per module (before starting) and once per subject batch processed, so that a running job's progress can be distinguished from a stalled one
6. Concurrent `.reload()` calls within a batch share one Flywheel client/HTTP session across worker threads; this is a known, accepted assumption (not a verified guarantee) about thread-safety

**Notes:** Because output is written per-module as soon as each module finishes (Requirement 3.11), a 4.4 failure while gathering module N no longer discards modules 1..N-1's already-written output — but N and any modules after it produce no output for that run. On 4.6: shared-client thread safety has been observed correct across all testing to date, including a full run against a large real center (`retrospective-form`), but isn't confirmed safe by the Flywheel SDK's own documentation.

### Requirement 5: Output File Production

**User Story:** As a data consumer, I want the gear to produce CSV output files named consistently, so that downstream processes can locate and consume them.

#### Acceptance Criteria

1. WHEN `formver_split` is `false`, THE Center_Form_Export_Gear SHALL produce one output CSV per module named `{study_id}-{module_name}-{date}.csv` where `{date}` is the current date in ISO 8601 format (YYYY-MM-DD)
2. WHEN `formver_split` is `true`, THE Center_Form_Export_Gear SHALL produce one output CSV per (module, formver) pair named `{study_id}-{module_name}-{formver_label}-{date}.csv` where `{date}` is the current date in ISO 8601 format (YYYY-MM-DD) and `{formver_label}` is the normalized form version label
3. WHEN a module gatherer has no data after processing, THE Center_Form_Export_Gear SHALL skip output for that module and log a warning identifying the module name
4. IF `formver_split` is `true` and a formver bucket has empty content, THEN THE Center_Form_Export_Gear SHALL skip output for that bucket without logging an error
5. THE Center_Form_Export_Gear SHALL write each output CSV encoded as UTF-8

### Requirement 6: Shared Library Dependency

**User Story:** As a developer, I want both gears to depend on the shared `data_requests` library in `common/`, so that the Module_Data_Gatherer, Data_Request_Match, and formver-split logic are maintained in one place.

#### Acceptance Criteria

1. THE Center_Form_Export_Gear SHALL import ModuleDataGatherer, DataRequestMatch, ModuleDataError, and formver_label from the `data_requests.data_request` module in `common/src/python/`
2. THE Gather_Form_Data_Gear SHALL continue to import from the same `data_requests.data_request` module, and the public API of that module (class names, method signatures, and function signatures) SHALL remain unchanged
3. WHEN `pants check gear/center_form_export/::` is run, THE build system SHALL resolve the `data_requests.data_request` import from the `common/src/python/data_requests` source root without requiring an explicit `dependencies` declaration in the python_sources target
4. THE `common/src/python/data_requests/data_request.py` source file SHALL NOT be duplicated into the Center_Form_Export_Gear directory

### Requirement 7: Revert gather_form_data to Single-Mode

**User Story:** As a developer, I want `gather_form_data` reverted to participant-list-only behavior, so that it has a single clear responsibility and reduced complexity.

#### Acceptance Criteria

1. THE Gather_Form_Data_Gear SHALL NOT contain the `execution_mode` config field in the Gear_Manifest
2. THE Gather_Form_Data_Gear SHALL NOT contain the `group_id` config field in the Gear_Manifest
3. THE Gather_Form_Data_Gear SHALL NOT contain the `project_name` config field in the Gear_Manifest
4. THE Gather_Form_Data_Gear SHALL NOT contain the ProjectModeVisitor class in its source code
5. THE Gather_Form_Data_Gear SHALL NOT contain the ProjectModeConfig class in its source code
6. THE Gather_Form_Data_Gear SHALL NOT contain the `run_project_mode` function in its source code
7. THE Gather_Form_Data_Gear SHALL NOT contain execution mode dispatch logic in the `main()` function
8. THE Gather_Form_Data_Gear `main()` function SHALL create a GearEngine and call `engine.run(gear_type=GatherFormDataVisitor)` without reading `execution_mode` from config and without conditional branching on execution mode
9. THE Gather_Form_Data_Gear SHALL retain the `formver_split` config field for use in participant-list mode
10. THE Gather_Form_Data_Gear SHALL NOT import ProjectModeVisitor, ProjectModeConfig, or `run_project_mode` in any source file

### Requirement 8: Test Migration

**User Story:** As a developer, I want the project-mode tests to live in the new gear's test directory, so that tests are co-located with the code they exercise.

#### Acceptance Criteria

1. THE Center_Form_Export_Gear SHALL have a test file in `test/python/` covering project-mode integration behavior including group resolution failure, project resolution failure, empty project handling, output file production, and output filename format
2. THE Center_Form_Export_Gear SHALL have a test file in `test/python/` covering resilient subject processing including continued execution after ModuleDataError, and verification that all subject-gatherer combinations are attempted
3. THE Gather_Form_Data_Gear SHALL NOT contain `test_project_mode_integration.py` in its test directory
4. THE Gather_Form_Data_Gear SHALL NOT contain `test_run_project_mode.py` in its test directory
5. THE Gather_Form_Data_Gear SHALL NOT contain `test_backward_compatibility.py` in its test directory since the mode dispatch it validated no longer exists
6. WHEN `pants test gear/center_form_export/test/python::` is run, THE Center_Form_Export_Gear tests SHALL pass without failures

### Requirement 9: Documentation Update

**User Story:** As a user, I want accurate documentation for both gears, so that I know which gear to use and how to configure it.

#### Acceptance Criteria

1. THE documentation at `docs/gather_form_data/index.md` SHALL NOT reference project mode, `execution_mode`, `group_id`, or `project_name` config fields
2. THE documentation at `docs/gather_form_data/index.md` SHALL describe participant-list mode as the sole execution behavior, including the required `input_file` CSV input and all remaining config fields with their types and defaults
3. WHEN the Center_Form_Export_Gear is created, THE documentation at `docs/center_form_export/index.md` SHALL describe the gear's purpose, list all config fields defined in the Gear_Manifest with their types and default values, and describe the output filename patterns for both `formver_split` modes
4. THE documentation at `docs/center_form_export/index.md` SHALL document the `formver_split` option including the filename pattern `{study_id}-{module_name}-{date}.csv` when disabled and `{study_id}-{module_name}-{formver_label}-{date}.csv` when enabled
5. THE documentation at `docs/center_form_export/index.md` SHALL state that the gear is intended for center-level export of all subjects in a project without a participant list, distinguishing it from the Gather_Form_Data_Gear which requires a participant list CSV as input

### Requirement 10: Build System Integration

**User Story:** As a developer, I want the new gear to build and test correctly with Pants, so that CI and local development workflows work without additional setup.

#### Acceptance Criteria

1. THE Center_Form_Export_Gear SHALL have a `src/python/center_form_export_app/BUILD` file defining a `python_sources` target and a `pex_binary` target with entry point `run.py`
2. THE Center_Form_Export_Gear SHALL have a `src/docker/BUILD` file defining a `file` target for `manifest.json` and a `docker_image` target that depends on the manifest file target and the `pex_binary` target from the Python source BUILD file
3. THE Center_Form_Export_Gear SHALL have a `test/python/BUILD` file defining a `python_tests` target
4. WHEN `pants test gear/center_form_export/test/python::` is run, THE Center_Form_Export_Gear tests SHALL pass with exit code 0
5. WHEN `pants check gear/center_form_export/::` is run, THE Center_Form_Export_Gear source SHALL pass type checking with exit code 0
6. WHEN `pants lint gear/center_form_export/::` is run, THE Center_Form_Export_Gear source and tests SHALL pass linting with exit code 0
7. WHEN `pants package gear/center_form_export/src/python/center_form_export_app:bin` is run, THE Center_Form_Export_Gear SHALL produce a PEX binary without errors
