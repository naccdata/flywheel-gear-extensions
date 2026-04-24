# Requirements Document

## Introduction

The user management gear's `InactiveUserProcess` currently disables users in Flywheel and suspends them in COmanage when they are marked inactive in the directory. However, it does not touch REDCap. Users who have been granted role-based access to REDCap projects retain those permissions after being disabled elsewhere. This feature adds REDCap user role removal as a third step in the inactive user disable flow, and sends a notification email to REDCap administrators flagging the user for manual account suspension (which is not available via the REDCap API).

## Glossary

- **InactiveUserProcess**: The user process class responsible for handling user entries marked inactive in the directory. Currently disables Flywheel users and suspends COmanage registry persons.
- **REDCapProject**: A class in the `redcap_api` library representing a REDCap project, providing methods for user-role assignment, record import/export, and role management.
- **REDCapParametersRepository**: A repository holding API credentials (keyed by PID) for REDCap projects, used to obtain `REDCapProject` instances.
- **NACCGroup**: A singleton class representing the NACC admin group, holding center information and the `REDCapParametersRepository`.
- **CenterGroup**: An adaptor for a Flywheel group representing a research center, providing access to center metadata and REDCap project connections.
- **CenterMetadata**: Metadata stored in a center's metadata project, containing study information and associated ingest projects.
- **FormIngestProjectMetadata**: Metadata for a form ingest project within a center, containing references to associated REDCap projects via `redcap_projects`.
- **REDCapFormProjectMetadata**: Metadata for a specific REDCap form project, including the `redcap_pid` used to retrieve the `REDCapProject` from the repository.
- **UserProcessEnvironment**: An environment object aggregating services (FlywheelProxy, UserRegistry, NotificationClient, NACCGroup, AuthMap) used by user process classes.
- **UserEventCollector**: A collector that accumulates `UserProcessEvent` objects (successes and errors) during gear execution for downstream reporting and CSV export.
- **EventCategory**: An enumeration of event categories used to classify `UserProcessEvent` objects for reporting.
- **EmailClient**: A wrapper for the boto3 SES client used to send notification emails.
- **UserRegistry**: A wrapper for the COmanage registry API, providing methods to look up, add, suspend, and re-enable registry persons.
- **RegistryPerson**: A data model representing a person record in the COmanage registry, including email addresses and authentication identifiers.
- **Auth_Email**: The authentication email address from the COmanage registry, used as the REDCap username when granting project access.
- **Directory_Email**: The email address from the NACC directory entry, which may differ from the auth_email.
- **Role_Unassignment**: The act of removing a user's role-based permissions in a REDCap project by calling `assign_user_role(username, "")`, which passes an empty `unique_role_name`.
- **Dry_Run_Mode**: A mode in which operations are logged but not executed against external APIs.

## Requirements

### Requirement 1: Provide Local Wrapper for REDCap Role Unassignment

**User Story:** As a developer, I want a local helper function that unassigns a user from their role in a REDCap project, so that the disable flow can remove REDCap permissions using a clear, intention-revealing API without modifying the external `redcap_api` library.

#### Acceptance Criteria

1. THE codebase SHALL provide a local helper function (not in the `redcap_api` library) that accepts a REDCapProject instance and a username string, and calls `REDCapProject.assign_user_role` with the username and an empty string for the role to perform Role_Unassignment.
2. WHEN the helper function is called, THE helper function SHALL return the number of user-role assignments updated.
3. IF the underlying `assign_user_role` call raises a REDCapConnectionError, THEN THE helper function SHALL propagate the error to the caller.

### Requirement 2: Resolve REDCap Username from Directory Entry

**User Story:** As a developer, I want the disable flow to determine the correct REDCap username for an inactive user, so that role unassignment targets the correct account in each REDCap project.

#### Acceptance Criteria

1. WHEN an inactive user entry is processed for REDCap role removal, THE InactiveUserProcess SHALL look up the user in the COmanage registry using the directory email to obtain the auth_email.
2. WHEN a matching COmanage registry person is found with an auth_email, THE InactiveUserProcess SHALL use the auth_email as the REDCap username for role unassignment.
3. WHEN no matching COmanage registry person is found, THE InactiveUserProcess SHALL fall back to using the directory email as the REDCap username.
4. WHEN the user entry already contains an auth_email field, THE InactiveUserProcess SHALL use the auth_email from the entry without an additional registry lookup.

### Requirement 3: Remove REDCap Roles When a User Is Disabled

**User Story:** As a system administrator, I want inactive users to have their role assignments removed from all REDCap projects they may have access to, so that disabled users lose REDCap permissions as part of the standard disable flow.

#### Acceptance Criteria

