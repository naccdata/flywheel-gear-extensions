# Tasks: Visit Metadata Architecture Refactoring

## Status: ✅ Complete

All refactoring tasks are complete. The visit metadata architecture has been successfully refactored with enhanced QC log filename support.

## Implementation Tasks

- [x] 1. Create Component Classes
  - [x] 1.1 Implement ParticipantIdentification
  - [x] 1.2 Implement VisitIdentification
  - [x] 1.3 Implement FormIdentification
  - [x] 1.4 Implement ImageIdentification

- [x] 2. Create Composite Class
  - [x] 2.1 Implement DataIdentification with composition
  - [x] 2.2 Implement factory methods (from_visit_metadata, from_form_record, from_visit_info)
  - [x] 2.3 Implement __getattr__ for flat access pattern
  - [x] 2.4 Implement serialize_model for flat serialization
  - [x] 2.5 Implement with_updates method

- [x] 3. Add Type Aliases
  - [x] 3.1 Add VisitKeys = DataIdentification alias
  - [x] 3.2 Add VisitMetadata = DataIdentification alias

- [x] 4. Update VisitEvent
  - [x] 4.1 Replace flat fields with data_identification: DataIdentification
  - [x] 4.2 Implement __getattr__ for backward compatibility
  - [x] 4.3 Implement serialize_model for field name mapping
  - [x] 4.4 Implement validate_datatype_consistency validator

- [x] 5. Update Tests
  - [x] 5.1 Update tests to use DataIdentification
  - [x] 5.2 Add tests for component classes
  - [x] 5.3 Add tests for serialization
  - [x] 5.4 Add tests for backward compatibility

- [x] 6. Verify Integration
  - [x] 6.1 Verify QC logging works with DataIdentification
  - [x] 6.2 Verify event capture works with updated VisitEvent
  - [x] 6.3 Verify file annotation works
  - [x] 6.4 Run full test suite

- [x] 7. Enhance QC Status Log Filenames
  - [x] 7.1 Implement visitor pattern for datatype-agnostic filename generation
    - Implemented ErrorLogIdentificationVisitor class
    - Visitor traverses DataIdentification structure
    - Extracts non-None fields in consistent order: ptid, visitnum (if present), date, module, datatype-specific fields (if present)
    - Normalizes fields (lowercase, leading zeros)
    - Returns None if required fields missing
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  
  - [x] 7.2 Implement instantiate() method using visitor pattern
    - Accepts DataIdentification object
    - Uses ErrorLogIdentificationVisitor to extract fields
    - Generates new format filename with all available fields
    - Works for any datatype through visitor pattern
    - _Requirements: 11.5_
  
  - [x] 7.3 Implement instantiate_legacy() method for backward compatibility
    - Uses same visitor pattern
    - Excludes visitnum and packet fields
    - Returns legacy format: {ptid}_{date}_{module}_qc-status.log
    - Supports backward compatibility with old filenames
    - _Requirements: 11.6, 11.7, 11.8, 11.9_
  
  - [x] 7.4 Update tests for visitor pattern implementation
    - Test with form data (visitnum, packet)
    - Test with image data (no packet)
    - Test backward compatibility scenarios
    - Test missing field handling
    - Test field normalization

## QC Filename Integration Tasks

- [x] 8. Update QCStatusLogManager
  - [x] 8.1 Update file creation to use instantiate()
    - Replaced calls to old instantiate() with new instantiate(data_id)
    - Pass DataIdentification object instead of record dict
    - Verified new filenames include visitnum and packet when available
    - _Requirements: 12.1_
  
  - [x] 8.2 Implement get_qc_log_filename() for file lookup
    - Try instantiate() first → check if file exists
    - Try instantiate_legacy() → check if file exists
    - Return new format filename if neither exists (what would be created)
    - Handle case where no files match
    - _Requirements: 12.2, 12.3_
  
  - [x] 8.3 Write integration tests for QCStatusLogManager
    - Test file creation with new format
    - Test file lookup with legacy filenames
    - Test file lookup with new filenames
    - Test backward compatibility scenarios
    - _Requirements: 12.4_

- [x] 9. Update EventAccumulator (form_scheduler)
  - [x] 9.1 Update QC log filename generation
    - Use instantiate() for filename generation
    - Ensure DataIdentification is available from form data
    - _Requirements: 13.1_
  
  - [x] 9.2 Update QC log file lookup
    - Handle both new and legacy filenames
    - _Requirements: 13.2_
  
  - [x] 9.3 Write tests for EventAccumulator changes
    - Test filename generation with visitnum and packet
    - Test file lookup with legacy filenames
    - Test backward compatibility
    - _Requirements: 13.5_

- [x] 10. Update EventProcessor (event_capture)
  - [x] 10.1 Update QC log filename generation
    - Use instantiate() for filename generation
    - Ensure DataIdentification is available from event data
    - _Requirements: 13.3_
  
  - [x] 10.2 Update QC log file lookup
    - Handle both new and legacy filenames
    - _Requirements: 13.4_
  
  - [x] 10.3 Write tests for EventProcessor changes
    - Test filename generation with visitnum and packet
    - Test file lookup with legacy filenames
    - Test backward compatibility
    - _Requirements: 13.5_

- [x] 11. Integration Testing and Verification
  - [x] 11.1 Run full test suite
    - Verify all unit tests pass
    - Verify all integration tests pass
    - Check for any regressions
  
  - [x] 11.2 Verify backward compatibility
    - Test that legacy filenames are still found
    - Test that new filenames include additional fields
    - Verify no breaking changes to existing functionality
  
  - [x] 11.3 Manual verification
    - Create test data with various field combinations
    - Verify filenames are generated correctly
    - Verify file lookup works with both formats

- [x] 12. Cleanup
  - [x] 12.1 Remove unused ErrorLogTemplate parameters
    - Removed id_field and date_field parameters from 4 initializations
    - Simplified code to use default constructor
  
  - [x] 12.2 Remove unused VisitLabelTemplate base class
    - Removed base class that was only used for inheritance
    - Simplified ErrorLogTemplate implementation
  
  - [x] 12.3 Update all gears to use QCStatusLogManager
    - Migrated form_qc_checker
    - Migrated form_qc_coordinator
    - Migrated form_transformer
    - Migrated identifier_provisioning
    - Migrated participant_transfer

## Future Tasks (Not in Scope)

These tasks are for future consideration but not part of the current refactoring:

- [ ] 7. Internal Code Migration
  - [ ] 7.1 Update common/ code to use DataIdentification directly
  - [ ] 7.2 Update gear/ code to use DataIdentification directly
  - [ ] 7.3 Use component extraction methods where beneficial

- [ ] 8. Documentation Updates
  - [ ] 8.1 Update all documentation to reference DataIdentification
  - [ ] 8.2 Add migration guide for external users
  - [ ] 8.3 Mark old names as deprecated in docstrings

- [ ] 9. Deprecation (Future Major Version)
  - [ ] 9.1 Add deprecation warnings for type aliases
  - [ ] 9.2 Update external user communication
  - [ ] 9.3 Plan removal timeline

- [ ] 10. Cleanup (Future Major Version)
  - [ ] 10.1 Remove type aliases
  - [ ] 10.2 Remove deprecated names
  - [ ] 10.3 Update all references

## Notes

- The refactoring maintains full backward compatibility through type aliases
- All existing code continues to work without modification
- The composed structure serializes to the same flat format as before
- QC logging, event capture, and file annotation all work unchanged
- Visitor pattern provides datatype-agnostic filename generation
- All production code has been migrated to use QCStatusLogManager
- Unused parameters and base classes have been removed for cleaner code
