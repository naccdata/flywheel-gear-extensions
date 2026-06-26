# Implementation Plan: Registry Person Multivalued Attributes

## Overview

This implementation plan adds comprehensive test coverage for the RegistryPerson class and enhances its email handling capabilities. The approach is to first add tests for existing functionality to establish a safety net, then incrementally add new features with tests, ensuring backward compatibility throughout.

## Tasks

- [x] 1. Set up test infrastructure and fixtures
  - Create test directory structure in `common/test/python/users/`
  - Create shared test fixtures for generating CoPersonMessage objects
  - Add hypothesis to test dependencies if not already present
  - Create helper functions for building EmailAddress, Name, Identifier objects
  - _Requirements: 2.1-2.10_

- [x]* 2. Implement unit tests for existing email functionality
  - [x]* 2.1 Write tests for email_address property priority logic
    - Test organizational email takes priority over regular emails
    - Test fallback to first email when no org email
    - Test None when no emails exist
    - _Requirements: 1.1, 1.5_
    - _Note: Tests business logic of priority selection, not simple list access_
  
  - [x]* 2.2 Write tests for has_email method
    - Test finds email in list (search logic)
    - Test returns False for missing email
    - _Requirements: 1.9_
    - _Note: Tests search logic, not list iteration_
  
  - [x]* 2.3 Write tests for organization_email_addresses property
    - Test returns emails from claimed org identity (finding logic)
    - Test returns empty list when no org identity
    - _Requirements: 1.7_
    - _Note: Tests org identity lookup logic via __get_claim_org_

- [ ]* 3. Implement unit tests for name and identifier functionality
  - [ ]* 3.1 Write tests for primary_name property
    - Test extracts and formats primary name as "Given Family"
    - Test returns None when no names exist
    - Test returns None when no name marked as primary
    - _Requirements: 2.4_
    - _Note: Tests string formatting logic, not attribute access_
  
  - [ ]* 3.2 Write tests for identifiers method with predicates
    - Test filters identifiers using custom predicate function
    - Test returns all identifiers with default predicate
    - _Requirements: 2.5_
    - _Note: Tests predicate filtering logic, not simple list return_
  
  - [ ]* 3.3 Write tests for registry_id method
    - Test extracts naccid identifier with status="A"
    - Test returns None when no naccid exists
    - Test ignores inactive naccid (status != "A")
    - _Requirements: 2.7_
    - _Note: Tests specific identifier type and status filtering logic_

- [ ] 4. Implement unit tests for complex business logic
  - [x] 4.1 Write tests for is_claimed method (current behavior)
    - Test returns True when active AND has email AND has oidcsub
    - Test returns False without oidcsub identifier
    - Test returns False when inactive
    - Test returns False without email
    - _Requirements: 2.6_
    - _Note: Tests complex multi-condition logic, not simple status check_
  
  - [ ]* 4.2 Write tests for create factory method
    - Test creates RegistryPerson with correct CoPersonMessage structure
    - Test sets name, email, role, and status correctly
    - _Requirements: 2.10_
    - _Note: Tests factory construction logic_

- [ ]* 5. Checkpoint - Ensure all existing functionality tests pass
  - Run all tests to verify existing behavior is captured
  - Ensure all tests pass, ask the user if questions arise

- [ ] 6. Add new email filtering properties
  - [x] 6.1 Implement official_email_addresses property
    - Add property that filters emails by type="official"
    - Return empty list if no official emails
    - Preserve order from COManage
    - _Requirements: 1.8, 3.1, 3.3_
    - _Note: Implements filtering logic, not simple list return_
  
  - [x] 6.2 Implement verified_email_addresses property
    - Add property that filters emails by verified=True
    - Return empty list if no verified emails
    - Preserve order from COManage
    - _Requirements: 3.2_
    - _Note: Implements filtering logic_
  
  - [x] 6.3 Write unit tests for new filtering properties
    - Test official_email_addresses filters by type correctly
    - Test verified_email_addresses filters by verified status correctly
    - Test order preservation from original list
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
    - _Note: Tests filtering logic, not list comprehension itself_

- [x] 7. Update email_address property with priority logic
  - [x] 7.1 Refactor email_address to use priority chain
    - Update to check organizational → official → verified → any → None
    - Maintain backward compatibility
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Note: Implements complex priority selection logic_
  
  - [x] 7.2 Write unit tests for updated priority logic
    - Test each level of priority chain (org, official, verified, any)
    - Test fallback behavior through the chain
    - Test edge cases (multiple of same type, mixed types)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Note: Tests priority decision logic, not attribute access_

