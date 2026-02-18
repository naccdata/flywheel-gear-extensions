# Tasks: Visit Metadata Architecture Refactoring

## Status: 🔄 In Progress

Core refactoring tasks are complete. QC filename integration tasks are in progress.

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
  - [ ] 7.1 Refactor instantiate_from_data_identification() to be datatype-agnostic
    - Remove hardcoded form-specific logic (visitnum, packet checks)
    - Inspect DataIdentification structure to determine which fields are present
    - Include all non-None fields in consistent order: ptid, visitnum (if present), date, module, datatype-specific fields (if present)
    - Determine field order by examining data_id.visit and data_id.data components
    - Normalize fields (lowercase, leading zeros)
    - Return None if required fields missing
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  
  - [ ] 7.2 Refactor get_possible_filenames() to be datatype-agnostic
    - Remove hardcoded form-specific fallback logic
    - Generate filename variations by systematically removing optional fields
    - Determine which fields are optional by inspecting DataIdentification structure
    - Return list in priority order: most complete first, legacy format last
    - Deduplicate filenames
    - Support backward compatibility with legacy filenames
    - _Requirements: 11.6, 11.7, 11.8_
  
  - [x] 7.3 Preserve legacy instantiate() method
    - Keep existing method signature unchanged
    - Maintain backward compatibility with existing code
    - _Requirements: 11.9_
  
  - [ ]* 7.4 Update tests for datatype-agnostic implementation
    - Test with form data (visitnum, packet)
    - Test with image data (no packet)
    - Test with hypothetical future datatype
    - Test backward compatibility scenarios
    - Test missing field handling
    - Test lookup fallback order
    - Test field normalization

## QC Filename Integration Tasks

- [ ] 8. Update QCStatusLogManager
  - [ ] 8.1 Update file creation to use instantiate_from_data_identification()
    - Replace calls to instantiate() with instantiate_from_data_identification()
    - Pass DataIdentification object instead of record dict
    - Verify new filenames include visitnum and packet when available
    - _Requirements: 12.1_
  
  - [ ] 8.2 Update file lookup to use get_possible_filenames()
    - Replace single filename lookup with multiple filename attempts
    - Try filenames in priority order
    - Return first match found
    - Handle case where no files match
    - _Requirements: 12.2, 12.3_
  
  - [ ]* 8.3 Write integration tests for QCStatusLogManager
    - Test file creation with new format
    - Test file lookup with legacy filenames
    - Test file lookup with new filenames
    - Test backward compatibility scenarios
    - _Requirements: 12.4_

- [ ] 9. Update EventAccumulator (form_scheduler)
  - [ ] 9.1 Update QC log filename generation
    - Use instantiate_from_data_identification() for filename generation
    - Ensure DataIdentification is available from form data
    - _Requirements: 13.1_
  
  - [ ] 9.2 Update QC log file lookup
    - Use get_possible_filenames() for file lookup
    - Try multiple filename formats
    - Handle both new and legacy filenames
    - _Requirements: 13.2_
  
  - [ ]* 9.3 Write tests for EventAccumulator changes
    - Test filename generation with visitnum and packet
    - Test file lookup with legacy filenames
    - Test backward compatibility
    - _Requirements: 13.5_

- [ ] 10. Update EventProcessor (event_capture)
  - [ ] 10.1 Update QC log filename generation
    - Use instantiate_from_data_identification() for filename generation
    - Ensure DataIdentification is available from event data
    - _Requirements: 13.3_
  
  - [ ] 10.2 Update QC log file lookup
    - Use get_possible_filenames() for file lookup
    - Try multiple filename formats
    - Handle both new and legacy filenames
    - _Requirements: 13.4_
  
  - [ ]* 10.3 Write tests for EventProcessor changes
    - Test filename generation with visitnum and packet
    - Test file lookup with legacy filenames
    - Test backward compatibility
    - _Requirements: 13.5_

- [ ] 11. Integration Testing and Verification
  - [ ] 11.1 Run full test suite
    - Verify all unit tests pass
    - Verify all integration tests pass
    - Check for any regressions
  
  - [ ] 11.2 Verify backward compatibility
    - Test that legacy filenames are still found
    - Test that new filenames include additional fields
    - Verify no breaking changes to existing functionality
  
  - [ ] 11.3 Manual verification
    - Create test data with various field combinations
    - Verify filenames are generated correctly
    - Verify file lookup works with both formats

- [ ]* 12. Optional: File Renaming for Legacy Files
  - [ ]* 12.1 Implement file renaming logic
    - When old-format file is discovered during lookup
    - Check if DataIdentification has additional non-None fields (visitnum or packet)
    - Rename file to new format if additional fields are available
    - Update file metadata if needed
    - _Requirements: 11.8_
  
  - [ ]* 12.2 Add safety checks for renaming
    - Verify new filename doesn't already exist
    - Handle rename failures gracefully
    - Log rename operations for audit trail
  
  - [ ]* 12.3 Write tests for file renaming
    - Test renaming with visitnum added
    - Test renaming with packet added
    - Test renaming with both fields added
    - Test handling of rename conflicts
    - Test that renaming is skipped when no new fields available

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
