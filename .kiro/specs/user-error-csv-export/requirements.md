# Requirements Document

## Introduction

This feature refactors the user error handling system in the pull-directory and user-management gears. Currently, these gears collect user processing errors and send them via complex AWS SES email templates. The new approach simplifies this by saving errors to CSV files stored in Flywheel and sending simple notification emails indicating where the error files can be found.

## Glossary

- **Gear**: A Flywheel application that processes data within the NACC Data Platform
- **UserEventCollector**: A component that accumulates user processing errors during gear execution
- **Flywheel**: The NACC Data Platform where projects and files are stored
- **CSV_File**: A comma-separated values file containing error information
- **Error_Notification**: A simple email sent to support staff indicating error file location
- **Input_File**: The YAML file containing user data that the gear processes
- **Error_CSV**: A CSV file containing all errors from processing, named `{input-file-basename}-errors.csv`
- **SES_Template**: AWS Simple Email Service template system (to be deprecated)

## Requirements

### Requirement 1: CSV Export from UserEventCollector

**User Story:** As a developer, I want to export UserEventCollector errors to CSV format, so that errors can be stored as files and easily reviewed in spreadsheet tools.

#### Acceptance Criteria

1. WHEN UserEventCollector contains errors, THE CSV_Export_Function SHALL convert all errors to CSV format
2. THE CSV_File SHALL include columns in order: email, name, center_id, registry_id, auth_email, category, message, action_needed, timestamp, event_id
3. THE CSV_File SHALL preserve all error information currently captured in UserProcessEvent objects
4. THE CSV_File SHALL be human-readable and importable into spreadsheet applications
5. WHEN a field value is None or empty, THE CSV_Export_Function SHALL represent it as an empty string in the CSV

### Requirement 2: File Storage in Flywheel

**User Story:** As a support staff member, I want error files stored in Flywheel alongside the output files, so that I can easily locate and review errors in context.

#### Acceptance Criteria

1. WHEN errors are exported to CSV, THE Gear SHALL save the Error_CSV to the same Flywheel project as the gear output
2. THE User_Management_Gear Error_CSV SHALL be named `{input-file-basename}-errors.csv` where `{input-file-basename}` is the Input_File name without extension
3. THE Pull_Directory_Gear Error_CSV SHALL be named `directory-pull-errors.csv`
4. WHEN the User_Management_Gear Input_File is named `users.yaml`, THE Error_CSV SHALL be named `users-errors.csv`
5. THE Gear SHALL use existing Flywheel gear context methods to upload the Error_CSV
6. THE File_Upload SHALL complete successfully before sending notifications

### Requirement 3: Simple Error Notification Email

**User Story:** As a support staff member, I want to receive simple notification emails when errors occur, so that I know where to find the detailed error information without complex email templates.

#### Acceptance Criteria

1. WHEN errors occur during gear execution, THE Gear SHALL send an Error_Notification to configured support email addresses
2. THE Error_Notification SHALL include the gear name
3. THE Error_Notification SHALL include the total number of errors
4. THE Error_Notification SHALL include the Flywheel location of the Error_CSV
5. THE Error_Notification SHALL include instructions or a link to access the Error_CSV in Flywheel
6. THE Error_Notification SHALL NOT require complex AWS SES templates
7. WHEN no errors occur, THE Gear SHALL NOT send any notification

### Requirement 4: Consistent Implementation Across Gears

**User Story:** As a developer, I want both pull-directory and user-management gears to use the same CSV export approach, so that error handling is consistent and maintainable.

#### Acceptance Criteria

1. THE CSV_Export_Function SHALL be implemented in the common library for reuse
2. THE Pull_Directory_Gear SHALL use the CSV_Export_Function to export errors
3. THE User_Management_Gear SHALL use the CSV_Export_Function to export errors
4. THE File_Upload_Logic SHALL remain in each gear's run.py file (not in common library)
5. THE Notification_Logic SHALL remain in each gear's run.py file (not in common library)
6. THE Filename_Generation_Logic SHALL remain in each gear's run.py file (gear-specific naming)
7. WHEN either gear processes errors, THE resulting CSV format SHALL be identical

### Requirement 5: Preservation of Error Information

**User Story:** As a support staff member, I want all error details preserved in the CSV export, so that I have the same information available as in the previous email system.

#### Acceptance Criteria

1. THE CSV_Export SHALL include all fields from UserProcessEvent: event_id, timestamp, event_type, category, user_context (email, name, center_id, registry_id, auth_email), message, and action_needed
2. THE CSV_Export SHALL represent EventCategory enum values as their human-readable string values
3. THE CSV_Export SHALL format timestamps in ISO 8601 format
4. WHEN comparing CSV export to previous email templates, THE CSV SHALL contain equivalent information for each error
5. THE CSV_Export SHALL handle special characters in error messages without data corruption

### Requirement 6: Deprecation of Complex Template System

**User Story:** As a developer, I want to deprecate the complex SES template system, so that the codebase is simpler and easier to maintain.

#### Acceptance Criteria

1. THE Gears SHALL NOT use UserEventNotificationGenerator.send_event_notification() for error notifications
2. THE Gears SHALL NOT use ConsolidatedNotificationData for error notifications
3. THE Gears SHALL NOT use the "error-consolidated" SES template
4. THE Gears MAY use simple email sending without templates for Error_Notification
5. THE Code SHALL remain backward compatible during transition (existing notification code may remain but unused)
