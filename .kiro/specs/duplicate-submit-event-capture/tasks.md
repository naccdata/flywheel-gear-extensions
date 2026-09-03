# Implementation Plan: Duplicate Submit Event Capture

## Overview

This plan implements the `"duplicate-submit"` event type in the NACC transaction log system and integrates it into the form-transformer gear. The implementation proceeds bottom-up: event model extension, manifest config, gear wiring (run.py and main.py), then tests.

## Tasks

- [x] 1. Extend VisitEventType with duplicate-submit action
  - [x] 1.1 Add "duplicate-submit" to VisitEventType literal and ACTION_DUPLICATE_SUBMIT constant
    - Modify `common/src/python/event_capture/visit_events.py`
    - Add `"duplicate-submit"` to the `VisitEventType` Literal type
    - Add `ACTION_DUPLICATE_SUBMIT: VisitEventType = "duplicate-submit"` constant below existing action constants
    - No changes needed to VisitEvent model, serializer, or validator (they are action-agnostic)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Add event capture configuration to form-transformer manifest
  - [x] 2.1 Add event_bucket and event_environment config options to manifest.json
    - Modify `gear/form_transformer/src/docker/manifest.json`
    - Add `event_bucket` config: type string, optional, description for S3 transaction log bucket
    - Add `event_environment` config: type string, optional, enum `["prod", "dev"]`, description for environment prefix
    - Both fields must be optional with no default value
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 3. Integrate VisitEventCapture into form-transformer
  - [x] 3.1 Add event_capture, center_label, project_label, timestamp parameters to run() and CSVTransformVisitor
    - Modify `gear/form_transformer/src/python/form_csv_app/main.py`
    - Add `event_capture: Optional[VisitEventCapture] = None` parameter to `run()` function
    - Add `center_label: str = ""` parameter to `run()` function
    - Add `project_label: str = ""` parameter to `run()` function
    - Add `timestamp: Optional[datetime] = None` parameter to `run()` function
    - Add same parameters to `CSVTransformVisitor.__init__()` and store as instance attributes
    - Pass parameters through from `run()` to the `CSVTransformVisitor` constructor
    - Add required imports: `from datetime import datetime`, `from event_capture.event_capture import VisitEventCapture`, `from event_capture.visit_events import ACTION_DUPLICATE_SUBMIT, VisitEvent`
    - _Requirements: 3.5, 2.1_

  - [x] 3.2 Implement __capture_duplicate_event() method in CSVTransformVisitor
    - Add private method `__capture_duplicate_event(self, transformed_row: Dict[str, Any]) -> None`
    - Return early if `self.__event_capture` or `self.__timestamp` is None
    - Try constructing `DataIdentification.from_form_record(transformed_row, self.__date_field)`
    - On `EmptyFieldError`, `InvalidDateError`, or `ValidationError`: log warning with ptid/date and return (skip event)
    - Create `VisitEvent` with action=ACTION_DUPLICATE_SUBMIT, datatype="form", and the stored project_label, center_label, gear_name, timestamp
    - Call `self.__event_capture.capture_event(event)` wrapped in try/except that catches any Exception, logs warning, and continues
    - Add import for `EmptyFieldError`, `InvalidDateError` from `nacc_common.data_identification`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1, 7.2, 7.3_

  - [x] 3.3 Call __capture_duplicate_event in visit_row() at the duplicate detection point
    - In `visit_row()`, after `is_existing_visit()` returns True and BEFORE `self.__existing_visits[subject_lbl].append(transformed_row)`
    - Insert call: `self.__capture_duplicate_event(transformed_row)`
    - This ensures exactly one event per duplicate row at detection time, not during batch reprocessing
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 3.4 Wire VisitEventCapture creation and passing in run.py
    - Modify `gear/form_transformer/src/python/form_csv_app/run.py`
    - Add imports: `from botocore.exceptions import ClientError`, `from event_capture.event_capture import VisitEventCapture`, `from s3.s3_bucket import S3BucketInterface, S3InterfaceError`
    - In `FormCSVtoJSONTransformer.run()`, after getting `gear_name`:
      - Read `event_bucket` and `event_environment` from `context.config.opts`
      - If both are non-empty strings: create `S3BucketInterface.create_from_environment(event_bucket)` and `VisitEventCapture`, catch `(S3InterfaceError, ClientError)` and raise `GearExecutionError`
      - If only one is provided: log warning that both are required, set event_capture to None
      - If neither: event_capture stays None (backward-compatible)
    - Get file timestamp: `file_entry = self.__file_input.file_entry(context)`, `timestamp = file_entry.created`
    - Pass `event_capture`, `center_label=prj_adaptor.group`, `project_label=prj_adaptor.label`, `timestamp` to `run()` call
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.3, 5.4_

