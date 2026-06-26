# Implementation Plan: General Authorization Support

## Overview

This implementation adds general authorization support to the user management gear, enabling users to receive Flywheel project access for non-center-specific resources like ADRC Portal pages. The main work involves implementing the empty `UpdateUserProcess.__authorize_user()` method and creating a new `GeneralAuthorizationVisitor` class that follows the established visitor pattern.

The implementation leverages existing infrastructure (admin_group property, NACCGroup.get_project(), PageProjectMetadata, visitor pattern) and focuses on error resilience - collecting detailed error events for notification without blocking processing.

## Tasks

- [x] 1. Implement GeneralAuthorizationVisitor class
  - [x] 1.1 Create GeneralAuthorizationVisitor class in authorization_visitor.py
    - Add class with constructor accepting user, authorizations, auth_map, nacc_group, collector parameters
    - Store parameters as private instance variables
    - Add class docstring explaining purpose and visitor pattern
    - _Requirements: 2.1_
    - _Dependencies: None_

  - [x] 1.2 Implement visit_page_resource() method
    - Construct project_label as f"page-{page_resource.name}"
    - Call nacc_group.get_project(project_label) to retrieve project
    - Handle missing project: log warning, create error event (FLYWHEEL_ERROR), collect event, return early
    - Create temporary StudyAuthorizations with study_id="general" and activities from self.__authorizations
    - Query auth_map.get() for roles using project_label and study_authorizations
    - Handle missing roles: log warning, create error event (INSUFFICIENT_PERMISSIONS), collect event, return early
    - Call project.add_user_roles() with user and roles
    - Handle ProjectError: log error, create error event (FLYWHEEL_ERROR), collect event
    - Log success message on successful role assignment
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 6.1, 6.2, 6.3, 6.5, 7.1, 7.2, 7.5, 8.1, 8.2, 8.3_
    - _Dependencies: 1.1_

  - [x] 1.3 Write unit tests for GeneralAuthorizationVisitor
    - Test constructor with all required parameters
    - Test visit_page_resource with valid project assigns roles correctly
    - Test visit_page_resource with missing project collects error event with FLYWHEEL_ERROR category
    - Test visit_page_resource with missing roles collects error event with INSUFFICIENT_PERMISSIONS category
    - Test visit_page_resource with role assignment failure collects error event with FLYWHEEL_ERROR category
    - Test project label construction format (page-{page_name})
    - Test error event content includes user context, message, action_needed
    - Test collector.collect() is called for each error event
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_
    - _Dependencies: 1.1, 1.2_

