# Implementation Plan: center-form-export

## Overview

Extract the "project mode" execution path from `gather_form_data` into a new standalone gear called `center_form_export`. The new gear is scaffolded via the cookiecutter template, reuses the shared `data_requests` library, and follows the existing gear architecture. The original `gather_form_data` gear is then surgically reverted to participant-list-only behavior.

## Tasks

- [x] 1. Scaffold new gear and define manifest
  - [x] 1.1 Generate gear directory structure using cookiecutter template
    - Install cookiecutter via `pipx install cookiecutter` (per developer docs)
    - Run `pipx run cookiecutter templates/gear/ --output-dir gear/` with `gear_name="Center Form Export"` 
    - This produces `gear/center_form_export/` with `src/docker/`, `src/python/center_form_export_app/`, and `test/python/center_form_export_test/`
    - Verify the generated directory structure matches the standard gear layout
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Create the gear manifest (`manifest.json`)
    - Define config fields: `group_id` (required string, no default), `project_name` (required string, no default), `modules` (string, default `"UDS,FTLD,LBD"`), `study_id` (string, default `"adrc"`), `include_derived` (boolean, default `false`), `formver_split` (boolean, default `false`)
    - Define input: `api-key` with base `"api-key"` — no `input_file` input
    - Do NOT include `execution_mode` config field
    - Set gear name to `"center-form-export"`, label to `"Center Form Export"`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 1.3 Create the Dockerfile
    - Base image `python:3.12`, working directory `/flywheel/v0`
    - Copy `manifest.json` to working directory
    - Copy PEX binary to `/bin/run`
    - Set entrypoint to `["/bin/run"]`
    - _Requirements: 1.4_

  - [x] 1.4 Create BUILD files for the new gear
    - `src/python/center_form_export_app/BUILD`: `python_sources` target and `pex_binary` target with entry point `run.py`
    - `src/docker/BUILD`: `file` target for `manifest.json` and `docker_image` target depending on manifest and pex_binary
    - `test/python/center_form_export_test/BUILD`: `python_tests` target
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 2. Implement core business logic
  - [x] 2.1 Implement `main.py` with `ProjectModeConfig` and `run_project_mode`
    - Move `ProjectModeConfig` Pydantic model (field validators for blank `group_id`/`project_name`, valid modules)
    - Move `run_project_mode` function (iterates requests × gatherers, catches `ModuleDataError`, logs warning, returns `True`)
    - Import `DataRequestMatch`, `ModuleDataGatherer`, `ModuleDataError` from `data_requests.data_request`
    - _Requirements: 2.9, 3.3, 4.1, 4.2, 4.3, 4.4, 6.1_

  - [x] 2.2 Implement `run.py` with `CenterFormExportVisitor`
    - Create `CenterFormExportVisitor(GearExecutionEnvironment)` with `create()` and `run()` methods
    - `create()`: extract config from `GearContext`, validate via `ProjectModeConfig`, wrap `ValidationError` in `GearExecutionError`
    - `run()`: resolve group/project via `FlywheelProxy`, build `DataRequestMatch` list from subjects, create `ModuleDataGatherer` instances, call `run_project_mode`, call `_write_module_output`
    - Implement `_write_module_output` helper (duplicated from gather_form_data, handles both single-file and formver-split modes)
    - Implement `main()` function: `GearEngine().create_with_parameter_store().run(gear_type=CenterFormExportVisitor)`
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1_

  - [x] 2.3 Write property test: blank config fields rejected
    - **Property 1: Blank config fields are rejected**
    - Generate whitespace-only strings (empty, spaces, tabs, newlines), verify `ValidationError` raised for `group_id` and `project_name`
    - **Validates: Requirements 2.9**

  - [ ]* 2.4 Write property test: subject-to-DataRequestMatch mapping preserves identity
    - **Property 2: Subject-to-DataRequestMatch mapping preserves identity**
    - Generate (label, id, project_label) tuples, verify resulting `DataRequestMatch` list has same length and matching fields
    - **Validates: Requirements 3.2**

  - [ ]* 2.5 Write property test: resilient subject processing
    - **Property 3: All request-gatherer combinations are attempted with resilience**
    - Generate request lists + failure masks, verify all (request, gatherer) pairs attempted, `True` returned, `ModuleDataError` not propagated
    - **Validates: Requirements 3.3, 4.1, 4.2, 4.3**

  - [x] 2.6 Write property test: output filename conforms to naming pattern
    - **Property 4: Output filename conforms to naming pattern**
    - Generate `study_id`, `module_name`, date combos; verify regex match for both default and formver-split patterns
    - **Validates: Requirements 5.1, 5.2**

