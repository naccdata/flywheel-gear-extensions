# Requirements Document

## Introduction

When a user is marked inactive in the NACC directory, the system currently disables them in Flywheel via `InactiveUserProcess`. This feature extends the inactive user workflow to also suspend the user in the COmanage registry, revoking downstream OIDC authorization. It also adds re-enablement logic so that a previously suspended user who becomes active again is restored in COmanage rather than duplicated. All new COmanage operations respect the existing dry-run mode.

## Glossary

- **User_Registry**: The `UserRegistry` class that interfaces with the COmanage Core API to manage CO Person records. Currently supports `add` and `get` operations.
- **Registry_Person**: The `RegistryPerson` wrapper around a `CoPersonMessage` that provides convenient access to CO Person attributes such as email, name, identifiers, and status.
- **Inactive_User_Process**: The `InactiveUserProcess` class that processes user entries marked inactive in the NACC directory. Currently disables users in Flywheel only.
- **Active_User_Process**: The `ActiveUserProcess` class that processes active user entries, adding new users to the registry or routing them to claimed/unclaimed queues.
- **COmanage_API**: The COmanage Core API accessed via the generated `DefaultApi` SDK client. Supports GET and PUT operations on CO Person records. The PUT endpoint requires the full `CoPersonMessage` (not patch semantics).
- **CoPersonMessage**: The full JSON document representing a CO Person and all related models (Name, EmailAddress, CoPersonRole, Identifier, OrgIdentity, etc.). Omitting related models in a PUT causes the API to delete them.
- **Suspended_Status**: CO Person status value `"S"` which removes the user from the `CO:members:active` group, revoking OIDC authorization. Reversible by setting status back to `"A"`.
- **Active_Status**: CO Person status value `"A"` indicating the CO Person is active and authorized.
- **Flywheel_Proxy**: The `FlywheelProxy` class that wraps Flywheel SDK calls and supports dry-run mode for all write operations.
- **Dry_Run_Mode**: A mode where write operations are logged but not executed against external services. The Flywheel_Proxy already supports this via its `dry_run` property.
- **Event_Collector**: The `UserEventCollector` that accumulates `UserProcessEvent` objects categorized by `EventCategory` during gear execution.

## Requirements

### Requirement 1: Suspend a CO Person in COmanage

**User Story:** As a system administrator, I want the User_Registry to support suspending a CO Person record via the COmanage_API, so that inactive users lose OIDC authorization.

#### Acceptance Criteria

1. WHEN a suspend operation is requested for a Registry_Person with a valid registry ID, THE User_Registry SHALL retrieve the full CoPersonMessage from the COmanage_API, set the CoPerson status to Suspended_Status, and submit the entire modified CoPersonMessage back via the PUT endpoint.
2. THE User_Registry SHALL preserve all related models (Name, EmailAddress, CoPersonRole, Identifier, OrgIdentity) unchanged when submitting the updated CoPersonMessage.
3. IF the COmanage_API returns an error during the suspend operation, THEN THE User_Registry SHALL raise a RegistryError with a descriptive message including the API error details.
4. IF the Registry_Person has no registry ID, THEN THE User_Registry SHALL raise a RegistryError indicating the person cannot be identified for update.

### Requirement 2: Re-enable a CO Person in COmanage

**User Story:** As a system administrator, I want the User_Registry to support re-enabling a suspended CO Person record, so that users who become active again regain OIDC authorization.

#### Acceptance Criteria

1. WHEN a re-enable operation is requested for a Registry_Person with Suspended_Status, THE User_Registry SHALL retrieve the full CoPersonMessage from the COmanage_API, set the CoPerson status to Active_Status, and submit the entire modified CoPersonMessage back via the PUT endpoint.
2. THE User_Registry SHALL preserve all related models unchanged when submitting the updated CoPersonMessage for re-enablement.
3. IF the COmanage_API returns an error during the re-enable operation, THEN THE User_Registry SHALL raise a RegistryError with a descriptive message including the API error details.

### Requirement 3: Inactive User Process Suspends in COmanage

**User Story:** As a system administrator, I want the Inactive_User_Process to suspend users in COmanage after disabling them in Flywheel, so that inactive users are fully deauthorized across both services.

#### Acceptance Criteria

1. WHEN processing an inactive user entry, THE Inactive_User_Process SHALL first disable the user in Flywheel, then suspend the user in COmanage.
2. THE Inactive_User_Process SHALL look up the user in COmanage by email to find matching Registry_Person records.
3. IF the Flywheel disable operation fails, THEN THE Inactive_User_Process SHALL still attempt to suspend the user in COmanage.
4. IF the COmanage suspend operation fails, THEN THE Inactive_User_Process SHALL log the error and collect an error event without affecting the Flywheel disable result.
5. IF no matching Registry_Person is found in COmanage for the user email, THEN THE Inactive_User_Process SHALL log that no COmanage record was found and continue without error.
6. WHEN a user is successfully suspended in COmanage, THE Inactive_User_Process SHALL collect a success event with EventCategory USER_DISABLED and a message distinguishing the COmanage suspension from the Flywheel disable.
7. IF the COmanage suspend operation fails, THEN THE Inactive_User_Process SHALL collect an error event with a message identifying the COmanage service and the error details.

### Requirement 4: Active User Process Re-enables Suspended Users

**User Story:** As a system administrator, I want the Active_User_Process to re-enable suspended COmanage users when they appear as active in the directory, so that returning users regain access without creating duplicate records.

#### Acceptance Criteria

1. WHEN processing an active user entry that matches a Registry_Person with Suspended_Status by email, THE Active_User_Process SHALL re-enable the Registry_Person by setting the status to Active_Status instead of creating a new registry record.
2. THE Active_User_Process SHALL only re-enable Registry_Person records matched by the same email address.
3. WHEN a user is successfully re-enabled in COmanage, THE Active_User_Process SHALL collect a success event indicating the user was re-enabled.
4. IF the re-enable operation fails, THEN THE Active_User_Process SHALL collect an error event with the failure details and continue processing.

### Requirement 5: Dry-Run Support for COmanage Operations

**User Story:** As a system administrator, I want COmanage suspend and re-enable operations to respect dry-run mode, so that I can preview changes without modifying COmanage records.

#### Acceptance Criteria

1. WHILE Dry_Run_Mode is enabled, THE User_Registry SHALL log the intended suspend action (including the registry ID and target status) without calling the COmanage_API PUT endpoint.
2. WHILE Dry_Run_Mode is enabled, THE User_Registry SHALL log the intended re-enable action (including the registry ID and target status) without calling the COmanage_API PUT endpoint.
3. WHILE Dry_Run_Mode is enabled, THE User_Registry SHALL still perform read operations (GET) against the COmanage_API to validate that the target record exists.

### Requirement 6: Full Record Integrity on Update

**User Story:** As a system administrator, I want the COmanage update operations to always send the complete CoPersonMessage, so that related models are never accidentally deleted by the API.

#### Acceptance Criteria

1. THE User_Registry SHALL retrieve the full CoPersonMessage via GET before any status update operation.
2. THE User_Registry SHALL modify only the CoPerson status field on the retrieved CoPersonMessage.
3. THE User_Registry SHALL submit the complete CoPersonMessage (including all related models returned by GET) in the PUT request.
4. FOR ALL valid CoPersonMessage objects retrieved from the COmanage_API, retrieving the record, modifying only the status field, and submitting the full record back SHALL preserve all non-status fields and related models (round-trip property).
