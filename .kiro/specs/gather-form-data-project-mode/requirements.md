# Requirements Document

## Introduction

Add a project-based execution mode to the gather-form-data gear. Currently the gear requires a CSV participant list as input and gathers form data for each listed NACCID. The new project mode iterates all subjects in a specified Flywheel project and gathers their form data without requiring a pre-built participant list. This enables bulk data export for an entire center project.

## Glossary

- **Gear**: A Flywheel processing unit with defined inputs, config, and outputs
- **GatherFormDataGear**: The gather-form-data gear that collects form data across centers
- **ModuleDataGatherer**: The existing component that collects form file info for a given module (UDS, FTLD, LBD) from acquisitions labeled by module name
- **DataRequestMatch**: A model representing a resolved participant with naccid, subject_id, and project_label
- **Subject**: A Flywheel subject container representing a participant within a project
- **Project**: A Flywheel project container that holds subjects and their data
- **ExecutionMode**: The gear configuration option controlling whether the gear uses a participant list or iterates a project
- **ParticipantListMode**: The execution mode where the gear reads NACCIDs from an input CSV file (current default behavior)
- **ProjectMode**: The execution mode where the gear iterates all subjects in a specified project
- **Module**: A form data category (UDS, FTLD, or LBD) identifying acquisition labels to gather
- **GroupID**: A Flywheel group identifier representing a center
- **ProjectName**: The label of the Flywheel project to iterate in project mode

## Requirements

### Requirement 1: Execution Mode Selection

**User Story:** As a data administrator, I want to select between participant-list mode and project mode, so that I can choose the appropriate data gathering strategy for my use case.

#### Acceptance Criteria

1. THE GatherFormDataGear SHALL provide an `execution_mode` config option of type string with allowed values `participant_list` and `project`.
2. WHEN the `execution_mode` config is not specified, THE GatherFormDataGear SHALL default to `participant_list` mode.
3. WHEN the `execution_mode` is set to `participant_list`, THE GatherFormDataGear SHALL require the `input_file` input and use the `project_names` config for subject matching, consistent with the existing participant-list workflow.
4. IF the `execution_mode` config value is not one of the allowed values, THEN THE GatherFormDataGear SHALL report a configuration error indicating the invalid value and exit without processing.

### Requirement 2: Project Mode Configuration

**User Story:** As a data administrator, I want to specify a center group and project to iterate, so that the gear knows which project's subjects to gather data from.

#### Acceptance Criteria

1. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL require a `group_id` string config parameter identifying the Flywheel group for the center.
2. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL require a `project_name` string config parameter identifying the project label to iterate within the group.
3. IF the `execution_mode` is `project` and `group_id` is not provided or is empty after trimming whitespace, THEN THE GatherFormDataGear SHALL log an error message indicating the missing group_id, set the gear run state to failed, and exit without processing any subjects.
4. IF the `execution_mode` is `project` and `project_name` is not provided or is empty after trimming whitespace, THEN THE GatherFormDataGear SHALL log an error message indicating the missing project_name, set the gear run state to failed, and exit without processing any subjects.

### Requirement 3: Input File Handling in Project Mode

**User Story:** As a data administrator, I want the input CSV file to be optional in project mode, so that I do not need to prepare a participant list when iterating an entire project.

#### Acceptance Criteria

1. THE GatherFormDataGear SHALL declare the `input_file` input as optional in the gear manifest.
2. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL not require the `input_file` input and SHALL ignore it if provided.
3. IF the `execution_mode` is `participant_list` and the `input_file` input is not provided, THEN THE GatherFormDataGear SHALL report a configuration error indicating the missing input file and exit without processing.
4. WHEN the `execution_mode` is `participant_list` and the `input_file` input is provided, THE GatherFormDataGear SHALL require and process the `input_file` input identically to the current implementation.

### Requirement 4: Subject Iteration in Project Mode

**User Story:** As a data administrator, I want the gear to iterate all subjects in the specified project, so that form data is gathered for every participant without a pre-built list.

#### Acceptance Criteria

1. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL resolve the project by looking up the project matching `project_name` within the group identified by `group_id`.
2. WHEN the `execution_mode` is `project` and the project is resolved, THE GatherFormDataGear SHALL iterate all subjects in the resolved project and pass each to the data gathering logic.
3. IF the `execution_mode` is `project` and no group matching `group_id` exists, THEN THE GatherFormDataGear SHALL log an error message indicating the group was not found and exit with a failure status without processing any subjects.
4. IF the `execution_mode` is `project` and no project matching `project_name` exists within the group, THEN THE GatherFormDataGear SHALL log an error message indicating the project was not found and exit with a failure status without processing any subjects.
5. IF the `execution_mode` is `project` and the resolved project contains zero subjects, THEN THE GatherFormDataGear SHALL log a warning indicating the project has no subjects and complete without producing output files.

### Requirement 5: Data Gathering Per Subject

**User Story:** As a data administrator, I want form data gathered for each subject using the existing module logic, so that the output is consistent regardless of execution mode.

#### Acceptance Criteria

1. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL use ModuleDataGatherer to collect form data for each subject in the project, processing all subjects regardless of individual subject failures.
2. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL construct a DataRequestMatch for each subject using the subject label as naccid, the subject id as subject_id, and the project label as project_label.
3. WHEN the `execution_mode` is `project`, THE GatherFormDataGear SHALL apply each configured ModuleDataGatherer to each subject via the `gather_request_data` method.
4. IF a ModuleDataGatherer raises an error during `gather_request_data` for a subject, THEN THE GatherFormDataGear SHALL log a warning identifying the subject and module, skip that module for that subject, and continue processing remaining subjects.

### Requirement 6: Module and Derived Data Configuration

**User Story:** As a data administrator, I want the existing modules and include_derived config options to work in project mode, so that I control which data is gathered the same way in both modes.

#### Acceptance Criteria

1. WHILE the `execution_mode` is `project`, THE GatherFormDataGear SHALL create a ModuleDataGatherer for each valid module name in the `modules` config (comma-separated list with allowed values UDS, FTLD, LBD) and gather data only for those modules.
2. WHILE the `execution_mode` is `project`, THE GatherFormDataGear SHALL include acquisition paths labeled "derived" in addition to "forms.json" when `include_derived` is true, and search only "forms.json" acquisition paths when `include_derived` is false.
3. WHILE the `execution_mode` is `project`, THE GatherFormDataGear SHALL use the `study_id` config value as the `{study_id}` component in output file naming.
4. IF the `execution_mode` is `project` and the `modules` config contains values not in the allowed set (UDS, FTLD, LBD), THEN THE GatherFormDataGear SHALL log a warning identifying the unexpected module names and exclude them from gathering.
5. IF the `execution_mode` is `project` and the `modules` config is empty or contains no valid module names after filtering, THEN THE GatherFormDataGear SHALL report a configuration error and exit without processing.

### Requirement 7: Output Format

**User Story:** As a data administrator, I want the output format to remain unchanged in project mode, so that downstream consumers of the CSV files are not affected.

#### Acceptance Criteria

1. WHEN the `execution_mode` is `project` and data gathering completes successfully, THE GatherFormDataGear SHALL write one CSV output file per module as a gear output file, using the naming pattern `{study_id}-{module_name}-{date}.csv` where `{date}` is the current date in ISO 8601 format (`YYYY-MM-DD`).
2. WHEN the `execution_mode` is `project` and a module's gatherer has accumulated no content, THE GatherFormDataGear SHALL skip writing an output file for that module and log a warning identifying the module.
3. WHEN the `execution_mode` is `project` and a CSV output file is written, THE GatherFormDataGear SHALL encode the file as UTF-8.

### Requirement 8: Warning Logging for Empty Subjects

**User Story:** As a data administrator, I want to see warnings for subjects that have no acquisitions for a requested module, so that I can identify gaps in the data.

#### Acceptance Criteria

1. WHEN the `execution_mode` is `project` and a subject has no acquisitions matching a requested module, THE GatherFormDataGear SHALL log a warning that includes the subject label (NACCID) and the module name that returned no data.
2. WHEN the `execution_mode` is `project` and a subject has no acquisitions matching a requested module, THE GatherFormDataGear SHALL continue processing the remaining modules for that subject and subsequent subjects without interruption.
3. WHEN the `execution_mode` is `project` and multiple subjects have no acquisitions for a requested module, THE GatherFormDataGear SHALL log a separate warning for each subject-module combination that has no data.

### Requirement 9: Backward Compatibility

**User Story:** As a data administrator using the existing participant-list workflow, I want no breaking changes to the current behavior, so that my existing automation continues to work.

#### Acceptance Criteria

1. WHEN the `execution_mode` config is not specified, THE GatherFormDataGear SHALL default to `participant_list` mode and execute the participant-list workflow without requiring any new config parameters.
2. WHEN the `execution_mode` is `participant_list`, THE GatherFormDataGear SHALL require the `input_file` input, read NACCIDs from the CSV, resolve subjects across the Flywheel instance, filter to subjects matching the `project_names` config, and gather form data using the configured modules.
3. WHEN the `execution_mode` is `participant_list` and data gathering completes, THE GatherFormDataGear SHALL write output CSV files using the same naming pattern and content structure as the current implementation, and SHALL write QC validation metadata and file tags to the input file.
4. IF the `execution_mode` is `participant_list` and the `input_file` input is not provided, THEN THE GatherFormDataGear SHALL report an error and exit without processing.

### Requirement 10: Architecture Constraints

**User Story:** As a developer, I want the project mode implementation to follow the existing gear architecture, so that the codebase remains consistent and testable.

#### Acceptance Criteria

1. THE GatherFormDataGear SHALL implement project resolution, subject iteration, and file output writing for project mode in run.py.
2. THE GatherFormDataGear SHALL reuse ModuleDataGatherer for per-subject data gathering in project mode without duplicating gathering logic.
3. THE GatherFormDataGear SHALL keep per-subject data gathering orchestration in main.py testable by passing domain models or plain data types rather than Flywheel SDK objects across the run.py/main.py boundary.
4. THE GatherFormDataGear main.py SHALL NOT import the Flywheel SDK or GearContext directly.