- [x] 3. Migrate tests to new gear
  - [x] 3.1 Migrate `test_project_mode_integration.py` to new gear
    - Copy from `gear/gather_form_data/test/python/test_project_mode_integration.py` to `gear/center_form_export/test/python/center_form_export_test/test_project_mode_integration.py`
    - Update imports: change `gather_form_data_app.run.ProjectModeVisitor` to `center_form_export_app.run.CenterFormExportVisitor`
    - Update all references from `ProjectModeVisitor` to `CenterFormExportVisitor`
    - Update patch targets from `gather_form_data_app.run.ModuleDataGatherer` to `center_form_export_app.run.ModuleDataGatherer` and similarly for `date`
    - _Requirements: 8.1, 8.3_

  - [x] 3.2 Migrate `test_run_project_mode.py` to new gear
    - Copy from `gear/gather_form_data/test/python/test_run_project_mode.py` to `gear/center_form_export/test/python/center_form_export_test/test_run_project_mode.py`
    - Update imports: change `gather_form_data_app.main` to `center_form_export_app.main`
    - Update patch targets from `gather_form_data_app.main.log` to `center_form_export_app.main.log`
    - _Requirements: 8.2, 8.4_

  - [x] 3.3 Create `conftest.py` and `__init__.py` for the new gear's test directory
    - Create `gear/center_form_export/test/python/center_form_export_test/__init__.py`
    - Create `gear/center_form_export/test/python/center_form_export_test/conftest.py` with shared fixtures (mock `ClientWrapper`, `FlywheelProxy`, `GearContext`)
    - _Requirements: 8.1, 8.2_

- [x] 4. Checkpoint - Verify new gear builds and tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Revert gather_form_data to single-mode
  - [ ] 5.1 Remove project-mode code from `gather_form_data/main.py`
    - Remove `ProjectModeConfig` class, `run_project_mode` function
    - Remove `pydantic` import, `DataRequestMatch`/`ModuleDataError`/`ModuleDataGatherer` imports (keep only `DataRequestVisitor`)
    - Retain `run()` function unchanged
    - _Requirements: 7.5, 7.6, 7.10_

  - [ ] 5.2 Remove project-mode code from `gather_form_data/run.py`
    - Remove `ProjectModeVisitor` class entirely
    - Remove mode dispatch logic from `main()` — simplify to: `engine = GearEngine().create_with_parameter_store(); engine.run(gear_type=GatherFormDataVisitor)`
    - Remove `sys` import, `ProjectModeConfig`/`run_project_mode` imports from `main`
    - Retain `_write_module_output`, `GatherFormDataVisitor`, and all their imports
    - _Requirements: 7.4, 7.7, 7.8, 7.10_

  - [ ] 5.3 Remove project-mode config fields from `gather_form_data/manifest.json`
    - Remove `execution_mode`, `group_id`, `project_name` config fields
    - Retain `formver_split`, `modules`, `study_id`, `include_derived`, `project_names`, `dry_run`, `apikey_path_prefix`
    - _Requirements: 7.1, 7.2, 7.3, 7.9_

  - [x] 5.4 Delete obsolete test files from gather_form_data
    - Delete `gear/gather_form_data/test/python/test_project_mode_integration.py`
    - Delete `gear/gather_form_data/test/python/test_run_project_mode.py`
    - Delete `gear/gather_form_data/test/python/test_backward_compatibility.py`
    - _Requirements: 8.3, 8.4, 8.5_

- [ ] 6. Checkpoint - Verify gather_form_data still builds and passes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Documentation
  - [ ] 7.1 Update `docs/gather_form_data/index.md`
    - Remove all references to project mode, `execution_mode`, `group_id`, `project_name`
    - Describe participant-list mode as the sole execution behavior
    - Document required `input_file` CSV input and all remaining config fields with types and defaults
    - _Requirements: 9.1, 9.2_

  - [ ] 7.2 Create `docs/center_form_export/index.md`
    - Describe gear purpose: center-level export of all subjects in a project without a participant list
    - List all config fields with types and default values
    - Document output filename patterns for both `formver_split` modes
    - Distinguish from `gather_form_data` which requires a participant list CSV
    - _Requirements: 9.3, 9.4, 9.5_

- [ ] 8. Final checkpoint - Full quality check
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based test sub-tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at wave boundaries
- Property tests validate universal correctness properties from the design document
- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- The `full_quality_check` should be run at wave boundaries (after checkpoints 4, 6, and 8)
- The cookiecutter template generates the test directory as `center_form_export_test/` (with `_test` suffix) to avoid namespace conflicts per project conventions
- The `kiro-pants-power` is available for running all Pants commands

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["7.1", "7.2"] }
  ]
}
```
