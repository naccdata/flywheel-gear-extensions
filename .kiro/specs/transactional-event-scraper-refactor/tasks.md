# Transactional Event Scraper Refactor - Tasks

## 1. Add New Data Models

- [-] 1.1 Create EventMatchKey model in models.py
  - Add ptid, date, module fields
  - Add from_visit_metadata class method
  - Implement __hash__ and __eq__ for dict key usage

- [ ] 1.2 Create QCEventData model in models.py
  - Add visit_metadata, qc_status, qc_completion_timestamp fields

- [ ] 1.3 Create UnmatchedSubmitEvents class in models.py
  - Implement __init__ with dict storage
  - Implement add(event) method
  - Implement find_and_remove(key) method
  - Implement get_remaining() method
  - Implement count() method

## 2. Add VisitMetadataExtractor Utilities

- [ ] 2.1 Create visit_metadata_extractor.py module
  - Copy VisitMetadataExtractor class from form_scheduler
  - Include from_qc_status_custom_info static method
  - Include from_json_file_metadata static method
  - Include is_valid_for_event static method

## 3. Create SubmitEventProcessor

- [ ] 3.1 Create submit_event_processor.py module
  - Create SubmitEventProcessor class
  - Implement __init__ with project, event_generator, unmatched_events, date_filter
  - Implement process_qc_logs() method
  - Implement _process_log_file() method
  - Implement _discover_qc_logs() method
  - Reuse existing extract_event_from_log from log_file_processor

## 4. Create QCEventProcessor

- [ ] 4.1 Create qc_event_processor.py module
  - Create QCEventProcessor class
  - Implement __init__ with project, event_generator, unmatched_events, event_capture, dry_run, date_filter

- [ ] 4.2 Implement JSON file processing methods
  - Implement process_json_files() method
  - Implement _process_json_file() method
  - Implement _discover_json_files() method (iterate subjects/sessions/acquisitions)

- [ ] 4.3 Implement QC event extraction methods
  - Implement _extract_qc_event_data() method
  - Implement _find_qc_status_for_json_file() method (use ErrorLogTemplate)
  - Add ErrorLogTemplate import

- [ ] 4.4 Implement event matching and enrichment methods
  - Implement _enrich_and_push_submit_event() method
  - Implement _push_qc_event() method
  - Add logging for matched/unmatched events

## 5. Update EventGenerator

- [ ] 5.1 Add create_qc_event method to event_generator.py
  - Accept QCEventData parameter
  - Create VisitEvent with ACTION_PASS_QC
  - Use qc_completion_timestamp from QCEventData
  - Include packet and visitnum from visit_metadata

## 6. Refactor EventScraper Orchestrator

- [ ] 6.1 Update EventScraper class in event_scraper.py
  - Update __init__ to create UnmatchedSubmitEvents
  - Update __init__ to create SubmitEventProcessor
  - Update __init__ to create QCEventProcessor
  - Remove old _event_generator initialization (move to processors)

- [ ] 6.2 Update scrape_events method
  - Phase 1: Call submit_processor.process_qc_logs()
  - Log count of unmatched submit events after Phase 1
  - Phase 2: Call qc_processor.process_json_files()
  - Phase 3: Log warning if unmatched submit events remain
  - Log sample of unmatched events (first 5)
  - Remove old _process_log_file and related methods

- [ ] 6.3 Remove obsolete methods
  - Remove _create_and_capture_submission_event
  - Remove _create_and_capture_pass_qc_event
  - Remove _log_summary
  - Remove _discover_log_files

## 7. Update Imports and Dependencies

- [ ] 7.1 Update imports in event_scraper.py
  - Add SubmitEventProcessor import
  - Add QCEventProcessor import
  - Add UnmatchedSubmitEvents import

- [ ] 7.2 Update imports in qc_event_processor.py
  - Add ErrorLogTemplate import
  - Add VisitMetadataExtractor import
  - Add FileQCModel import

## 8. Remove Obsolete Code

- [ ] 8.1 Remove ProcessingStatistics model from models.py (no longer needed)

- [ ] 8.2 Update main.py if it references ProcessingStatistics
  - Change return type if needed
  - Update logging

## 9. Sandbox Testing and Validation

- [ ] 9.1 Deploy to sandbox environment
  - Build Docker image
  - Deploy to Flywheel sandbox

- [ ] 9.2 Run on test project with known data
  - Execute gear on project with QC logs and JSON files
  - Monitor logs for errors

- [ ] 9.3 Validate results
  - Check logs for Phase 1/2/3 execution
  - Verify submit events have packet information in S3
  - Verify pass-QC events are created
  - Check for unmatched event warnings
  - Verify no duplicate events in S3

- [ ] 9.4 Investigate any issues
  - Review unmatched event warnings
  - Check if packet information is correctly populated
  - Verify matching logic works correctly

## 10. Optional: Add Minimal Unit Tests (Only if issues found)

- [ ]* 10.1 Add UnmatchedSubmitEvents tests
  - Test add and find_and_remove operations
  - Test that second match returns None

- [ ]* 10.2 Add enrichment tests
  - Test enrichment preserves non-None values
  - Test enrichment fills None values

## 11. Documentation and Cleanup

- [ ] 11.1 Update module docstrings
  - Document new modules
  - Update EventScraper docstring

- [ ] 11.2 Add inline comments for complex logic
  - Comment matching logic
  - Comment enrichment logic

- [ ] 11.3 Update CHANGELOG if applicable
  - Document refactoring changes
  - Note new packet information feature
