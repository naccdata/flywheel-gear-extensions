# Implementation Plan: Authorization User Profiles

## Overview

Implement user profile CRUD operations in the authorization client library and integrate profile sync into the user processing pipeline. The implementation follows the existing patterns: Pydantic models with camelCase aliases, `retry_on_503` wrapping, error classification, and fault-isolated error reporting via `UserEventCollector`.

## Tasks

- [x] 1. Add NotFoundError exception and UserProfile models
  - [x] 1.1 Add `NotFoundError` to `common/src/python/authorization/exceptions.py`
    - Add `NotFoundError(AuthorizationClientError)` with a `message` attribute
    - Follows the same pattern as `ValidationError` and `UnexpectedError`
    - _Requirements: 1.7_

  - [x] 1.2 Add `UserProfileRequest`, `UserProfile`, and `UserProfileList` models to `common/src/python/authorization/models.py`
    - `UserProfileRequest` with fields: first_name (alias firstName, 1-256 chars, non-whitespace validator), last_name (alias lastName, 1-256 chars, non-whitespace validator), email (alias email, optional), auth_email (alias authEmail, 1-256 chars), active (optional bool)
    - `UserProfile` with fields: user_id (alias userId), first_name (alias firstName), last_name (alias lastName), email (optional), auth_email (alias authEmail), active (bool)
    - `UserProfileList` with field: users (list[UserProfile])
    - All models use `ConfigDict(populate_by_name=True)`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 1.3 Write property test for UserProfileRequest serialization round-trip
    - **Property 3: UserProfileRequest serialization round-trip**
    - Generate valid UserProfileRequest inputs with Hypothesis, serialize with `model_dump_json(by_alias=True)`, deserialize back, assert equivalence
    - **Validates: Requirements 2.1, 2.3**

  - [x]* 1.4 Write property test for UserProfile response parsing round-trip
    - **Property 2: UserProfile response parsing round-trip**
    - Generate valid UserProfile JSON data with camelCase keys, parse via `model_validate_json`, assert fields match original data
    - **Validates: Requirements 1.5, 1.11, 1.13, 2.2, 2.4**

  - [x]* 1.5 Write property test for name field validation
    - **Property 5: Name field validation rejects invalid inputs**
    - Generate empty strings, whitespace-only strings, and strings >256 chars; assert Pydantic validation error on UserProfileRequest construction
    - **Validates: Requirements 2.5**

- [x] 2. Implement Profile_User_ID validation and client profile methods
  - [x] 2.1 Add `_validate_profile_user_id` method and `_PROFILE_USER_ID_PATTERN` to `common/src/python/authorization/client.py`
    - Compile regex `^Registry\d{6}@naccdata\.org$`
    - Raise `ValidationError` if ID is None, empty, or doesn't match pattern
    - Import `re` module at top of file
    - _Requirements: 5.1, 5.2, 5.3_

  - [x]* 2.2 Write property test for Profile_User_ID validation
    - **Property 4: Profile_User_ID validation**
    - Generate random strings (both matching and non-matching the pattern), assert validation accepts/rejects correctly
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x] 2.3 Implement `put_user_profile` method on `AuthorizationClient`
    - Validate profile_user_id, serialize UserProfileRequest body, PUT to `/users/{profileUserId}`
    - Handle 200 (parse and return UserProfile), 400 (raise ValidationError), other (raise UnexpectedError)
    - Wrap transport call in `retry_on_503`
    - Import `UserProfileRequest`, `UserProfile` from models; import `NotFoundError` from exceptions
    - _Requirements: 1.1, 1.5, 1.6, 1.10, 1.12_

  - [x] 2.4 Implement `get_user_profile` method on `AuthorizationClient`
    - Validate profile_user_id, GET `/users/{profileUserId}`
    - Handle 200 (parse and return UserProfile), 404 (raise NotFoundError), 400 (raise ValidationError), other (raise UnexpectedError)
    - Wrap transport call in `retry_on_503`
    - _Requirements: 1.2, 1.7, 1.11, 1.10, 1.12_

  - [x] 2.5 Implement `delete_user_profile` method on `AuthorizationClient`
    - Validate profile_user_id, DELETE `/users/{profileUserId}`
    - Handle 204 (return None), 404 (return None, idempotent), 400 (raise ValidationError), other (raise UnexpectedError)
    - Wrap transport call in `retry_on_503`
    - _Requirements: 1.3, 1.8, 1.9, 1.10, 1.12_

  - [x] 2.6 Implement `get_user_profiles` method on `AuthorizationClient`
    - Validate each profile_user_id in the list, GET `/users?ids=id1,id2,...`
    - Handle 200 (parse UserProfileList, return list of UserProfile), 400 (raise ValidationError), other (raise UnexpectedError)
    - Wrap transport call in `retry_on_503`
    - _Requirements: 1.4, 1.13, 5.4, 1.10, 1.12_

  - [x]* 2.7 Write property test for request routing correctness
    - **Property 1: Request routing correctness**
    - Generate valid Profile_User_IDs, call each method with a mock transport, assert correct HTTP method and path
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

  - [x]* 2.8 Write property test for unexpected status codes
    - **Property 7: Unexpected status codes raise UnexpectedError**
    - Generate random unexpected status codes (not in handled set), assert UnexpectedError raised with correct status code and message
    - **Validates: Requirements 1.12**

  - [x] 2.9 Write unit tests for client profile methods
    - Test `put_user_profile` returns parsed UserProfile on 200
    - Test `get_user_profile` raises NotFoundError on 404
    - Test `delete_user_profile` returns None on 204
    - Test `delete_user_profile` returns None on 404 (idempotent)
    - Test retry-on-503 integration (mock 503 then 200)
    - _Requirements: 1.5, 1.7, 1.8, 1.9, 1.10_

