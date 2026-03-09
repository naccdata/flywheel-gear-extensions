# Requirements Document

## Introduction

This document specifies requirements for implementing general authorization support in the user management gear. The feature enables users to receive Flywheel project access for general (non-center-specific) resources such as ADRC Portal pages.

The ADRC Portal uses Flywheel's authorization system where stub projects are created manually in the nacc admin group. Users are granted roles on these stub projects by the user management gear, and the portal checks Flywheel permissions to control access to portal pages (webinars, presentations, etc.).

Currently, the `UpdateUserProcess.__authorize_user()` method exists but has an empty implementation (line 348 in `user_processes.py`). This feature will complete the implementation to apply general authorizations to users.

**Important:** This refactoring leverages existing infrastructure:
- `UserProcessEnvironment.admin_group` property (already exists)
- `NACCGroup.get_project()` method (inherited from CenterAdaptor)
- `PageProjectMetadata` class (already exists in center metadata)
- `CenterAuthorizationVisitor.visit_page_project()` method (already exists)
- Visitor pattern established by `CenterAuthorizationVisitor`

The main work involves:
1. Implementing the empty `__authorize_user()` method in `UpdateUserProcess`
2. Creating a new `GeneralAuthorizationVisitor` class (similar to existing `CenterAuthorizationVisitor`)

## Glossary

- **User_Management_Gear**: The Flywheel gear that synchronizes users and authorizations from the NACC Directory to Flywheel
- **NACC_Directory**: The COmanage-based directory system that stores user information and authorizations
- **General_Authorization**: Authorization for resources not tied to a specific research center (e.g., portal pages)
- **Center_Authorization**: Authorization for resources tied to a specific research center (e.g., center data projects)
- **Page_Resource**: A resource representing an ADRC Portal page (e.g., webinars, presentations)
- **Stub_Project**: A Flywheel project that exists solely for authorization purposes, not for storing data
- **NACC_Admin_Group**: The Flywheel group (id: "nacc") that contains administrative and general resource projects
- **Authorization_Map**: A YAML configuration file that maps activities to Flywheel roles for specific projects
- **General_Authorization_Visitor**: A visitor class that applies general authorizations to users
- **Active_User_Entry**: A user entry from the directory with active status and general authorizations
- **User_Process_Environment**: The environment object that provides access to Flywheel groups and configuration

## Requirements

### Requirement 1: Implement General Authorization Method

**User Story:** As a system administrator, I want the user management gear to apply general authorizations to users, so that users can access ADRC Portal pages based on their directory permissions.

#### Acceptance Criteria

1. WHEN THE User_Management_Gear processes an Active_User_Entry with general authorizations, THE User_Management_Gear SHALL call the general authorization method with the user and authorizations
2. WHEN THE general authorization method receives authorizations with no activities, THE User_Management_Gear SHALL log an informational message and return without processing
3. WHEN THE general authorization method receives authorizations with activities, THE User_Management_Gear SHALL retrieve the NACC_Admin_Group from the User_Process_Environment
4. WHEN THE general authorization method has retrieved the NACC_Admin_Group, THE User_Management_Gear SHALL create a General_Authorization_Visitor with the user, authorizations, authorization map, and nacc group
5. WHEN THE General_Authorization_Visitor is created, THE User_Management_Gear SHALL iterate through all activities in the authorizations
6. WHEN THE User_Management_Gear encounters a Page_Resource activity, THE User_Management_Gear SHALL call the visitor's page resource method with the resource
7. WHEN THE general authorization method completes processing all activities, THE User_Management_Gear SHALL return without error

### Requirement 2: Create General Authorization Visitor

**User Story:** As a developer, I want a visitor class that handles general authorization logic, so that the authorization process follows the existing visitor pattern used for center authorizations.

#### Acceptance Criteria

