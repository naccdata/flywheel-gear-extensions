# Implementation Plan

- [x] 1. Create extended VisitMetadata model
- [x] 1.1 Create VisitMetadata class extending VisitKeys with packet field
  - Create new Pydantic model in appropriate module
  - Add optional packet field for form packet information
  - Add to_visit_event_fields() method for field name mapping
  - _Requirements: 7.1, 7.2_

- [x] 1.2 Write property test for VisitMetadata model
  - **Property 9: Extended Visit Metadata Model**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

- [x] 2. Update FileVisitAnnotator to use VisitMetadata
- [x] 2.1 Modify FileVisitAnnotator.annotate_qc_log_file() to use VisitMetadata
  - Update method signature to accept VisitMetadata instead of VisitKeys
  - Update _create_visit_metadata() to use VisitMetadata.model_dump()
  - Include packet information in visit metadata annotation
  - _Requirements: 7.3, 7.4_

- [x] 2.2 Write unit tests for FileVisitAnnotator changes
  - Test annotation with VisitMetadata including packet field
  - Test backward compatibility with existing QC status logs
  - _Requirements: 7.3, 7.4_

- [x] 3. Create simplified EventAccumulator
- [x] 3.1 Create new simplified EventAccumulator class
  - Remove complex visitor pattern implementations
  - Remove submit event and QC-fail event logic
  - Remove duplicate prevention logic
  - Add simple log_events() method for QC-pass events only
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3.2 Implement VisitMetadataExtractor utility
  - Add from_qc_status_custom_info() method using VisitMetadata.model_validate()
  - Add from_json_file_metadata() method with field name mapping
  - Add is_valid_for_event() validation method
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 3.3 Implement QC status log discovery using ErrorLogTemplate
  - Add find_qc_status_for_json_file() method
  - Use ErrorLogTemplate.instantiate() to generate expected filename
  - Use project.get_file() for direct file lookup
  - _Requirements: 2.1, 2.2, 2.5_

- [x] 3.4 Write property test for QC-pass event creation only
  - **Property 1: QC-Pass Event Creation Only**
  - **Validates: Requirements 1.1, 1.2**

- [x] 3.5 Write property test for JSON file processing
  - **Property 2: JSON File QC Status Processing**
  - **Validates: Requirements 1.3, 1.4, 2.1, 2.2**

- [x] 3.6 Write property test for no submit event creation
  - **Property 3: No Submit Event Creation**
  - **Validates: Requirements 1.5**

- [x] 4. Implement QC status checking and event creation
- [x] 4.1 Add QC status validation logic
  - Use FileQCModel.get_file_status() to check QC status from file custom info (info.qc)
  - Only create events for visits with PASS status
  - Extract QC completion timestamp from status log
  - _Requirements: 1.1, 1.2_

- [x] 4.2 Implement VisitEvent creation from VisitMetadata
  - Create VisitEvent with action="pass-qc" and datatype="form"
  - Use VisitMetadata.to_visit_event_fields() for field mapping
  - Set gear_name="form-scheduler" and timestamp from QC completion
  - Include pipeline_adcid from project.get_pipeline_adcid()
  - _Requirements: 6.1, 6.3, 6.4, 6.5_

- [x] 4.3 Write property test for visit metadata extraction priority
  - **Property 4: Visit Metadata Extraction Priority**
  - **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**

- [x] 4.4 Write property test for QC status log matching
  - **Property 5: QC Status Log to JSON File Matching**
  - **Validates: Requirements 2.5**

- [x] 4.5 Write property test for visit metadata validation
  - **Property 6: Visit Metadata Validation**
  - **Validates: Requirements 4.4, 4.5**

- [x] 5. Implement error handling and resilience
- [x] 5.1 Add comprehensive error handling
  - Handle missing QC status log files gracefully
  - Handle invalid visit metadata extraction
  - Handle S3 event logging failures
  - Log warnings but continue processing
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 5.2 Add missing configuration handling
  - Skip event logging entirely when event logger not configured
  - No errors when event logger is None
  - _Requirements: 5.5_

- [x] 5.3 Write property test for error resilience
  - **Property 7: Error Resilience**
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 5.4 Write property test for missing configuration handling
  - **Property 8: Missing Configuration Handling**
  - **Validates: Requirements 5.5**

- [x] 6. Update FormSchedulerQueue integration
- [x] 6.1 Update FormSchedulerQueue._log_pipeline_events()
  - Replace complex EventAccumulator usage with simplified version
  - Pass JSON file from finalization queue to EventAccumulator
  - Remove pipeline parameter from EventAccumulator constructor
  - Maintain existing error handling pattern
  - _Requirements: 8.5_

- [x] 6.2 Update EventAccumulator instantiation in FormSchedulerQueue
  - Remove pipeline parameter from constructor
  - Keep event_logger and datatype="form" parameters
  - Update method call to pass json_file instead of generic file
  - _Requirements: 8.5_

- [x] 6.3 Write property test for event structure compatibility
  - **Property 10: Event Structure Compatibility**
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

- [x] 7. Integration testing and validation
- [x] 7.1 Test end-to-end event logging flow
  - Test with JSON files in finalization queue
  - Verify QC status log discovery using ErrorLogTemplate
  - Verify VisitMetadata extraction from both sources
  - Verify QC-pass event creation and S3 logging
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7.2 Write integration tests for FormSchedulerQueue
  - Test EventAccumulator integration with FormSchedulerQueue
  - Test error handling doesn't affect pipeline processing
  - Test missing event logger configuration
  - _Requirements: 8.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.