- [x] 4. Checkpoint - Verify source changes compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Write tests for event model extension
  - [x] 5.1 Write unit tests for ACTION_DUPLICATE_SUBMIT constant and VisitEvent acceptance
    - Create `common/test/python/event_capture/test_visit_events_duplicate_submit.py`
    - Test that ACTION_DUPLICATE_SUBMIT equals "duplicate-submit"
    - Test that VisitEvent accepts action="duplicate-submit" with datatype="form" and FormIdentification
    - Test that VisitEvent rejects action="duplicate-submit" with datatype="form" and non-FormIdentification data
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 5.2 Write property test for VisitEvent serialization with duplicate-submit (Property 1)
    - **Property 1: VisitEvent serialization round-trip for duplicate-submit**
    - In same test file `test_visit_events_duplicate_submit.py`
    - Use hypothesis to generate random valid DataIdentification with FormIdentification
    - Create VisitEvent with action="duplicate-submit", datatype="form"
    - Verify serialized output contains pipeline_adcid, visit_date, visit_number, module, ptid
    - **Validates: Requirements 1.3, 1.4**

  - [ ]* 5.3 Write property test for filename generation with hyphenated action (Property 6)
    - **Property 6: Filename generation for hyphenated actions**
    - In same test file `test_visit_events_duplicate_submit.py`
    - Use hypothesis to generate random VisitEvents with action="duplicate-submit"
    - Call `create_event_filename()` and verify output matches regex `^.*/log-duplicate-submit-\d{8}-\d{6}-\d+-[^/]+-[^/]+-\d{4}-\d{2}-\d{2}\.json$`
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 6. Write tests for form-transformer event capture integration
  - [x] 6.1 Write unit tests for run.py config handling and __capture_duplicate_event edge cases
    - Create `gear/form_transformer/test/python/test_duplicate_event_capture.py`
    - Test four config states: both present, only bucket, only environment, neither
    - Test that missing date field in row skips event capture (logs warning, doesn't raise)
    - Test that metadata copy failure does not trigger second event
    - _Requirements: 3.2, 3.3, 3.4, 5.4, 2.7, 6.3_

  - [ ]* 6.2 Write property test for captured event metadata correctness (Property 3)
    - **Property 3: Captured event contains correct metadata**
    - In same test file `test_duplicate_event_capture.py`
    - Use hypothesis to generate random transformed rows with valid fields
    - Mock `is_existing_visit()` to return True, mock `capture_event()`
    - Verify captured event has action="duplicate-submit", datatype="form", correct gear_name, timestamp, project_label, center_label
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6**

  - [x] 6.3 Write property test for event count equals duplicate count (Property 4)
    - **Property 4: Event count equals duplicate row count**
    - In same test file `test_duplicate_event_capture.py`
    - Generate N duplicate rows and M non-duplicate rows, process all through visit_row()
    - Verify capture_event call count equals N
    - **Validates: Requirements 6.1, 6.2**

  - [x] 6.4 Write property test for failure isolation (Property 5)
    - **Property 5: Event capture failure does not alter processing outcome**
    - In same test file `test_duplicate_event_capture.py`
    - Mock capture_event to raise an exception
    - Process duplicate rows, verify visit_row() still returns True
    - Verify rows are still added to __existing_visits collection
    - **Validates: Requirements 7.1, 7.2, 7.3, 2.8**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (lower-priority property tests that provide defense-in-depth for already-tested behavior)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- The design explicitly confirms that `VisitEventCapture`, `create_event_filename()`, and `FormPreprocessor` need NO changes
- The `CSVCaptureVisitor` in `common/src/python/event_capture/csv_capture_visitor.py` shows the exact pattern for per-row event capture

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3"] },
    { "id": 3, "tasks": ["3.4"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "6.1", "6.2", "6.3", "6.4"] }
  ]
}
```
