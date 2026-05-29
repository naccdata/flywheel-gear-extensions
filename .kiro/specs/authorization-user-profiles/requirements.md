# Requirements Document

## Introduction

The NACC Authorization API now provides user profile CRUD endpoints for managing user profile records. The existing user management processes (user management gear and authorization sync service) need to push user entry information as user profiles to these new endpoints whenever user entries are processed. This enables the authorization system to maintain a complete view of user identity alongside their permissions.

## Glossary

- **Authorization_Client**: The `AuthorizationClient` class that wraps HTTP calls to the NACC Authorization API.
- **Authorization_Sync_Service**: The service that orchestrates synchronization of user data with the Authorization API during user processing.
- **User_Entry**: A model representing a user in the NACC directory, containing name, email, auth_email, active status, and registry person information.
- **User_Profile**: A record in the Authorization API containing userId, firstName, lastName, email, authEmail, and active status.
- **Profile_User_ID**: The user identifier for profile endpoints, in the format `RegistryNNNNNN@naccdata.org` (the registry_id from COmanage).
- **User_Process**: The processing logic that manages user entries, including creating Flywheel users, syncing authorizations, and sending notifications.
- **Event_Collector**: The mechanism for reporting processing outcomes (successes and errors) without propagating exceptions.
- **UserProfileRequest**: The request body for creating or updating a user profile, containing firstName, lastName, email, authEmail, and active fields.

## Requirements

### Requirement 1: Authorization Client User Profile Methods

**User Story:** As a developer, I want the Authorization Client to support user profile CRUD operations, so that other services can push and retrieve user profile data through a consistent client interface.

#### Acceptance Criteria

1. THE Authorization_Client SHALL provide a `put_user_profile` method that accepts a Profile_User_ID and a UserProfileRequest and sends a PUT request to `/users/{profileUserId}`
2. THE Authorization_Client SHALL provide a `get_user_profile` method that accepts a Profile_User_ID and sends a GET request to `/users/{profileUserId}`
3. THE Authorization_Client SHALL provide a `delete_user_profile` method that accepts a Profile_User_ID and sends a DELETE request to `/users/{profileUserId}`
4. THE Authorization_Client SHALL provide a `get_user_profiles` method that accepts a list of Profile_User_IDs and sends a GET request to `/users?ids=...` with the IDs joined as a comma-separated query parameter
5. WHEN the `put_user_profile` method receives a 200 response, THE Authorization_Client SHALL return a parsed UserProfile model
6. WHEN the `put_user_profile` method receives a 400 response, THE Authorization_Client SHALL raise a ValidationError with the error message from the response
7. WHEN the `get_user_profile` method receives a 404 response, THE Authorization_Client SHALL raise a NotFoundError indicating the requested Profile_User_ID was not found
8. WHEN the `delete_user_profile` method receives a 204 response, THE Authorization_Client SHALL return None
9. WHEN the `delete_user_profile` method receives a 404 response, THE Authorization_Client SHALL return None without raising an exception
10. THE Authorization_Client SHALL apply the same retry-on-503 strategy to user profile methods as used by existing methods, using the configured max_retries and base_backoff parameters with exponential backoff
11. WHEN the `get_user_profile` method receives a 200 response, THE Authorization_Client SHALL return a parsed UserProfile model
12. IF any user profile method receives an unexpected HTTP status code not explicitly handled, THEN THE Authorization_Client SHALL raise an UnexpectedError containing the status code and error message from the response
13. WHEN the `get_user_profiles` method receives a 200 response, THE Authorization_Client SHALL return a list of parsed UserProfile models

### Requirement 2: User Profile Data Models

**User Story:** As a developer, I want Pydantic models for user profile requests and responses, so that profile data is validated and serialized consistently.

#### Acceptance Criteria

1. THE Authorization_Client module SHALL define a `UserProfileRequest` model with fields: firstName (str, 1-256 chars, must contain at least one non-whitespace character), lastName (str, 1-256 chars, must contain at least one non-whitespace character), email (str or None, email format, 1-256 chars, default None), authEmail (str, email format, 1-256 chars), and active (bool or None, default None)
2. THE Authorization_Client module SHALL define a `UserProfile` response model with fields: userId (str), firstName (str), lastName (str), email (str or None), authEmail (str), and active (bool)
3. THE UserProfileRequest model SHALL serialize field names using camelCase aliases matching the API schema (firstName, lastName, authEmail) and support field access by both Python snake_case names and camelCase aliases (populate_by_name)
4. THE UserProfile model SHALL deserialize field names from camelCase aliases matching the API schema and support field access by both Python snake_case names and camelCase aliases (populate_by_name)
5. IF a UserProfileRequest is constructed with a firstName or lastName that is empty or exceeds 256 characters, THEN THE Authorization_Client module SHALL raise a validation error indicating the field length constraint