1. THE General_Authorization_Visitor SHALL accept a user, authorizations, authorization map, nacc group, and event collector in its constructor
2. THE General_Authorization_Visitor SHALL provide a method to process Page_Resource objects
3. WHEN THE visitor processes a Page_Resource, THE General_Authorization_Visitor SHALL construct the project label as "page-{page_name}"
4. WHEN THE visitor has constructed the project label, THE General_Authorization_Visitor SHALL retrieve the project from the NACC_Admin_Group using the project label
5. IF THE project does not exist in the NACC_Admin_Group, THEN THE General_Authorization_Visitor SHALL log a warning message with the group ID and project label
6. IF THE project does not exist in the NACC_Admin_Group, THEN THE General_Authorization_Visitor SHALL return without assigning roles
7. WHEN THE visitor has retrieved the project, THE General_Authorization_Visitor SHALL query the Authorization_Map for roles using the project label and authorizations
8. IF THE Authorization_Map returns no roles, THEN THE General_Authorization_Visitor SHALL log a warning message with the user ID and project label
9. IF THE Authorization_Map returns no roles, THEN THE General_Authorization_Visitor SHALL return without assigning roles
10. WHEN THE visitor has retrieved roles from the Authorization_Map, THE General_Authorization_Visitor SHALL call the project's add user roles method with the user and role set
11. WHEN THE role assignment succeeds, THE General_Authorization_Visitor SHALL log an informational message with the user ID, group ID, and project label
12. IF THE role assignment fails with a ProjectError, THEN THE General_Authorization_Visitor SHALL log an error message with the error details

### Requirement 3: Verify NACC Admin Group Access

**User Story:** As a developer, I want to verify that the User_Process_Environment provides access to the NACC admin group, so that general authorization processing can access page projects.

**Note:** The `admin_group` property already exists in `UserProcessEnvironment` (line 147-149 in `user_process_environment.py`). This requirement is to verify its availability, not to create it.

#### Acceptance Criteria

1. THE User_Process_Environment SHALL have an existing property named admin_group
2. WHEN THE admin_group property is accessed, THE User_Process_Environment SHALL return a NACCGroup instance
3. THE NACCGroup instance SHALL represent the Flywheel group with ID "nacc"
4. THE NACCGroup instance SHALL provide the inherited get_project() method to retrieve projects by label

### Requirement 4: Handle Page Resources in Authorization Flow

**User Story:** As a system administrator, I want page resource authorizations to flow through the user processing pipeline, so that users with page access in the directory receive Flywheel project access.

#### Acceptance Criteria

1. WHEN THE User_Management_Gear processes an Active_User_Entry, THE User_Management_Gear SHALL extract general authorizations from the entry
2. WHEN THE User_Management_Gear has created or updated the Flywheel user, THE User_Management_Gear SHALL call the general authorization method with the user, email, and general authorizations
3. WHEN THE general authorization method is called, THE User_Management_Gear SHALL pass the complete Authorizations object including all Page_Resource activities
4. WHEN THE general authorization method encounters an error, THE User_Management_Gear SHALL log the error and continue processing other users

### Requirement 5: Log Authorization Events

**User Story:** As a system administrator, I want detailed logging of general authorization operations, so that I can troubleshoot authorization issues and verify correct operation.

#### Acceptance Criteria

1. WHEN THE general authorization method is called with no activities, THE User_Management_Gear SHALL log an informational message stating "No general authorizations for user {user_id}"
2. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL log a warning message stating "Page project not found: {group_id}/{project_label}"
3. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL log a warning message stating "No roles found for user {user_id} in page project {project_label}"
4. WHEN THE General_Authorization_Visitor successfully assigns roles, THE User_Management_Gear SHALL log an informational message stating "Added roles for user {user_id} to page project {group_id}/{project_label}"
5. WHEN THE role assignment fails, THE User_Management_Gear SHALL log an error message stating "Failed to assign roles: {error_message}"

### Requirement 6: Handle Missing Page Projects Gracefully

