# Requirements Document

## Introduction

The pull-directory gear retrieves user records from the NACC REDCap directory and converts them to a YAML file consumed by the user management gear. Currently, the gear filters out records where `permissions_approval` or `signed_agreement_status_num_ct` are falsey at three points: `filter_approved_records` pre-filters on `permissions_approval`, the `run()` function skips records missing either flag, and `to_user_entry()` returns `None` for records missing either flag. This means archived contacts (`archive_contact='1'`) that lack permissions approval or a signed user agreement are silently dropped and never appear in the output YAML.

The `to_user_entry()` method in `DirectoryAuthorizations` already handles the archived case correctly: when `inactive` is `True`, it returns a `UserEntry` with `active=False`. However, the upstream filters prevent archived contacts from ever reaching that code path.

This feature modifies the filtering logic so that records with `archive_contact='1'` bypass the `permissions_approval` and `signed_agreement_status_num_ct` checks at all three filtering points, allowing them to pass through the pipeline and appear in the output YAML with `active: false`.

## Glossary

- **Pull_Directory_Gear**: The Flywheel gear (`gear/pull_directory`) that retrieves user permission data from the NACC Directory REDCap project and converts it to a YAML file consumed by the user management gear.
- **Filter_Approved_Records**: The function in `gear/pull_directory/src/python/directory_app/main.py` that pre-filters raw REDCap records to retain only those with `permissions_approval == '1'`. This is the first filtering point.
- **Run_Function**: The `run()` function in `gear/pull_directory/src/python/directory_app/main.py` that deserializes records into `DirectoryAuthorizations` objects and checks `permissions_approval` and `signed_user_agreement` before calling `to_user_entry()`. This is the second filtering point.
- **DirectoryAuthorizations**: The Pydantic model in `common/src/python/users/nacc_directory.py` that deserializes a REDCap directory record. Contains the `to_user_entry()` method, which is the third filtering point.
- **To_User_Entry**: The method on `DirectoryAuthorizations` that converts a directory record to a `UserEntry`. Currently returns `None` when `signed_user_agreement` or `permissions_approval` is `False`, and returns a `UserEntry` with `active=False` when `inactive` is `True`.
- **Archive_Contact**: A REDCap field (`archive_contact`) that indicates a contact has been archived. A value of `'1'` means the contact is archived. Mapped to the `inactive` field on `DirectoryAuthorizations`.
- **UserEntry**: A Pydantic model representing a user in the output YAML. Contains an `active` field that controls whether the user is treated as active or inactive by the user management gear.
- **UserEventCollector**: An event collector that tracks processing errors and warnings during the directory pull, used for error reporting and notifications.

## Requirements

### Requirement 1: Allow Archived Contacts Through Pre-Filter

**User Story:** As a platform administrator, I want archived contacts to pass through the initial record filter, so that they are not silently dropped before processing.

#### Acceptance Criteria

1. WHEN a raw REDCap record has `archive_contact` equal to `'1'`, THE Filter_Approved_Records function SHALL retain the record regardless of the value of `permissions_approval`.
2. WHEN a raw REDCap record has `archive_contact` not equal to `'1'`, THE Filter_Approved_Records function SHALL retain the record only when `permissions_approval` equals `'1'`.

### Requirement 2: Allow Archived Contacts Through Run Function Checks

**User Story:** As a platform administrator, I want archived contacts to bypass the permissions and agreement checks in the run function, so that they proceed to user entry conversion.

#### Acceptance Criteria

1. WHEN a deserialized `DirectoryAuthorizations` record has `inactive` equal to `True`, THE Run_Function SHALL skip the `permissions_approval` check and proceed to user entry conversion.
2. WHEN a deserialized `DirectoryAuthorizations` record has `inactive` equal to `True`, THE Run_Function SHALL skip the `signed_user_agreement` check and proceed to user entry conversion.
3. WHEN a deserialized `DirectoryAuthorizations` record has `inactive` equal to `False` and `permissions_approval` equal to `False`, THE Run_Function SHALL skip the record and log a warning.
4. WHEN a deserialized `DirectoryAuthorizations` record has `inactive` equal to `False` and `signed_user_agreement` equal to `False`, THE Run_Function SHALL skip the record and log a warning.

### Requirement 3: Allow Archived Contacts Through User Entry Conversion

**User Story:** As a platform administrator, I want archived contacts to produce a user entry with `active: false`, so that the user management gear can process them as inactive users.

#### Acceptance Criteria

1. WHEN `inactive` is `True`, THE To_User_Entry method SHALL return a `UserEntry` with `active` set to `False`, regardless of the values of `signed_user_agreement` and `permissions_approval`.
2. WHEN `inactive` is `False` and `signed_user_agreement` is `False`, THE To_User_Entry method SHALL return `None`.
3. WHEN `inactive` is `False` and `permissions_approval` is `False`, THE To_User_Entry method SHALL return `None`.
4. WHEN `inactive` is `False`, `signed_user_agreement` is `True`, and `permissions_approval` is `True`, THE To_User_Entry method SHALL return a `UserEntry` with `active` set to `True`.

### Requirement 4: Preserve Existing Behavior for Non-Archived Contacts

**User Story:** As a platform administrator, I want the filtering behavior for non-archived contacts to remain unchanged, so that existing user processing continues to work correctly.

#### Acceptance Criteria

1. WHEN a record has `archive_contact` not equal to `'1'` and `permissions_approval` not equal to `'1'`, THE Pull_Directory_Gear SHALL exclude the record from the output YAML.
2. WHEN a record has `archive_contact` not equal to `'1'` and `signed_agreement_status_num_ct` is falsey, THE Pull_Directory_Gear SHALL exclude the record from the output YAML.
3. THE Pull_Directory_Gear SHALL produce the same YAML output format for non-archived contacts as the current implementation.

### Requirement 5: Archived Contact Output Format

**User Story:** As a platform administrator, I want archived contacts to appear in the output YAML with the correct structure, so that the user management gear can identify and handle them.

#### Acceptance Criteria

1. WHEN an archived contact passes through the pipeline, THE Pull_Directory_Gear SHALL include the contact in the output YAML with `active` set to `false`.
2. WHEN an archived contact passes through the pipeline, THE Pull_Directory_Gear SHALL include the contact's `name`, `email`, and `auth_email` fields in the output YAML entry.
3. WHEN an archived contact passes through the pipeline, THE Pull_Directory_Gear SHALL set `approved` to the value of the contact's `permissions_approval` field in the output YAML entry.