- [x] 2. Implement UpdateUserProcess.__authorize_user() method
  - [x] 2.1 Implement __authorize_user() method in user_processes.py
    - Check if authorizations.activities is empty - if so, log info message and return early
    - Retrieve admin_group from self.__env.admin_group
    - Create GeneralAuthorizationVisitor with user, authorizations, self.__env.authorization_map, admin_group, self.collector
    - Iterate through authorizations.activities.values()
    - For each activity with PageResource, call visitor.visit_page_resource(activity.resource)
    - Add try-except to catch unexpected exceptions, log error, don't propagate
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 4.1, 4.2, 4.3, 4.4, 5.1_
    - _Dependencies: 1.1, 1.2_

  - [x] 2.2 Write unit tests for __authorize_user()
    - Test with empty authorizations logs info and returns early
    - Test with page resource authorizations creates visitor and processes activities
    - Test with multiple page resource activities processes all
    - Test admin_group property access
    - Test visitor creation with correct parameters
    - Test error handling (exceptions don't propagate)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 4.1, 4.2, 4.3, 4.4, 5.1_
    - _Dependencies: 2.1_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - _Dependencies: 1.3, 2.2_

- [-] 4. Create test infrastructure and builders
  - [x] 4.1 Create test builders in conftest.py
    - Create UserBuilder for building test User objects
    - Create AuthorizationsBuilder for building test Authorizations objects
    - Create mock factories for NACCGroup, AuthMap, ProjectAdaptor
    - Create reusable fixtures for mock_nacc_group, mock_auth_map, mock_event_collector
    - _Requirements: Testing infrastructure_
    - _Dependencies: None_

  - [ ]* 4.2 Write property-based tests
    - **Property 1: General Authorization Method Invocation**
    - **Validates: Requirements 1.1, 4.1, 4.2, 4.3**
    - Test that for any active user entry with general authorizations, the general authorization method is called
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.3 Write property-based tests
    - **Property 2: Visitor Creation and Activity Processing**
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6**
    - Test that for any user and authorizations with page resource activities, visitor is created and processes each activity
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.4 Write property-based tests
    - **Property 3: Project Label Construction and Retrieval**
    - **Validates: Requirements 2.3, 2.4**
    - Test that for any page resource, project label is constructed as "page-{page_name}" and project is retrieved
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.5 Write property-based tests
    - **Property 4: Role Lookup and Assignment**
    - **Validates: Requirements 2.7, 2.10**
    - Test that for any page project that exists, roles are queried and assigned to user
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.6 Write property-based tests
    - **Property 5: Missing Project Error Handling**
    - **Validates: Requirements 2.5, 2.6, 6.2, 6.3**
    - Test that for any page resource where project doesn't exist, error event with FLYWHEEL_ERROR is collected and processing continues
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.7 Write property-based tests
    - **Property 6: Missing Roles Error Handling**
    - **Validates: Requirements 2.8, 2.9, 7.2**
    - Test that for any page project where auth map returns no roles, error event with INSUFFICIENT_PERMISSIONS is collected and processing continues
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.8 Write property-based tests
    - **Property 7: Role Assignment Failure Error Handling**
    - **Validates: Requirements 2.12, 8.1, 8.3**
    - Test that for any page project where role assignment raises ProjectError, error event with FLYWHEEL_ERROR is collected and processing continues
    - _Dependencies: 1.2, 2.1, 4.1_

  - [ ]* 4.9 Write property-based tests
    - **Property 11: Multiple Page Resources Processing**
    - **Validates: Requirements 9.1, 9.2, 9.4**
    - Test that for any user with multiple page resource activities, each is processed independently
    - _Dependencies: 1.2, 2.1, 4.1_

- [x] 5. Create integration tests
  - [x] 5.1 Create integration test file test_general_authorization_integration.py
    - Create file in gear/user_management/test/python/
    - _Requirements: Integration testing_
    - _Dependencies: None_

  - [x] 5.2 Write end-to-end integration tests
    - Test end-to-end general authorization for user with page access
    - Test end-to-end general authorization for user with multiple page resources
    - Test user receives both center and general authorizations
    - Test general authorization does not affect center authorization
    - Test general authorization occurs before center authorization
    - Test same authorization map is used for general and center authorization
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5_
    - _Dependencies: 1.2, 2.1, 5.1_

  - [ ]* 5.3 Write error event integration tests
    - Test end-to-end with missing page project collects and exports error event
    - Test end-to-end with missing authorization map entry collects and exports error event
    - Test end-to-end with role assignment failure collects and exports error event
    - Test error events are included in notification email generation
    - Test error events are exported to CSV file with correct format
    - Test multiple errors in single user processing collects multiple error events
    - Test error in general authorization does not prevent center authorization
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10_
    - _Dependencies: 1.2, 2.1, 5.1_

  - [ ]* 5.4 Write logging verification tests
    - Test general authorization logging produces expected messages
    - Test info log for no general authorizations
    - Test warning log for missing page project
    - Test warning log for missing authorization map entry
    - Test error log for role assignment failure
    - Test success log for successful role assignment
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
    - _Dependencies: 1.2, 2.1, 5.1_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - _Dependencies: 5.2_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties across generated inputs
- Unit tests validate specific examples and error handling paths
- Integration tests validate end-to-end flows and error event collection
