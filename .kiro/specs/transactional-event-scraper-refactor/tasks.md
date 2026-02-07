# Transactional Event Scraper Refactor - Tasks

## 1. Add New Data Models

- [x] 1.1 Create EventMatchKey model in models.py
  - Add ptid, date, module fields
  - Add from_visit_metadata class method
  - Implement __hash__ and __eq__ for dict key usage

- [x] 1.2 Create QCEventData model in models.py
  - Add visit_metadata, qc_status, qc_completion_timestamp fields

- [x] 1.3 Create UnmatchedSubmitEvents class in models.py
  - Implement __init__ with dict storage
  - Implement add(event) method
  - Implement find_and_remove(key) method
  - Implement get_remaining() method
  - Implement count() method

## 2. Create SubmitEventProcessor

- [x] 2.1 Create submit_event_processor.py module
  - Create SubmitEventProcessor class
  - Implement __init__ with project, event_generator, unmatched_events, date_filter
  - Implement process_qc_logs() method
  - Implement _process_log_file() method
  - Implement _discover_qc_logs() method
  - Reuse existing extract_event_from_log from log_file_processor

## 3. Create QCEventProcessor

- [x] 3.1 Create qc_event_processor.py module
  - Create QCEventProcessor class
  - Implement __init__ with project, event_generator, unmatched_events, event_capture, dry_run, date_filter

- [x] 3.2 Implement JSON file processing methods
  - Implement process_json_files() method
  - Implement _process_json_file() method
  - Implement _discover_json_files() method (iterate subjects/sessions/acquisitions)

- [x] 3.3 Implement QC event extraction methods
  - Implement _extract_qc_event_data() method
  - Implement _find_qc_status_for_json_file() method (use ErrorLogTemplate)
  - Add ErrorLogTemplate import

- [x] 3.4 Implement event matching and enrichment methods
  - Implement _enrich_and_push_submit_event() method
  - Implement _push_qc_event() method
  - Add logging for matched/unmatched events

## 4. Update EventGenerator

- [x] 4.1 Add create_qc_event method to event_generator.py
  - Accept QCEventData parameter
  - Create VisitEvent with ACTION_PASS_QC
  - Use qc_completion_timestamp from QCEventData
  - Include packet and visitnum from visit_metadata

## 5. Refactor EventScraper Orchestrator

- [x] 5.1 Update EventScraper class in event_scraper.py
  - Update __init__ to create UnmatchedSubmitEvents
  - Update __init__ to create SubmitEventProcessor
  - Update __init__ to create QCEventProcessor
  - Remove old _event_generator initialization (move to processors)

- [x] 5.2 Update scrape_events method
  - Phase 1: Call submit_processor.process_qc_logs()
  - Log count of unmatched submit events after Phase 1
  - Phase 2: Call qc_processor.process_json_files()
  - Phase 3: Log warning if unmatched submit events remain
  - Log sample of unmatched events (first 5)
  - Remove old _process_log_file and related methods

- [x] 5.3 Remove obsolete methods
  - Remove _create_and_capture_submission_event
  - Remove _create_and_capture_pass_qc_event
  - Remove _log_summary
  - Remove _discover_log_files

## 6. Update Imports and Dependencies

- [x] 6.1 Update imports in event_scraper.py
  - Add SubmitEventProcessor import
  - Add QCEventProcessor import
  - Add UnmatchedSubmitEvents import

- [x] 6.2 Update imports in qc_event_processor.py
  - Add ErrorLogTemplate import
  - Add VisitMetadataExtractor import from event_capture.visit_extractor
  - Add FileQCModel import

## 7. Remove Obsolete Code

- [x] 7.1 Remove ProcessingStatistics model from models.py (no longer needed)

- [x] 7.2 Update main.py if it references ProcessingStatistics
  - Change return type if needed
  - Update logging

- [x] 7.3 Fix failing tests and type checks
  - Update test_event_scraper.py to match new refactored implementation
  - Remove references to ProcessingStatistics return values
  - Update tests to verify new three-phase workflow
  - Fix any remaining type check errors
  - Ensure all tests pass with pants test ::
  - Ensure all type checks pass with pants check ::

## 8. Sandbox Testing and Validation

- [x] 8.1 Deploy to sandbox environment
  - Build Docker image
  - Deploy to Flywheel sandbox

- [x] 8.2 Run on test project with known data
  - Execute gear on project with QC logs and JSON files
  - Monitor logs for errors

- [x] 8.3 Validate results
  - Check logs for Phase 1/2/3 execution
  - Verify submit events have packet information in S3
  - Verify pass-QC events are created
  - Check for unmatched event warnings
  - Verify no duplicate events in S3
  - **ISSUE FOUND**: All events are unmatched - matching logic is broken

- [x] 8.4 Fix matching bug
  - **Root Cause**: EventMatchKey date type mismatch
  - In UnmatchedSubmitEvents.add(): passing event.visit_date (datetime.date object)
  - In EventMatchKey.from_visit_metadata(): passing metadata.date (string)
  - Keys don't match because date types are different
  - **Fix**: Convert date to string consistently in both places

## 9. Optional: Add Minimal Unit Tests (Only if issues found)

- [ ]* 9.1 Add UnmatchedSubmitEvents tests
  - Test add and find_and_remove operations
  - Test that second match returns None

- [ ]* 9.2 Add enrichment tests
  - Test enrichment preserves non-None values
  - Test enrichment fills None values

- [x] 9.3 Add EventMatchKey matching tests
  - Test that submit events and QC events with same ptid/date/module match
  - Test case-insensitive module matching (UDS vs uds)
  - Test that keys with different ptid/date/module don't match
  - Test UnmatchedSubmitEvents.add() and find_and_remove() with matching keys

## 10. Documentation and Cleanup

- [x] 10.1 Update module docstrings
  - Document new modules
  - Update EventScraper docstring

- [x] 10.2 Add inline comments for complex logic
  - Comment matching logic
  - Comment enrichment logic

- [x] 10.3 Update CHANGELOG if applicable
  - Document refactoring changes
  - Note new packet information feature
