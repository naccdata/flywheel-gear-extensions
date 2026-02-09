# Implementation Tasks

## 1. Create CSV Export Function in Common Library

Create the reusable CSV export function that converts UserEventCollector errors to CSV format.

**Files to modify:**
- Create: `common/src/python/users/csv_export.py`
- Update: `common/src/python/users/BUILD` (add csv_export.py to sources)

**Implementation details:**
- Function signature: `export_errors_to_csv(collector: UserEventCollector) -> str`
- Use Python's `csv` module with `csv.DictWriter`
- Column order: email, name, center_id, registry_id, auth_email, category, message, action_needed, timestamp, event_id
- Set `quoting=csv.QUOTE_MINIMAL` and `lineterminator='\n'`
- Convert None values to empty strings
- Format timestamps using `.isoformat()`
- Extract category value using `category.value` from enum
- Raise ValueError if collector is empty or has no errors

**Acceptance criteria:**
- Function exports all error fields in correct order
- None/empty fields represented as empty strings
- Timestamps formatted in ISO 8601
- Category enums converted to human-readable strings
- Special characters (commas, quotes, newlines) handled correctly

### 1.1 Write unit tests for CSV export function

Create comprehensive unit tests for the CSV export function.

**Files to create:**
- `common/test/python/users/test_csv_export.py`

**Test cases:**
- Single error event export
- Multiple error events across categories
- None/empty optional fields (center_id, registry_id, auth_email, action_needed)
- Special characters in messages (commas, quotes, newlines)
- Empty collector (should raise ValueError)
- Timestamp formatting verification
- Category enum to string conversion
- CSV parsing round-trip (export then parse to verify format)

## 2. Update pull-directory Gear for CSV Export

Modify the pull-directory gear to export errors to CSV and send simple notifications.

**Files to modify:**
- `gear/pull_directory/src/python/directory_app/run.py`

**Implementation details:**
- Import `export_errors_to_csv` from `users.csv_export`
- After writing YAML output, check if `collector.has_errors()`
- If errors exist:
  - Call `export_errors_to_csv(collector)` to generate CSV content
  - Use fixed filename: `directory-pull-errors.csv`
  - Write CSV using `context.open_output(error_filename, mode="w", encoding="utf-8")`
  - Log: "Wrote {count} errors to {filename}"
- Replace complex `UserEventNotificationGenerator.send_event_notification()` call
- Send simple notification email with:
  - Subject: `[pull_directory] User Processing Errors`
  - Body: gear name, error count, filename, location, affected users, category breakdown
  - Use existing `EmailClient` (may need new `send_simple_email()` method)
- Handle errors gracefully (log but don't fail gear run)

**Acceptance criteria:**
- CSV file created with name `directory-pull-errors.csv`
- CSV uploaded to Flywheel destination
- Simple notification email sent to support addresses
- No use of complex SES templates
- Gear continues if notification fails

### 2.1 Add integration test for pull-directory CSV export

Create integration test to verify pull-directory CSV export flow.

**Files to modify:**
- `gear/pull_directory/test/python/` (add new test file or extend existing)

**Test cases:**
- Gear run with errors produces CSV file
- CSV filename is `directory-pull-errors.csv`
- CSV content matches collector errors
- Notification sent when errors exist
- No notification when no errors

## 3. Update user-management Gear for CSV Export

Modify the user-management gear to export errors to CSV and send simple notifications.

**Files to modify:**
- `gear/user_management/src/python/user_app/run.py`

**Implementation details:**
- Import `export_errors_to_csv` from `users.csv_export`
- After user processing, check if `collector.has_errors()`
- If errors exist:
  - Call `export_errors_to_csv(collector)` to generate CSV content
  - Derive filename from input file: `Path(user_filepath).stem + "-errors.csv"`
  - Write CSV using `context.open_output(error_filename, mode="w", encoding="utf-8")`
  - Log: "Wrote {count} errors to {filename}"
- Replace complex `UserEventNotificationGenerator.send_event_notification()` call
- Send simple notification email with:
  - Subject: `[user_management] User Processing Errors`
  - Body: gear name, error count, filename, location, affected users, category breakdown
  - Use existing `EmailClient` (may need new `send_simple_email()` method)
- Handle errors gracefully (log but don't fail gear run)

**Acceptance criteria:**
- CSV file created with name `{input-basename}-errors.csv`
- CSV uploaded to Flywheel destination
- Simple notification email sent to support addresses
- No use of complex SES templates
- Gear continues if notification fails

### 3.1 Add integration test for user-management CSV export

Create integration test to verify user-management CSV export flow.

**Files to modify:**
- `gear/user_management/test/python/test_integration_gear_error_handling.py` (extend existing test)

**Test cases:**
- Gear run with errors produces CSV file
- CSV filename derived from input file correctly
- CSV content matches collector errors
- Notification sent when errors exist
- No notification when no errors

## 4. Add Simple Email Method to EmailClient (if needed)

Add a simple email sending method to EmailClient if it doesn't already exist.

**Files to modify:**
- `common/src/python/notifications/email.py`

**Implementation details:**
- Check if `EmailClient` has a method for sending plain text emails without templates
- If not, add method: `send_simple_email(to_addresses: List[str], subject: str, body: str) -> Optional[str]`
- Use boto3 SES `send_email()` API (not `send_templated_email()`)
- Return message ID on success, None on failure
- Handle exceptions gracefully

**Acceptance criteria:**
- Method sends plain text email without templates
- Returns message ID on success
- Handles SES errors gracefully

### 4.1 Add unit tests for simple email method

Create unit tests for the simple email sending method.

**Files to modify:**
- `common/test/python/notifications/` (add or extend test file)

**Test cases:**
- Successful email send returns message ID
- Email with multiple recipients
- SES error handling
- Mock SES client to verify API calls

## 5. Run Integration Tests and Verify

Run all tests to ensure the refactoring works correctly.

**Commands to run:**
```bash
./bin/start-devcontainer.sh
./bin/exec-in-devcontainer.sh pants test common/test/python/users::
./bin/exec-in-devcontainer.sh pants test gear/pull_directory/test/python::
./bin/exec-in-devcontainer.sh pants test gear/user_management/test/python::
```

**Acceptance criteria:**
- All unit tests pass
- All integration tests pass
- CSV export produces correct format
- Both gears produce identical CSV structure
- Notifications sent successfully

## 6. Code Quality and Type Checking

Run linting, formatting, and type checking to ensure code quality.

**Commands to run:**
```bash
./bin/start-devcontainer.sh
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
```

**Acceptance criteria:**
- No linting errors
- Code properly formatted
- No type checking errors
- All imports resolved correctly

## 7. Update Documentation (Optional)

Update any relevant documentation to reflect the new CSV export approach.

**Files to potentially update:**
- Gear README files
- Common library documentation
- Any user-facing documentation about error handling

**Acceptance criteria:**
- Documentation reflects new CSV export behavior
- Examples show new error file locations
- Migration notes if needed for existing users
