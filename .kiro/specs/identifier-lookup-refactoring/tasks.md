# Implementation Plan

- [x] 1. Prepare refactoring foundation
- [x] 1.1 Create backup and new feature branch
  - Create backup branch from current feature/add-event-logging branch
  - Name backup branch "backup/add-event-logging-before-refactoring"
  - Create new branch "feature/identifier-lookup-refactoring" from current state
  - Ensure clean working directory before starting refactoring
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 1.2 Set up test fixtures and documentation
  - Create backup of current NACCIDLookupVisitor implementation
  - Set up test fixtures for backward compatibility verification
  - Document current behavior for regression testing
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 1.3 Write property test for backward compatibility baseline
  - **Property 6: Backward Compatibility**
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 2. Refactor NACCIDLookupVisitor to remove QC responsibilities
- [x] 2.1 Remove QC-related dependencies from constructor
  - Remove project, gear_name, and QC-related parameters
  - Remove QCStatusLogManager and FileVisitAnnotator setup
  - Simplify constructor to focus on identifier lookup only
  - _Requirements: 1.4_

- [x] 2.2 Remove QC logging logic from visit_row method
  - Remove __update_visit_error_log method calls
  - Remove QC status log creation and updates
  - Keep only identifier lookup and CSV transformation logic
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2.3 Simplify header validation for identifier lookup only
  - Focus header validation on identifier lookup requirements
  - Remove QC-specific field validation
  - _Requirements: 1.5_

- [x] 2.4 Write property test for NACCIDLookupVisitor separation of concerns
  - **Property 1: NACCIDLookupVisitor Separation of Concerns**
  - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 2.5 Write unit tests for simplified NACCIDLookupVisitor
  - Test identifier lookup functionality in isolation
  - Test CSV transformation without QC dependencies
  - Test error handling for missing identifiers
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 3. Create visitor coordination mechanism ✅ COMPLETED
- [x] 3.1 Implement result communication between visitors ✅ COMPLETED
  - ✅ Enhanced existing AggregateCSVVisitor with short_circuit=False parameter
  - ✅ Enhanced existing QCStatusLogCSVVisitor with determine_status_from_errors parameter
  - ✅ Implemented shared error writer coordination using existing FileError objects
  - ✅ Ensured visit information consistency across visitors
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 3.2 Write property test for visitor coordination ✅ COMPLETED
  - **Property 7: Visitor Coordination** ✅ PASSING
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 3.3 Write property test for visitor isolation ✅ COMPLETED
  - **Property 8: Visitor Isolation** ✅ PASSING
  - **Validates: Requirements 5.5**

- [x] 4. Update run.py to use AggregateCSVVisitor pattern
- [x] 4.1 Modify __build_naccid_lookup method
  - Create simplified NACCIDLookupVisitor instance
  - Create QCStatusLogCSVVisitor instance with appropriate configuration
  - Combine visitors using AggregateCSVVisitor
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4.2 Configure QCStatusLogCSVVisitor for identifier lookup context
  - Set up QCStatusLogManager with correct error log template
  - Configure module configs and project adaptor
  - Ensure proper gear name and error writer setup
  - _Requirements: 2.1, 2.5_

- [x] 4.3 Implement error coordination logic
  - Ensure QC visitor can determine identifier lookup results
  - Coordinate error reporting between visitors
  - Handle miscellaneous errors appropriately
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 4.4 Write property test for aggregate visitor coordination
  - **Property 4: Aggregate Visitor Coordination**
  - **Validates: Requirements 3.2, 3.3**

- [x] 4.5 Write property test for error propagation
  - **Property 5: Error Propagation**
  - **Validates: Requirements 3.4, 3.5**

- [x] 5. Implement QC status determination logic
- [x] 5.1 Configure QC visitor to read identifier lookup results
  - Implement logic to determine PASS/FAIL based on error writer state
  - Ensure proper error details are included in FAIL status
  - Handle QC logging failures gracefully
  - _Requirements: 2.2, 2.3, 2.4_

- [x] 5.2 Write property test for QC status determination
  - **Property 2: QC Status Determination**
  - **Validates: Requirements 2.2, 2.3**

- [x] 5.3 Write property test for QC logging resilience
  - **Property 3: QC Logging Resilience**
  - **Validates: Requirements 2.4**

- [x] 5.4 Write property test for QC visitor usage
  - **Property 10: QC Visitor Usage**
  - **Validates: Requirements 2.1**

- [x] 5.5 Write property test for visit key consistency
  - **Property 9: Visit Key Consistency**
  - **Validates: Requirements 2.5**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Verify backward compatibility
- [x] 7.1 Run comprehensive regression tests
  - Test with existing CSV files and configurations
  - Verify identical output files are produced
  - Verify error messages and QC log structures are unchanged
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7.2 Update existing tests for new architecture
  - Modify tests that directly instantiate NACCIDLookupVisitor
  - Update test fixtures to work with new constructor signature
  - Ensure test coverage remains comprehensive
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.