- [x] 8. Update is_claimed method to require verified email
  - [x] 8.1 Modify is_claimed to check for verified email
    - Add check for verified_email_addresses (not just any email)
    - Return False if no verified emails
    - Maintain other checks (active, oidcsub)
    - _Requirements: 1.10_
    - _Note: Updates complex multi-condition business logic_
  
  - [x] 8.2 Write unit tests for updated is_claimed
    - Test returns False without verified email (even with unverified email)
    - Test returns True with verified email AND oidcsub AND active
    - Test all combinations of conditions
    - _Requirements: 1.10_
    - _Note: Tests updated complex logic with new condition_

- [x] 9. Update documentation and type hints
  - [x] 9.1 Add comprehensive docstrings
    - Document email_address priority logic
    - Document difference between email_address and email_addresses
    - Document what constitutes "claimed" and "active"
    - Document all new properties
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 9.2 Verify type hints are complete
    - Ensure all methods have parameter and return type hints
    - Add type hints to new properties
    - _Requirements: 5.2_

- [x] 10. Checkpoint - Ensure all tests pass
  - Run full test suite
  - Verify backward compatibility
  - Ensure all tests pass, ask the user if questions arise

- [ ]* 11. Implement property-based tests
  - [ ]* 11.1 Write property test for email priority selection
    - **Property 1: Email Priority Selection**
    - Generate CoPersonMessage with varying email configurations
    - Verify email_address follows priority: org → official → verified → any → None
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
    - _Note: Tests priority decision logic across random inputs_
  
  - [ ]* 11.2 Write property test for email filtering correctness
    - **Property 2: Email Filtering Correctness**
    - Verify official_email_addresses returns only type="official" emails
    - Verify verified_email_addresses returns only verified=True emails
    - Verify order preservation from original list
    - **Validates: Requirements 1.7, 1.8, 3.1, 3.2, 3.3, 3.5**
    - _Note: Tests filtering logic correctness_
  
  - [ ]* 11.3 Write property test for email search completeness
    - **Property 3: Email Search Completeness**
    - Generate person with 1-5 emails
    - Verify has_email finds any email in the list
    - Verify has_email returns False for emails not in list
    - **Validates: Requirements 1.9, 3.6**
    - _Note: Tests search logic completeness_
  
  - [ ]* 11.4 Write property test for claimed account validation
    - **Property 4: Claimed Account Validation**
    - Verify is_claimed requires: active AND verified email AND oidcsub
    - Test with various combinations of conditions
    - **Validates: Requirements 1.10**
    - _Note: Tests complex multi-condition logic_
  
  - [ ]* 11.5 Write property test for primary name extraction
    - **Property 5: Primary Name Extraction**
    - Generate persons with 0-2 names
    - Verify primary_name returns "Given Family" format for primary name
    - **Validates: Requirements 2.4**
    - _Note: Tests name formatting logic_
  
  - [ ]* 11.6 Write property test for identifier filtering
    - **Property 6: Identifier Filtering**
    - Generate persons with various identifiers
    - Test filtering with different predicate functions
    - Verify predicate logic is applied correctly
    - **Validates: Requirements 2.5**
    - _Note: Tests predicate filtering logic_
  
  - [ ]* 11.7 Write property test for registry ID extraction
    - **Property 7: Registry ID Extraction**
    - Generate persons with various identifier types and statuses
    - Verify registry_id extracts only active naccid
    - **Validates: Requirements 2.7**
    - _Note: Tests specific type and status filtering logic_

- [ ] 12. Final validation and cleanup
  - [x] 12.1 Run full test suite with coverage
    - Verify >95% line coverage for RegistryPerson
    - Verify 100% branch coverage
    - _Requirements: 2.1-2.10_
  
  - [x] 12.2 Run linting and type checking
    - Run `pants fix` to format code
    - Run `pants lint` to check code quality
    - Run `pants check` to verify type hints
    - _Requirements: 5.2_
  
  - [x] 12.3 Verify backward compatibility
    - Check that existing code using RegistryPerson still works
    - Verify all existing properties and methods unchanged
    - _Requirements: 4.1-4.10_

- [x] 13. Final checkpoint - Complete implementation
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Tests focus on business logic only - we don't test simple Pydantic model access
- Tests are written before refactoring to ensure safety
- Property-based tests provide comprehensive coverage across randomized inputs
- All commands should be run inside the dev container using `./bin/exec-in-devcontainer.sh` or `./bin/terminal.sh`

## What We're NOT Testing (Pydantic Model Behavior)

The following are simple attribute access or trivial operations that don't need testing:
- `email_addresses` property - just returns the list from Pydantic model
- `is_active()` basic status check - just checks `status == "A"`
- `creation_date` property - just accesses nested attributes
- `identifiers()` with no predicate - just returns the list
- Empty list/None returns for missing data - trivial null checks

These are assumed to work correctly in the Pydantic models and don't contain business logic.