**User Story:** As a system administrator, I want the user management gear to continue processing when page projects are missing, so that one missing project does not prevent other authorizations from being applied.

#### Acceptance Criteria

1. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL log a warning
2. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL collect an error event with category FLYWHEEL_ERROR
3. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL continue processing other page resources for the same user
4. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL continue processing other users
5. WHEN THE General_Authorization_Visitor cannot find a page project, THE User_Management_Gear SHALL not raise an exception

### Requirement 7: Handle Missing Authorization Map Entries Gracefully

**User Story:** As a system administrator, I want the user management gear to continue processing when authorization map entries are missing, so that configuration gaps do not prevent other authorizations from being applied.

#### Acceptance Criteria

1. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL log a warning
2. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL collect an error event with category INSUFFICIENT_PERMISSIONS
3. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL continue processing other page resources for the same user
4. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL continue processing other users
5. WHEN THE Authorization_Map returns no roles for a page project, THE User_Management_Gear SHALL not raise an exception

### Requirement 8: Handle Role Assignment Failures Gracefully

**User Story:** As a system administrator, I want the user management gear to continue processing when role assignment fails, so that one failure does not prevent other users from being authorized.

#### Acceptance Criteria

1. WHEN THE project add user roles method raises a ProjectError, THE User_Management_Gear SHALL catch the exception
2. WHEN THE User_Management_Gear catches a ProjectError, THE User_Management_Gear SHALL log an error message with the error details
3. WHEN THE User_Management_Gear catches a ProjectError, THE User_Management_Gear SHALL collect an error event with category FLYWHEEL_ERROR
4. WHEN THE User_Management_Gear catches a ProjectError, THE User_Management_Gear SHALL continue processing other page resources for the same user
5. WHEN THE User_Management_Gear catches a ProjectError, THE User_Management_Gear SHALL continue processing other users

### Requirement 9: Support Multiple Page Resources Per User

**User Story:** As a user, I want to receive access to multiple portal pages when authorized, so that I can access all pages for which I have permissions.

#### Acceptance Criteria

1. WHEN THE User_Management_Gear processes authorizations with multiple Page_Resource activities, THE User_Management_Gear SHALL process each Page_Resource independently
2. WHEN THE User_Management_Gear processes multiple Page_Resource activities, THE User_Management_Gear SHALL apply roles for each corresponding page project
3. WHEN THE User_Management_Gear encounters an error processing one Page_Resource, THE User_Management_Gear SHALL continue processing remaining Page_Resource activities
4. WHEN THE User_Management_Gear completes processing all Page_Resource activities, THE User_Management_Gear SHALL have attempted role assignment for each page project

### Requirement 10: Integrate with Existing User Processing Flow

**User Story:** As a developer, I want general authorization to integrate seamlessly with the existing user processing flow, so that the implementation is consistent with center authorization processing.

#### Acceptance Criteria

1. THE general authorization method SHALL be called from the UpdateUserProcess visit method
2. THE general authorization method SHALL be called after the Flywheel user is created or updated
3. THE general authorization method SHALL be called before center authorization processing
4. THE general authorization method SHALL use the same Authorization_Map instance as center authorization processing
5. THE general authorization method SHALL follow the same error handling patterns as center authorization processing

### Requirement 11: Collect Error Events for Notification

**User Story:** As a system administrator, I want error events to be collected during general authorization processing, so that I receive notifications about authorization failures and can take corrective action.

#### Acceptance Criteria