- [x] 3. Implement sync_profile on AuthorizationSyncService
  - [x] 3.1 Extend `AuthorizationClientProtocol` with `put_user_profile` method in `common/src/python/authorization_sync/sync_service.py`
    - Add `put_user_profile(self, profile_user_id: str, request: "UserProfileRequest") -> "UserProfile": ...` to the Protocol class
    - Add necessary imports for `UserProfileRequest` and `UserProfile` (use string annotations in Protocol)
    - _Requirements: 3.1_

  - [x] 3.2 Implement `sync_profile` method on `AuthorizationSyncService`
    - Accept `registry_id: str` and `user_entry: UserEntry` parameters
    - Skip sync if `user_entry.auth_email` is None (log warning with user email)
    - Construct `UserProfileRequest` mapping: name.first_name → firstName, name.last_name → lastName, email → email, auth_email → authEmail, active → active
    - Call `self._client.put_user_profile(registry_id, request)`
    - Catch `AuthorizationClientError` and report via event collector with `AUTHORIZATION_SYNC` category
    - Import `UserEntry` from `users.user_entry` and `UserProfileRequest`, `UserProfile` from `authorization.models`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.3 Write property test for field mapping correctness
    - **Property 6: Field mapping correctness**
    - Generate random user entries with non-null auth_email, call sync_profile with mock client, assert UserProfileRequest fields match the mapping
    - **Validates: Requirements 3.3, 6.2**

  - [x]* 3.4 Write property test for idempotent profile sync
    - **Property 8: Idempotent profile sync**
    - Generate random user entries, call sync_profile multiple times, assert same request sent each time
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 3.5 Write unit tests for sync_profile
    - Test sync_profile skips when auth_email is None and logs warning
    - Test sync_profile reports error via event collector on AuthorizationClientError
    - Test sync_profile completes without error when API returns 200
    - _Requirements: 3.4, 3.5, 6.3_

- [x] 4. Integrate profile sync into user processes
  - [x] 4.1 Add profile sync to `UpdateUserProcess.__authorize_user` in `common/src/python/users/user_processes.py`
    - After existing `sync_service.sync_user` call, add independent `sync_service.sync_profile(registry_id=registry_id, user_entry=entry)` call
    - Wrap in try/except catching `Exception` for fault isolation (matching existing pattern)
    - Log error on failure; do not propagate
    - Pass the `ActiveUserEntry` as the user_entry parameter (requires passing entry into `__authorize_user` or accessing it from context)
    - _Requirements: 3.1, 3.6, 6.1_

  - [x] 4.2 Add profile sync to `UpdateCenterUserProcess.__authorize_user` in `common/src/python/users/user_processes.py`
    - After existing `sync_service.sync_user` loop, add independent `sync_service.sync_profile(registry_id=registry_id, user_entry=entry)` call
    - Wrap in try/except catching `Exception` for fault isolation
    - Log error on failure; do not propagate
    - Pass the `CenterUserEntry` as the user_entry parameter (requires passing entry into `__authorize_user` or accessing it from context)
    - _Requirements: 3.1, 3.6, 6.1_

  - [x] 4.3 Add profile sync to `InactiveUserProcess.visit` in `common/src/python/users/user_processes.py`
    - Add a new independent step (Step 0 or after Step 2 when registry_id is resolved) for profile sync
    - Only attempt sync if registry_id is available (from person_list lookup)
    - Call `sync_service.sync_profile(registry_id=registry_id, user_entry=entry)` where entry.active is False
    - Wrap in try/except catching `Exception` for fault isolation
    - Log error on failure; continue with remaining deactivation steps
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.4 Write unit tests for profile sync integration in user processes
    - Test fault isolation: profile sync failure does not block grant sync
    - Test fault isolation: grant sync failure does not block profile sync
    - Test InactiveUserProcess continues remaining steps after profile sync failure
    - Test profile sync is skipped for inactive user with null registry_id
    - _Requirements: 3.6, 4.3, 4.4_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All property tests use Hypothesis with minimum 100 iterations
- Test files go in `common/test/python/authorization_test/` and `common/test/python/authorization_sync_test/` (existing directories with BUILD files)
- User process integration tests go in `common/test/python/user_test/`
- The `UserEntry` type used in `sync_profile` is the base class; both `ActiveUserEntry` and `CenterUserEntry` inherit from it and provide the needed fields

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["2.7", "2.8", "2.9"] },
    { "id": 5, "tasks": ["3.1"] },
    { "id": 6, "tasks": ["3.2"] },
    { "id": 7, "tasks": ["3.3", "3.4", "3.5"] },
    { "id": 8, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 9, "tasks": ["4.4"] }
  ]
}
```
