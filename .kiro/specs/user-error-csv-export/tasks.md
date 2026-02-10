# Implementation Plan: User Error CSV Export

## Overview

This implementation refactors user error handling in the pull-directory and user-management gears by replacing complex AWS SES email templates with CSV file exports stored in Flywheel. The approach involves creating a reusable CSV export function in the common library, integrating it into both gears, and implementing simple notification emails.

## Tasks

- [x] 1. Implement CSV export function in common library
  - [x] 1.1 Create `csv_export.py` module in `common/src/python/users/`
    - Implement `export_errors_to_csv(collector: UserEventCollector) -> str` function
    - Use Python's `csv.DictWriter` with `QUOTE_MINIMAL` and `lineterminator='\n'`
    - Define column order: email, name, center_id, registry_id, auth_email, category, message, action_needed, timestamp, event_id
    - Convert None values to empty strings
    - Format timestamps using `.isoformat()`
    - Extract category values using `.value` from EventCategory enum
    - Raise ValueError if collector is empty or has no errors
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 5.1, 5.2, 5.3, 5.5_
  
  - [ ]* 1.2 Write property test for CSV export round-trip preservation
    - **Property 1: CSV Export Round-Trip Preservation**
    - **Validates: Requirements 1.1, 1.2, 1.3, 5.1**
  
  - [ ]* 1.3 Write property test for None field representation
    - **Property 2: None Field Representation**
    - **Validates: Requirements 1.5**
  
  - [ ]* 1.4 Write property test for special character handling
    - **Property 9: Special Character Handling**
    - **Validates: Requirements 5.5**
  
  - [ ]* 1.5 Write unit tests for CSV export function
    - Test with single error event
    - Test with multiple error events across categories
    - Test with empty collector (should raise ValueError)
    - Test timestamp formatting
    - Test category enum conversion
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 5.2, 5.3_

- [x] 2. Checkpoint - Verify CSV export function
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Integrate CSV export into user-management gear
  - [x] 3.1 Add CSV export and file upload to `gear/user_management/src/python/user_app/run.py`
    - Import `export_errors_to_csv` from common library
    - After processing, check if collector has errors
    - Generate error filename from input file: `{basename}-errors.csv`
    - Call `export_errors_to_csv(collector)` to get CSV content
    - Write CSV using `context.open_output(error_filename, mode="w", encoding="utf-8")`
    - Log the number of errors written and filename
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 4.2, 4.3, 4.4, 4.6_
  
  - [ ]* 3.2 Write property test for error filename generation
    - **Property 3: Error Filename Generation Pattern**
    - **Validates: Requirements 2.2**
  
  - [x] 3.3 Replace complex notification with simple email in user-management gear
    - Remove call to `UserEventNotificationGenerator.send_event_notification()`
    - Create simple email notification after CSV upload
    - Include: gear name, error count, CSV filename, Flywheel location, access instructions
    - Use `EmailClient` to send plain text email (no templates)
    - Only send if support_emails configured and errors exist
    - Handle email send failures gracefully (log but don't fail gear)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 6.3, 6.4_
  
  - [ ]* 3.4 Write property test for notification sent when errors exist
    - **Property 4: Notification Sent for Errors**
    - **Validates: Requirements 3.1**
  
  - [ ]* 3.5 Write property test for notification content completeness
    - **Property 5: Notification Content Completeness**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
  
  - [ ]* 3.6 Write unit tests for user-management gear integration
    - Test filename generation from various input filenames
    - Test CSV content written to context.open_output() (mocked)
    - Test email notification formatting
    - Test no notification sent when no errors
    - _Requirements: 2.2, 2.4, 3.1, 3.7_

- [x] 4. Integrate CSV export into pull-directory gear
  - [x] 4.1 Add CSV export and file upload to `gear/pull_directory/src/python/directory_app/run.py`
    - Import `export_errors_to_csv` from common library
    - After YAML output write, check if collector has errors
    - Use fixed error filename: `directory-pull-errors.csv`
    - Call `export_errors_to_csv(collector)` to get CSV content
    - Write CSV using `context.open_output(error_filename, mode="w", encoding="utf-8")`
    - Log the number of errors written and filename
    - _Requirements: 2.1, 2.3, 2.5, 2.6, 4.2, 4.4, 4.6_
  
  - [x] 4.2 Replace complex notification with simple email in pull-directory gear
    - Remove call to `UserEventNotificationGenerator.send_event_notification()`
    - Create simple email notification after CSV upload
    - Include: gear name, error count, CSV filename, Flywheel location, access instructions
    - Use `EmailClient` to send plain text email (no templates)
    - Only send if support_emails configured and errors exist
    - Handle email send failures gracefully (log but don't fail gear)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 6.3, 6.4_
  
  - [ ]* 4.3 Write unit tests for pull-directory gear integration
    - Test fixed filename usage
    - Test CSV content written to context.open_output() (mocked)
    - Test email notification formatting
    - Test no notification sent when no errors
    - _Requirements: 2.3, 3.1, 3.7_

- [ ] 5. Checkpoint - Verify gear integrations
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Add EmailClient simple email method (if needed)
  - [ ] 6.1 Check if `EmailClient` has a simple email sending method
    - Review `common/src/python/users/event_notifications.py` or equivalent
    - If `send_simple_email()` or similar method exists, skip to task 7
    - If not, implement `send_simple_email(to_addresses, subject, body)` method
    - Method should send plain text email without templates using SES
    - _Requirements: 3.6_
  
  - [ ]* 6.2 Write unit tests for simple email method (if implemented)
    - Test email sending with mocked SES client
    - Test error handling for send failures
    - _Requirements: 3.6_

- [ ] 7. Verify consistent CSV format across gears
  - [ ]* 7.1 Write property test for consistent CSV format
    - **Property 6: Consistent CSV Format Across Gears**
    - **Validates: Requirements 4.6**
  
  - [ ]* 7.2 Write integration test for end-to-end flow
    - Create collector with sample errors
    - Export to CSV
    - Verify CSV content matches input errors
    - Verify all fields present and correctly formatted
    - _Requirements: 1.1, 1.2, 1.3, 5.1, 5.3, 5.4_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Run full test suite: `pants test common/test/python/users:: gear/user_management/test/python:: gear/pull_directory/test/python::`
  - Verify CSV export works correctly
  - Verify both gears produce consistent CSV format
  - Verify simple notifications are sent
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The CSV export function is implemented in the common library for reuse across both gears
- File upload and notification logic remain gear-specific in each gear's run.py
- Property tests validate universal correctness properties with minimum 100 iterations
- Unit tests validate specific examples and edge cases
- The complex SES template system is deprecated but code may remain for backward compatibility