1. THE General_Authorization_Visitor SHALL accept a UserEventCollector instance in its constructor
2. WHEN THE General_Authorization_Visitor cannot find a page project, THE General_Authorization_Visitor SHALL create a UserProcessEvent with event_type ERROR and category FLYWHEEL_ERROR
3. WHEN THE General_Authorization_Visitor creates an error event for missing project, THE General_Authorization_Visitor SHALL include the user context, project label, and descriptive message
4. WHEN THE Authorization_Map returns no roles for a page project, THE General_Authorization_Visitor SHALL create a UserProcessEvent with event_type ERROR and category INSUFFICIENT_PERMISSIONS
5. WHEN THE General_Authorization_Visitor creates an error event for missing roles, THE General_Authorization_Visitor SHALL include the user context, project label, and descriptive message
6. WHEN THE role assignment fails with a ProjectError, THE General_Authorization_Visitor SHALL create a UserProcessEvent with event_type ERROR and category FLYWHEEL_ERROR
7. WHEN THE General_Authorization_Visitor creates an error event for role assignment failure, THE General_Authorization_Visitor SHALL include the user context, project label, error details, and descriptive message
8. WHEN THE General_Authorization_Visitor creates any error event, THE General_Authorization_Visitor SHALL call collector.collect() to add the event to the collection
9. WHEN THE general authorization method completes, THE collected error events SHALL be available for notification generation
10. THE error events SHALL follow the same structure as existing user process events for consistent notification formatting

## Testing Requirements

### Unit Tests

1. Test general authorization method with empty authorizations
2. Test general authorization method with Page_Resource authorizations
3. Test general authorization method with multiple Page_Resource activities
4. Test General_Authorization_Visitor construction with event collector
5. Test General_Authorization_Visitor page resource processing with valid project
6. Test General_Authorization_Visitor page resource processing with missing project collects error event
7. Test General_Authorization_Visitor page resource processing with missing authorization map entry collects error event
8. Test General_Authorization_Visitor page resource processing with role assignment failure collects error event
9. Verify User_Process_Environment admin_group property returns NACCGroup (already exists)
10. Test UpdateUserProcess calls general authorization method for Active_User_Entry
11. Test error events have correct EventCategory (FLYWHEEL_ERROR, INSUFFICIENT_PERMISSIONS)
12. Test error events include user context information
13. Test error events include descriptive messages and action_needed fields

### Integration Tests

1. Test end-to-end general authorization for user with page access
2. Test end-to-end general authorization for user with multiple page resources
3. Test end-to-end general authorization with missing page project collects and exports error event
4. Test end-to-end general authorization with missing authorization map entry collects and exports error event
5. Test end-to-end general authorization with role assignment failure collects and exports error event
6. Test user receives both center and general authorizations
7. Test general authorization does not affect center authorization
8. Test general authorization logging produces expected messages
9. Test error events are included in notification email generation
10. Test error events are exported to CSV file with correct format

### Error Handling Tests

1. Test missing page project logs warning and continues
2. Test missing page project collects error event with FLYWHEEL_ERROR category
3. Test missing authorization map entry logs warning and continues
4. Test missing authorization map entry collects error event with INSUFFICIENT_PERMISSIONS category
5. Test role assignment failure logs error and continues
6. Test role assignment failure collects error event with FLYWHEEL_ERROR category
7. Test multiple errors in single user processing collects multiple error events
8. Test error in general authorization does not prevent center authorization
9. Test error events include all required fields (user_context, message, category, timestamp)
10. Test error events can be serialized to CSV format

## Dependencies

### Required Infrastructure

1. Page projects must exist in the nacc admin group before user management runs
2. Page projects must be created manually or via administrative script
3. Page project naming convention: "page-{page_name}" (e.g., "page-web")

### Required Configuration

1. Authorization_Map (auth_file input) must include entries for page projects
2. Authorization_Map entries must map page activities to Flywheel roles
3. Example auth_file entry:
   ```yaml
   page-web:
     view-page-web: [read-only]
   ```

### Coordinates With

1. NACC Directory: Provides general_page_web_access_level field
2. ADRC Portal: Checks Flywheel permissions on page projects
3. Center Authorization: Runs after general authorization in same user processing flow

## Open Questions

1. Should General_Authorization_Visitor be in the same file as CenterAuthorizationVisitor or a separate file?
   - **Recommendation:** Same file (authorization_visitor.py) for consistency
   - **Note:** `PageProjectMetadata` is already imported in this file, and `visit_page_project()` already exists in `CenterAuthorizationVisitor`