1. WHEN an inactive user entry is processed, THE InactiveUserProcess SHALL iterate over all centers in the NACCGroup and examine each center's CenterMetadata for form ingest projects that have associated REDCap projects (via `FormIngestProjectMetadata.redcap_projects`).
2. WHEN a center's metadata contains no form ingest projects or no REDCap project references, THE InactiveUserProcess SHALL skip that center without error.
3. WHEN a REDCap project is found in a center's form ingest metadata, THE InactiveUserProcess SHALL attempt to unassign the user's role in that REDCap project using the resolved REDCap username.
4. WHEN a REDCap project's API credentials are unavailable in the REDCapParametersRepository, THE InactiveUserProcess SHALL log the error and continue processing remaining projects.
5. IF a role unassignment call fails for a specific REDCap project, THEN THE InactiveUserProcess SHALL log the error, collect an error event, and continue processing remaining REDCap projects.
6. THE REDCap role removal step SHALL be independent of the Flywheel disable and COmanage suspend steps; failure of any one step SHALL NOT prevent the other steps from executing.
7. WHILE Dry_Run_Mode is enabled, THE InactiveUserProcess SHALL log the intended REDCap role unassignment actions and skip the actual API calls.

### Requirement 4: Add Event Tracking for REDCap Disable Actions

**User Story:** As a system administrator, I want REDCap disable actions to be tracked as distinct events, so that they appear separately from Flywheel disable events in reporting and error CSV output.

#### Acceptance Criteria

1. THE EventCategory enumeration SHALL include a `REDCAP_USER_DISABLED` category with the display value "REDCap User Disabled".
2. WHEN a user's role is successfully unassigned from a REDCap project, THE InactiveUserProcess SHALL collect a success event through the UserEventCollector with the `REDCAP_USER_DISABLED` category, including the REDCap project title and PID in the message.
3. IF a REDCap role unassignment fails, THEN THE InactiveUserProcess SHALL collect an error event through the UserEventCollector with the `REDCAP_USER_DISABLED` category, including the error details and REDCap project identifier in the message.
4. THE REDCap disable events collected by the UserEventCollector SHALL include the user's email address, name, and center ID in the UserContext when available.

### Requirement 5: Send Notification for Manual REDCap Suspension

**User Story:** As a REDCap administrator, I want to receive a notification email when a user's REDCap roles have been removed, so that I can manually suspend the user's REDCap account (which cannot be done via the API).

#### Acceptance Criteria

1. WHEN one or more REDCap role unassignments are completed for an inactive user, THE InactiveUserProcess SHALL send a notification email to the configured support email addresses (the same addresses already stored in AWS SSM Parameter Store and used for error notifications in user management).
2. THE notification email SHALL include the user's directory email, the resolved REDCap username, and a list of REDCap projects from which roles were removed (including project title and PID).
3. THE notification email subject SHALL be "[REDCap] inactive users to suspend".
4. THE notification email SHALL be sent using the existing EmailClient infrastructure with the `send_raw` method.
5. IF no REDCap role unassignments were performed for the user (no REDCap projects found or all attempts failed), THEN THE InactiveUserProcess SHALL NOT send a REDCap suspension notification for that user.
6. IF the notification email fails to send, THEN THE InactiveUserProcess SHALL log the error and continue processing remaining users without raising an exception.

### Requirement 6: Provide REDCap Access to InactiveUserProcess

**User Story:** As a developer, I want `InactiveUserProcess` to have access to the NACCGroup and its REDCap infrastructure, so that it can iterate over centers and their REDCap projects during the disable flow.

#### Acceptance Criteria

1. THE InactiveUserProcess SHALL access the NACCGroup through the existing UserProcessEnvironment to retrieve center groups and their associated REDCap projects.
2. THE InactiveUserProcess SHALL access the support email addresses (already stored in AWS SSM Parameter Store for error notifications) through the UserProcessEnvironment or a parameter passed at construction.
3. THE UserProcessEnvironment SHALL provide access to the email source address and EmailClient needed for sending REDCap suspension notifications, reusing the same email infrastructure already configured for error notifications in the user management gear.

### Requirement 7: Support Best-Effort REDCap Role Removal

**User Story:** As a system administrator, I want the REDCap disable step to operate on a best-effort basis, so that failures in individual REDCap projects do not prevent role removal from other projects or block the overall disable flow.

#### Acceptance Criteria

1. WHEN iterating over REDCap projects for role removal, THE InactiveUserProcess SHALL process each project independently, catching and logging errors for each project.
2. IF a CenterGroup cannot be retrieved for a given ADCID, THEN THE InactiveUserProcess SHALL log the error and continue with the next center.
3. IF center metadata cannot be parsed or contains no form ingest projects, THEN THE InactiveUserProcess SHALL log the condition and continue with the next center.
4. THE InactiveUserProcess SHALL collect a summary of all REDCap projects where role removal succeeded and where it failed, for use in the notification email and event reporting.
