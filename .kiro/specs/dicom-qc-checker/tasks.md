# Implementation Plan: dicom-qc-checker

## Overview

Implement the dicom-qc-checker Flywheel gear following the project's standard gear structure. The gear reads DICOM QC metadata from a file, determines aggregate pass/fail status via a pure function, logs failures, and tags the file accordingly. Implementation follows the `GearExecutionEnvironment` pattern established by existing gears.

## Tasks

- [x] 1. Set up gear scaffold and configuration
  - [x] 1.1 Create manifest.json for the dicom-qc-checker gear
    - Create `gear/dicom_qc_checker/src/docker/manifest.json` with gear name `"dicom-qc-checker"`, label, description, version `"0.0.1"`, single file input (`"input_file"` with base `"file"`), `api-key` input, and `custom.gear-builder.image` set to `"naccdata/dicom-qc-checker:0.0.1"`
    - _Requirements: 5.1, 5.2, 5.5_

  - [x] 1.2 Create Dockerfile and docker BUILD file
    - Create `gear/dicom_qc_checker/src/docker/Dockerfile` following the phi_image_removal pattern (FROM python:3.12, copy manifest.json, copy pex binary, ENTRYPOINT)
    - Create `gear/dicom_qc_checker/src/docker/BUILD` with `file(name="manifest", source="manifest.json")` and `docker_image(name="dicom-qc-checker", ...)` targeting `gear/dicom_qc_checker/src/python/dicom_qc_checker_app:bin`
    - _Requirements: 5.4, 5.5_

  - [x] 1.3 Create Python package structure with __init__.py and BUILD files
    - Create `gear/dicom_qc_checker/src/python/dicom_qc_checker_app/__init__.py` (empty)
    - Create `gear/dicom_qc_checker/src/python/dicom_qc_checker_app/BUILD` with `python_sources(name="dicom_qc_checker_app")` and `pex_binary(name="bin", entry_point="run.py")`
    - Create `gear/dicom_qc_checker/test/python/dicom_qc_checker_app_test/__init__.py` (empty)
    - Create `gear/dicom_qc_checker/test/python/dicom_qc_checker_app_test/BUILD` with `python_tests(name="tests")`
    - _Requirements: 5.3, 5.4_

- [x] 2. Implement core business logic
  - [x] 2.1 Implement `determine_qc_status` in main.py
    - Create `gear/dicom_qc_checker/src/python/dicom_qc_checker_app/main.py`
    - Implement `determine_qc_status(dicom_qc: dict[str, Any]) -> tuple[str, list[str]]` as a pure function
    - Filter out `job_info` key; identify check results (dict entries with a `state` field)
    - Return `("FAIL", [...])` if any check has state != "PASS" or if no check results remain
    - Return `("PASS", [])` only if all check results have state == "PASS"
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Implement `run` function in main.py
    - Add `run(*, file: FileEntry, proxy: FlywheelProxy) -> None` to main.py
    - Extract `file.info.get("qc", {}).get("dicom-qc", {})` from the file entry
    - Handle absent/empty metadata: log warning, return early
    - Handle only-job_info case: log warning, return early
    - Call `determine_qc_status()` for the status decision
    - Log each failed/invalid check name at WARNING level
    - Use `GearTags("dicom-qc-checker").update_tags()` to compute new tags
    - Persist tags via `proxy.update_file_tags(file_id, updated_tags)`
    - Raise `GearExecutionError` if tag persistence fails
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 2.3 Write property tests for `determine_qc_status`
    - Create `gear/dicom_qc_checker/test/python/dicom_qc_checker_app_test/test_determine_status.py`
    - **Property 1: Status determination correctness** — For any metadata dict with at least one check result, status is PASS iff every check result has state "PASS"
    - **Validates: Requirements 2.3, 2.4, 2.6**
    - **Property 2: Job_info and non-check entry exclusion** — Modifying `job_info` or non-check entries does not change the status result
    - **Validates: Requirements 2.1, 2.2**
    - **Property 3: Failure reporting completeness** — When status is FAIL, problem_checks includes every check key whose state != "PASS"
    - **Validates: Requirements 3.1, 3.2**
    - Use Hypothesis with custom strategies generating DICOM QC metadata dicts (0–10 check entries, job_info, optional non-check entries)

  - [x] 2.4 Write unit tests for `main.run`
    - Create `gear/dicom_qc_checker/test/python/dicom_qc_checker_app_test/test_main.py`
    - Test no-metadata case: `file.info` has no `qc` key → returns None, warning logged
    - Test empty dicom-qc case: `file.info.qc.dicom-qc` is `{}` → returns None, warning logged
    - Test only-job_info case: metadata has only `{"job_info": {...}}` with no check results → returns None, warning logged
    - Test single PASS: one check with state "PASS" → returns "PASS"
    - Test single FAIL: one check with state "FAIL" → returns "FAIL", check name logged at WARNING
    - Test mixed results: multiple checks, some PASS some FAIL → returns "FAIL", all failed check names logged
    - Mock `FileEntry` with appropriate `info` dict; no proxy or API mocking needed since `main.run` is side-effect-free
    - _Requirements: 1.2, 1.3, 2.3, 2.4, 3.1, 3.2_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement gear entry point
  - [x] 4.1 Implement `DicomQCCheckerVisitor` in run.py
    - Create `gear/dicom_qc_checker/src/python/dicom_qc_checker_app/run.py`
    - Implement `DicomQCCheckerVisitor(GearExecutionEnvironment)` with `__init__`, `create`, and `run` methods following the PHIImageRemovalVisitor pattern
    - `create()`: build `ClientWrapper` from context, create `InputFileWrapper` for `"input_file"`, raise `GearExecutionError` if input missing
    - `run()`: retrieve `FileEntry` via `self.proxy.get_file()`, delegate to `main.run(file=file, proxy=self.proxy)`
    - Implement `main()` entry point calling `GearEngine().run(gear_type=DicomQCCheckerVisitor)`
    - _Requirements: 1.1, 5.1, 5.2, 5.3_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- Use `pants_tailor` when new .py files are created to generate BUILD files
- Full quality check at wave boundaries (parent task completion)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.3", "2.4"] }
  ]
}
```