2. Should we support other general resource types beyond pages in the future?
   - **Recommendation:** Design visitor to be extensible for future resource types
   - **Note:** The `Authorizations.activities` structure already supports multiple resource types

3. How should we handle users with both center and general authorizations?
   - **Recommendation:** Process general authorizations first, then center authorizations independently
   - **Note:** The current flow in `UpdateUserProcess.visit()` calls `__authorize_user()` before center processing

4. Should general authorization failures block center authorization?
   - **Recommendation:** No, failures should be logged but not block other processing
   - **Note:** This matches the pattern in `CenterAuthorizationVisitor` which catches `AuthorizationError` and logs warnings

## Related Files

- `common/src/python/users/user_processes.py` - User processing logic (UpdateUserProcess class)
- `common/src/python/users/authorization_visitor.py` - Authorization visitors (add GeneralAuthorizationVisitor)
- `common/src/python/users/user_process_environment.py` - Process environment (verify admin_group property)
- `common/src/python/users/authorizations.py` - Authorization models (PageResource, Authorizations)
- `common/src/python/centers/center_group.py` - Center group and NACC group classes
- `gear/user_management/src/python/user_app/run.py` - Gear entry point

## Implementation Notes

### Existing Capabilities to Leverage

1. **UserProcessEnvironment.admin_group**: Property already exists (line 147-149 in `user_process_environment.py`) - returns NACCGroup instance
2. **NACCGroup.get_project()**: Inherited method from CenterAdaptor - retrieves projects by label
3. **PageProjectMetadata**: Already exists in center metadata classes (imported in `authorization_visitor.py`)
4. **CenterAuthorizationVisitor.visit_page_project()**: Already exists (lines 257-263 in `authorization_visitor.py`) - follows visitor pattern
5. **AuthMap.get()**: Existing method to retrieve roles based on project label and authorizations
6. **Authorizations.activities**: Existing property that contains the activities dictionary
7. **UserEventCollector**: Already available via `self.collector` in BaseUserProcess - used for error event collection
8. **EventCategory enum**: Existing categories include FLYWHEEL_ERROR and INSUFFICIENT_PERMISSIONS
9. **UserProcessEvent**: Existing model for creating error events with user context
10. **UserContext.from_user_entry()**: Existing class method to create user context from user entries

### Design Patterns

1. Follow the visitor pattern established by CenterAuthorizationVisitor
2. Use the same error handling approach as center authorization
3. Maintain separation between general and center authorization logic
4. Log at appropriate levels (info for success, warning for missing config, error for failures)

### Code Organization

1. Implement `UpdateUserProcess.__authorize_user()` in user_processes.py (currently empty stub at line 348)
2. Create `GeneralAuthorizationVisitor` class in authorization_visitor.py (similar to CenterAuthorizationVisitor)
3. Verify `UserProcessEnvironment.admin_group` property exists (already confirmed)
4. Add unit tests in `common/test/python/users_test/` (note: use `_test` suffix for test directories)
5. Add integration tests in `gear/user_management/test/python/`

### Error Handling Strategy

1. Missing projects: Log warning, collect error event (FLYWHEEL_ERROR), continue processing
2. Missing authorization map entries: Log warning, collect error event (INSUFFICIENT_PERMISSIONS), continue processing
3. Role assignment failures: Log error, collect error event (FLYWHEEL_ERROR), continue processing
4. Never raise exceptions that would stop user processing
5. Collect detailed information for troubleshooting and notification
6. Error events include user context, descriptive messages, and action_needed fields
7. Error events are exported to CSV and included in email notifications

### Future Enhancements

1. Support additional general resource types (if needed)
2. Add metrics for general authorization success/failure rates
3. Add validation that page projects exist before processing users
4. Add authorization map validation for completeness
5. Consider adding success events for general authorization (currently only errors are collected)
