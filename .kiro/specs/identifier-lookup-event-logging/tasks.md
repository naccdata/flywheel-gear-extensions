# Implementation Plan

- [x] 1. Add event logging configuration to identifier lookup gear
- [x] 1.1 Add configuration parameters to gear manifest
  - Add `environment` parameter (string, default "prod", options ["prod", "dev"])
  - Add `event_bucket` parameter (string, default "nacc-event-logs")
  - Update manifest.json with new configuration options
  - _Requirements: 4.2, 4.3_

- [x] 1.2 Update IdentifierLookupVisitor initialization
  - Add event logging configuration parameters to constructor
  - Extract environment and event_bucket from gear context config
  - Pass configuration to create() method
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 2. Initialize event logging infrastructure
- [x] 2.1 Add S3 bucket and event logger initialization
  - Create S3BucketInterface in IdentifierLookupVisitor.create()
  - Handle S3 bucket access errors with clear error messages
  - Create VisitEventLogger with S3 bucket and environment
  - Store event logger as instance variable
  - _Requirements: 4.1, 4.4, 4.5_

- [x] 2.2 Extract file creation timestamp
  - Get file entry from input file wrapper in run() method
  - Extract created timestamp from file entry
  - Pass timestamp to __build_naccid_lookup() method
  - _Requirements: 2.4_

- [x] 3. Integrate CSVLoggingVisitor into processing pipeline
- [x] 3.1 Create CSVLoggingVisitor in __build_naccid_lookup()
  - Extract center label and project label from project adaptor
  - Create CSVLoggingVisitor with action="submit" and datatype="form"
  - Configure with module configs, error writer, and timestamp
  - Pass event logger to visitor
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

- [x] 3.2 Add CSVLoggingVisitor to AggregateCSVVisitor
  - Add event logging visitor to visitors list in AggregateCSVVisitor
  - Ensure visitors list includes: NACCIDLookupVisitor, QCStatusLogCSVVisitor, CSVLoggingVisitor
  - Verify visit_all_strategy is used for visitor coordination
  - _Requirements: 3.1, 3.2_

- [x] 3.3 Write property test for submit event creation
  - **Property 1: Submit Event Creation**
  - **Validates: Requirements 1.1, 1.2**

- [x] 3.4 Write property test for missing field resilience
  - **Property 2: Missing Field Resilience**
  - **Validates: Requirements 1.3**

- [x] 4. Verify direction-specific behavior
- [x] 4.1 Ensure event logging only in nacc direction with QC logging
  - Verify CSVLoggingVisitor only created in __build_naccid_lookup()
  - Verify __build_center_lookup() does not include event logging
  - Verify event logging requires form_configs_file (same as QC logging)
  - _Requirements: 1.4, 3.3_

- [x] 4.2 Write property test for direction-specific event logging
  - **Property 3: Direction-Specific Event Logging**
  - **Validates: Requirements 1.4, 3.3, 6.1**

- [x] 5. Implement error handling and resilience
- [x] 5.1 Verify visitor independence
  - Confirm AggregateCSVVisitor with visit_all_strategy handles visitor failures independently
  - Verify event logging failures don't affect identifier lookup or QC logging
  - Ensure success determination based on identifier lookup results
  - _Requirements: 1.5, 3.4, 3.5_

- [x] 5.2 Write property test for event logging resilience
  - **Property 4: Event Logging Resilience**
  - **Validates: Requirements 1.5**

- [x] 5.3 Write property test for visitor independence
  - **Property 6: Visitor Independence**
  - **Validates: Requirements 3.4**

- [x] 5.4 Write property test for success determination
  - **Property 7: Success Determination**
  - **Validates: Requirements 3.5, 6.5**

- [x] 6. Verify backward compatibility
- [x] 6.1 Test output format preservation
  - Verify output CSV file format unchanged
  - Verify QC metadata structure unchanged
  - Compare output with and without event logging
  - _Requirements: 6.4_

- [x] 6.2 Test error reporting preservation
  - Verify identifier lookup error messages unchanged
  - Verify error file structure unchanged
  - Compare error output with and without event logging
  - _Requirements: 6.2_

- [x] 6.3 Write property test for output format preservation
  - **Property 8: Output Format Preservation**
  - **Validates: Requirements 6.4**

- [x] 6.4 Write property test for error reporting preservation
  - **Property 9: Error Reporting Preservation**
  - **Validates: Requirements 6.2**

- [x] 7. Verify event metadata correctness
- [x] 7.1 Test event metadata fields
  - Verify events contain correct center label and project label
  - Verify events contain correct gear name
  - Verify events use file creation timestamp
  - Verify events have datatype="form"
  - Verify events include packet when present in CSV
  - _Requirements: 2.2, 2.4, 2.5, 2.6_

- [x] 7.2 Write property test for event metadata correctness
  - **Property 5: Event Metadata Correctness**
  - **Validates: Requirements 2.2, 2.4, 2.5, 2.6**

- [x] 8. Update gear manifest and documentation
- [x] 8.1 Update manifest.json
  - Add environment configuration parameter
  - Add event_bucket configuration parameter
  - Update gear description to mention event logging
  - _Requirements: 4.2, 4.3_

- [x] 8.2 Update gear documentation
  - Document new configuration parameters
  - Explain event logging behavior
  - Note that event logging only occurs with QC logging
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