### Requirement 3: Profile Sync During User Processing

**User Story:** As a system operator, I want user profiles to be pushed to the Authorization API whenever user entries are processed, so that the authorization system has up-to-date user identity information.

#### Acceptance Criteria

1. WHEN a registered active user entry is processed by the User_Process, THE Authorization_Sync_Service SHALL push a user profile to the Authorization API using the PUT endpoint
2. THE Authorization_Sync_Service SHALL construct the Profile_User_ID from the user entry's registry_id
3. THE Authorization_Sync_Service SHALL map user entry fields to UserProfileRequest fields as follows: name.first_name to firstName, name.last_name to lastName, email to email, auth_email to authEmail, active to active
4. IF a user entry has a null auth_email, THEN THE Authorization_Sync_Service SHALL skip the profile sync for that entry and log a warning message indicating the user's email and the reason the sync was skipped
5. IF profile sync fails with an AuthorizationClientError, THEN THE Authorization_Sync_Service SHALL report the failure via the Event_Collector as an error event with the AUTHORIZATION_SYNC category and continue processing without raising the exception
6. THE Authorization_Sync_Service SHALL execute profile sync independently of grant sync such that an exception in either operation does not prevent the other from executing

### Requirement 4: Profile Sync for Inactive Users

**User Story:** As a system operator, I want inactive user profiles to be updated in the Authorization API when users are deactivated, so that the authorization system reflects the current active status.

#### Acceptance Criteria

1. WHEN an inactive user entry is processed and the user has a non-null registry_id, THE User_Process SHALL push a profile update to the Authorization API using the PUT endpoint with active set to false and identity fields mapped per Requirement 3 criterion 3
2. IF an inactive user entry has a null registry_id, THEN THE User_Process SHALL skip the profile sync for that entry
3. IF the profile update for an inactive user raises an AuthorizationClientError, THEN THE User_Process SHALL report the failure via the Event_Collector and continue with the remaining deactivation steps (Flywheel disable, COmanage lookup, REDCap role removal, COmanage suspend)
4. THE User_Process SHALL execute profile sync for inactive users independently of other deactivation steps so that failure of one does not block the other

### Requirement 5: Profile User ID Validation

**User Story:** As a developer, I want the Profile User ID to be validated before sending requests, so that invalid IDs are caught early rather than rejected by the API.

#### Acceptance Criteria

1. THE Authorization_Client SHALL validate that the Profile_User_ID matches the pattern `^Registry\d{6}@naccdata\.org$` before sending any profile request
2. IF the Profile_User_ID does not match the expected pattern, THEN THE Authorization_Client SHALL raise a ValidationError with a message indicating the invalid value provided and the expected format
3. IF the Profile_User_ID is None or an empty string, THEN THE Authorization_Client SHALL raise a ValidationError with a message indicating that a non-empty Profile_User_ID is required
4. WHEN the `get_user_profiles` method is called with a list of Profile_User_IDs, THE Authorization_Client SHALL validate each ID in the list against the expected pattern before sending the request

### Requirement 6: Idempotent Profile Sync

**User Story:** As a system operator, I want profile sync to be idempotent, so that reprocessing user entries does not cause errors or inconsistent state.

#### Acceptance Criteria

1. THE Authorization_Sync_Service SHALL use the PUT endpoint for profile sync, which creates the profile if it does not exist or updates it if it already exists
2. WHEN the same user entry is processed multiple times with the same data, THE Authorization_Sync_Service SHALL send the same UserProfileRequest to the PUT endpoint each time, and the resulting UserProfile state in the Authorization API SHALL match the field mapping defined in Requirement 3 criterion 3
3. WHEN a user entry is reprocessed and the profile already exists in the Authorization API, THE Authorization_Sync_Service SHALL complete without raising exceptions or reporting errors via the Event_Collector
