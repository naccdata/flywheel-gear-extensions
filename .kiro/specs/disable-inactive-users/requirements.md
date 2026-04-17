# Requirements Document

## Introduction

The user management gear processes a directory of user entries, each with an `active` flag. Currently, entries marked inactive are silently ignored by `InactiveUserProcess`, which only logs a message and takes no action. This feature updates the inactive user handling to disable matching Flywheel users and capture disable events for reporting. Registry cleanup (COManage) and REDCap removal are explicitly out of scope.

## Glossary

- **User_Management_Gear**: The Flywheel gear that processes a directory of user entries, splitting them into active and inactive queues and applying the appropriate process to each.
- **InactiveUserProcess**: The user process class responsible for handling user entries marked inactive in the directory. Currently a no-op that logs and skips entries.
- **UserEntry**: A base data model representing a single user record from the NACC directory, including fields for name, email, auth_email, active flag, and approved flag.
- **FlywheelProxy**: A proxy class that wraps the Flywheel SDK client, providing methods for user lookup, creation, and modification while respecting a dry_run flag.
- **UserProcessEnvironment**: An environment object that aggregates services (FlywheelProxy, UserRegistry, NotificationClient, NACCGroup, AuthMap) used by user process classes.
- **UserEventCollector**: A collector that accumulates UserProcessEvent objects (successes and errors) during gear execution for downstream reporting and CSV export.
- **Flywheel_User**: A user account on the Flywheel platform, identified by a user ID and email address.
- **Dry_Run_Mode**: A mode in which FlywheelProxy logs intended actions without executing them against the Flywheel API.
- **EventCategory**: An enumeration of event categories used to classify UserProcessEvent objects for reporting.

## Requirements

### Requirement 1: Disable Flywheel Users for Inactive Directory Entries

**User Story:** As a system administrator, I want inactive directory entries to result in their matching Flywheel users being disabled, so that users who are no longer active in the NACC directory cannot access the platform.

#### Acceptance Criteria

1. WHEN a UserEntry with active=False is processed, THE InactiveUserProcess SHALL look up all Flywheel_User accounts matching the entry's email address.
2. WHEN one or more matching Flywheel_User accounts are found for an inactive entry, THE InactiveUserProcess SHALL disable each matching Flywheel_User by calling FlywheelProxy with disabled=True and clear_permissions=True.
3. WHEN a matching Flywheel_User is successfully disabled, THE InactiveUserProcess SHALL log the disable action including the user ID and email address.
4. WHEN no matching Flywheel_User accounts are found for an inactive entry, THE InactiveUserProcess SHALL log that no matching users were found and take no further action.

### Requirement 2: Provide Environment Access to InactiveUserProcess

**User Story:** As a developer, I want InactiveUserProcess to have access to UserProcessEnvironment, so that it can use FlywheelProxy to disable users.

#### Acceptance Criteria

1. THE InactiveUserProcess SHALL accept a UserProcessEnvironment parameter in addition to the existing UserEventCollector parameter.
2. THE InactiveUserProcess SHALL use the FlywheelProxy from the UserProcessEnvironment to look up and disable Flywheel users.
3. WHEN the UserProcess class instantiates InactiveUserProcess, THE UserProcess SHALL pass the UserProcessEnvironment to InactiveUserProcess.

### Requirement 3: Add Email-Based User Lookup to FlywheelProxy

**User Story:** As a developer, I want FlywheelProxy to support looking up Flywheel users by email address, so that InactiveUserProcess can find users to disable.

#### Acceptance Criteria

1. THE FlywheelProxy SHALL provide a find_user_by_email method that accepts an email address string and returns a list of matching Flywheel_User objects.
2. WHEN no Flywheel_User accounts match the provided email address, THE FlywheelProxy find_user_by_email method SHALL return an empty list.
3. WHILE Dry_Run_Mode is enabled, THE FlywheelProxy find_user_by_email method SHALL execute the lookup and return results without modification, since lookups are read-only operations.

### Requirement 4: Add User Disable Method to FlywheelProxy

**User Story:** As a developer, I want FlywheelProxy to provide a method to disable a Flywheel user, so that the disable logic is encapsulated and respects the dry_run flag.

#### Acceptance Criteria

1. THE FlywheelProxy SHALL provide a disable_user method that accepts a Flywheel_User object and calls the Flywheel SDK modify_user with the user's ID, a body of {"disabled": True}, and clear_permissions=True.
2. WHILE Dry_Run_Mode is enabled, THE FlywheelProxy disable_user method SHALL log the intended disable action and skip the actual API call.
3. IF the Flywheel SDK modify_user call fails with an API error, THEN THE FlywheelProxy disable_user method SHALL raise a FlywheelError with a descriptive message.

### Requirement 5: Update Flywheel Client Type Stub

**User Story:** As a developer, I want the mypy type stub for the Flywheel Client.modify_user method to accept boolean values in the body dictionary and the clear_permissions parameter, so that the disable_user implementation passes type checking.

#### Acceptance Criteria

1. THE modify_user signature in the Flywheel Client type stub SHALL accept a body parameter of type Dict[str, str | bool].
2. THE modify_user signature in the Flywheel Client type stub SHALL accept an optional clear_permissions parameter of type bool with a default value of False.

### Requirement 6: Capture Disable Events via UserEventCollector

**User Story:** As a system administrator, I want disable actions to be captured as events, so that they appear in the gear's output reporting alongside other user processing events.

#### Acceptance Criteria

1. WHEN a Flywheel_User is successfully disabled, THE InactiveUserProcess SHALL collect a success event through the UserEventCollector with a category indicating the user was disabled.
2. THE EventCategory enumeration SHALL include a category for user disable events.
3. IF a Flywheel_User disable operation fails, THEN THE InactiveUserProcess SHALL collect an error event through the UserEventCollector with a descriptive error message.
4. THE disable events collected by the UserEventCollector SHALL include the user's email address, name, and center ID when available in the UserContext.

### Requirement 7: Preserve Existing Inactive Entry Logging

**User Story:** As a developer, I want the existing log output for inactive entries to be preserved, so that operational logs remain consistent.

#### Acceptance Criteria

1. WHEN an inactive UserEntry is processed, THE InactiveUserProcess SHALL log that it is processing the inactive entry before attempting to disable matching Flywheel users.
