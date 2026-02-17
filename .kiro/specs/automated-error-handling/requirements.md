# Requirements Document

## Introduction

This specification defines requirements for enhancing the existing pull_directory and user_management gears with automated error detection, categorization, and notification capabilities. The goal is to provide non-technical support staff with actionable information about user access issues without requiring manual investigation across multiple systems (COManage registry, NACC directory, Flywheel).

## Glossary

- **COManage Registry**: User identity management system that handles user registration and authentication claims
- **NACC Directory**: REDCap-based system containing user authorization and contact information
- **Flywheel**: Data platform where users need access to projects and data
- **Registry Person**: User record in COManage with identity and claim status
- **User Entry**: Directory record containing user information and authorizations
- **Claim**: Process where users link their authentication identity to their registry record
- **Support Staff**: Non-technical personnel who assist users with access issues
- **Error Handler**: System component that detects, categorizes, and generates notifications for user access issues
- **Notification Client**: Component responsible for sending automated emails to support staff

## Requirements

### Requirement 1: General Error Event Capture Mechanism

**User Story:** As a support staff member, I want the system to capture and categorize user access issues using a general notification mechanism, so that I can receive consistent, actionable information about problems that prevent users from accessing the platform.

#### Acceptance Criteria

1. THE Error Capture System SHALL provide a general mechanism for capturing user access issues and mapping them to predefined categories
2. THE Error Capture System SHALL support both existing failure point detection and additional instrumentation for proactive issue detection
3. THE Error Capture System SHALL categorize captured events into predefined categories: Unclaimed Records, Incomplete Claim, Bad ORCID Claims, Missing Directory Permissions, Missing Directory Data, Missing Registry Data, Insufficient Permissions, Duplicate/Wrong User Records, and Flywheel Error
4. THE Error Capture System SHALL include relevant user context (email, name, center, registry ID, error details) with each captured event
5. THE Error Capture System SHALL capture error events without disrupting the normal user processing flow
6. WHEN API calls to external services fail, THE Error Capture System SHALL log these failures for technical staff but SHALL NOT generate support staff notifications for infrastructure issues
7. THE Error Capture System SHALL map each captured event to an appropriate notification message template based on the error category
8. THE Error Capture System SHALL support extensible error categories that can be added without code changes

### Requirement 1a: Existing Failure Point Detection

**User Story:** As a developer, I want to leverage existing failure points in the user management and directory pull processes to capture error events, so that we can provide notifications without extensive code changes.

#### Acceptance Criteria

1. WHEN ActiveUserProcess logs "Active user not in registry", THE Error Capture System SHALL categorize this as "Unclaimed Records"
2. WHEN ClaimedUserProcess logs "Unable to add user", THE Error Capture System SHALL categorize this as "Missing Directory Permissions" or "Duplicate/Wrong User Records" based on context
3. WHEN UpdateUserProcess logs "Failed to find a claimed user", THE Error Capture System SHALL categorize this as "Unclaimed Records"
4. WHEN pull_directory gear logs "Ignoring %s: Permissions not approved", THE Error Capture System SHALL categorize this as "Missing Directory Permissions"
5. WHEN pull_directory gear logs "Ignoring %s: Data platform survey is incomplete", THE Error Capture System SHALL categorize this as "Missing Directory Permissions"
6. WHEN UserRegistry detects incomplete claims via `has_bad_claim()`, THE Error Capture System SHALL analyze the claim to determine if ORCID is the identity provider and categorize as "Bad ORCID Claims" if ORCID is detected, or "Incomplete Claim" otherwise
7. WHEN directory validation errors occur, THE Error Capture System SHALL categorize these appropriately based on the validation failure type
8. THE Error Capture System SHALL preserve all existing logging behavior while adding event capture

### Requirement 1b: Additional Instrumentation for Proactive Detection

**User Story:** As a support staff member, I want the system to proactively detect user access issues that may not surface through normal processing failures, so that I can address problems before users encounter them.

#### Acceptance Criteria

1. THE Error Detection System SHALL check for incomplete claims (users who have logged in but whose identity provider did not return complete information such as email address)
2. THE Error Detection System SHALL identify when incomplete claims are specifically caused by ORCID identity provider by checking organizational identity records
3. THE Error Detection System SHALL indicate an error if the user entry has no authorizations
4. THE Error Detection System SHALL run these proactive checks during user processing without significantly impacting performance
6. THE Error Detection System SHALL use existing API connections and data sources where possible to minimize additional service calls
7. THE Error Detection System SHALL categorize proactively detected issues using the same category system as reactive failure detection

### Requirement 1c: RegistryPerson Interface Enhancement

**User Story:** As a developer, I want the RegistryPerson interface to provide comprehensive access to COManage data needed for error detection, so that I can implement robust error detection mechanisms without bypassing the abstraction layer.

**Status:** ✅ **LARGELY SATISFIED** - Recent enhancements to RegistryPerson have implemented most requirements. See implementation notes below.

#### Acceptance Criteria

1. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL provide methods to access email verification status from COManage EmailAddress records
   - **Implementation**: `verified_email_addresses` property returns all verified emails
   
2. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL provide methods to access detailed ORCID claim information and validation status beyond basic is_claimed() functionality
   - **Implementation**: Enhanced `is_claimed()` method with comprehensive logic checking active status, verified email, and oidcsub identifier from cilogon.org
   
3. ⚠️ **PARTIAL** - THE RegistryPerson Interface SHALL provide methods to access CoPersonRole information for permission level checking
   - **Implementation**: CoPersonRole accessible through underlying `CoPersonMessage` but not exposed as explicit property
   - **Action Needed**: May need explicit property if required for error detection scenarios
   
4. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL provide comprehensive email address comparison capabilities across all EmailAddress records
   - **Implementation**: Multiple properties (`email_addresses`, `organization_email_addresses`, `official_email_addresses`, `verified_email_addresses`) and `has_email()` method
   
5. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL provide methods to access OrgIdentity details for claim validation and identity provider detection
   - **Implementation**: `organization_email_addresses` property uses internal `__get_claim_org()` method to access claimed organizational identity
   - **Implementation**: `org_identities(predicate)` method allows filtering organizational identities by custom predicates
   - **Implementation**: `org_name_is(name)` module-level function creates predicates for testing organization names (e.g., "ORCID")
   
6. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL ensure all COManage data structures (EmailAddress, Identifier, CoPersonRole, OrgIdentity) needed for error detection are accessible through clean interface methods
   - **Implementation**: EmailAddress, Identifier, and OrgIdentity fully accessible; CoPersonRole accessible but may need explicit property
   
7. ✅ **SATISFIED** - THE RegistryPerson Interface SHALL maintain backward compatibility with existing code while adding new access methods
   - **Implementation**: All enhancements are additive; existing methods preserved

### Requirement 2: Category-Based Notification Generation

**User Story:** As a support staff member, I want to receive detailed email notifications that are tailored to specific categories of user access issues, so that I can provide appropriate assistance with clear, actionable guidance.

#### Acceptance Criteria

1. WHEN an error event is categorized as "Unclaimed Records", THE Notification Generator SHALL create a list of unclaimed records with the correct identity provider for each
2. WHEN an error event is categorized as "Incomplete Claim", THE Notification Generator SHALL use a template with instructions to verify identity provider configuration and reclaim account
3. WHEN an error event is categorized as "Bad ORCID Claims", THE Notification Generator SHALL use a template with instructions to delete bad record and reclaim with institutional identity provider (not ORCID)
4. WHEN an error event is categorized as "Missing Directory Permissions", THE Notification Generator SHALL use a template with instructions to contact center administrator for permission assignment
5. WHEN an error event is categorized as "Insufficient Permissions", THE Notification Generator SHALL use a template with instructions when no authorizations are listed in the user entry
6. WHEN an error event is categorized as "Duplicate/Wrong User Records", THE Notification Generator SHALL use a template with instructions for user deactivation and OIDC cache clearing
7. THE Notification Generator SHALL include user-specific context (name, email, center, identity provider details) in all notification templates
9. THE Notification Generator SHALL batch multiple error events for the same user into a single comprehensive notification
10. THE Notification Generator SHALL support both immediate and batched notification delivery modes

### Requirement 3: Success Notification Enhancement

**User Story:** As a support staff member, I want to be notified when users are successfully added to the system, so that I can track successful onboarding and provide proactive support.

#### Acceptance Criteria

1. WHEN a user is successfully created in Flywheel, THE Notification Client SHALL send a success notification to support staff
2. WHEN sending success notifications, THE Notification Client SHALL include user details (name, email, center, registry ID)
3. WHEN sending success notifications, THE Notification Client SHALL include the date and time of successful creation
4. WHEN sending success notifications, THE Notification Client SHALL include the authorizations granted to the user
5. WHEN sending success notifications, THE Notification Client SHALL use a standardized email template for consistency

### Requirement 4: API Integration for Error Context

**User Story:** As a system administrator, I want the error handling system to gather additional context from available sources, so that error notifications contain complete information for resolution.

#### Acceptance Criteria

1. WHEN categorizing errors, THE API Client SHALL query COManage Registry API for additional user record details when needed
2. WHEN categorizing errors, THE API Client SHALL use directory information already available from the pull_directory gear output
3. WHEN categorizing errors, THE API Client SHALL query Flywheel API for user status information when needed
4. WHEN API calls fail, THE Error Handler SHALL log the failure and continue with available information
5. WHEN gathering context, THE API Client SHALL include identity provider information from COManage when available
6. THE Error Handler SHALL use existing user entry data from the directory file as the primary source of user information
7. THE Error Handler SHALL only make additional API calls when essential information is missing from existing data sources

### Requirement 5: AWS SES Template Integration

**User Story:** As a system administrator, I want to use the existing AWS SES template infrastructure for error notifications, so that we maintain consistency with the current email system.

#### Acceptance Criteria

1. THE Notification Generator SHALL use existing AWS SES templates for error notifications
2. THE Notification Generator SHALL create new SES templates for error event types not currently covered
3. THE Notification Generator SHALL use the existing EmailClient and TemplateDataModel infrastructure
4. THE Notification Generator SHALL support variable substitution using the existing template data model pattern
5. THE Notification Generator SHALL extend the existing BaseTemplateModel for error-specific template data
6. THE Notification Generator SHALL maintain compatibility with the existing notification configuration system
7. THE Notification Generator SHALL use the existing SES configuration set for error notifications
8. THE Notification Generator SHALL follow the existing email template naming conventions

### Requirement 6: Support Staff Email Configuration

**User Story:** As a system administrator, I want to configure support staff email addresses for error notifications, so that the right people receive alerts about user access issues.

#### Acceptance Criteria

1. THE Configuration Manager SHALL store support staff email addresses in AWS Parameter Store
2. THE Configuration Manager SHALL support environment-specific email distribution lists (dev/staging/prod)
3. THE Notification Generator SHALL retrieve support staff email addresses from parameter store at runtime
4. THE Notification Generator SHALL send error notifications to all configured support staff email addresses
5. WHEN parameter store access fails, THE Notification Generator SHALL log the error and continue without sending notifications
6. THE Configuration Manager SHALL support both individual email addresses and distribution lists

### Requirement 7: Error Tracking and Monitoring

**User Story:** As a system administrator, I want to track error patterns and resolution status, so that I can identify systemic issues and improve the user onboarding process.

#### Acceptance Criteria

1. THE Error Tracker SHALL log all detected errors with timestamps and categories
2. THE Error Tracker SHALL track email delivery success and failure rates
3. THE Error Tracker SHALL generate periodic reports on common error patterns
4. WHEN email delivery fails, THE Error Tracker SHALL retry sending up to 3 times
5. WHEN email system failures occur, THE Error Tracker SHALL alert administrators
6. THE Error Tracker SHALL maintain error statistics for performance monitoring

### Requirement 8: Integration with Existing User Management Process

**User Story:** As a system administrator, I want the error handling system to integrate seamlessly with existing user management workflows, so that current functionality is preserved while adding new capabilities.

#### Acceptance Criteria

1. THE Error Handler SHALL integrate with the existing UserProcess class without breaking current functionality
2. THE Error Handler SHALL preserve all existing user creation and update workflows
3. THE Error Handler SHALL maintain compatibility with existing notification templates
4. WHEN errors occur during user processing, THE Error Handler SHALL handle them gracefully without stopping the entire process
5. THE Error Handler SHALL extend the existing NotificationClient to support error notifications
6. THE Error Handler SHALL use the existing EmailClient infrastructure for sending notifications

### Requirement 9: Test-Driven Development and Validation

**User Story:** As a developer, I want to use test-driven development for all new error handling functionality, so that I can ensure reliability and correctness through comprehensive testing from the start.

#### Acceptance Criteria

1. THE Development Process SHALL follow test-driven development (TDD) methodology for all new classes and functionality
2. THE Development Process SHALL create unit tests before implementing any new error capture, categorization, or notification code
3. THE Test Suite SHALL include unit tests for each error category detection mechanism
4. THE Test Suite SHALL include integration tests with mock API responses for COManage and Flywheel interactions
5. THE Test Suite SHALL validate email template rendering and variable substitution with various user scenarios
6. THE Test Suite SHALL test error handling gracefully when external APIs are unavailable
7. THE Test Suite SHALL verify email delivery to test accounts using the existing SES infrastructure
8. THE Test Suite SHALL include property-based tests for error categorization logic to ensure consistent behavior across input variations
9. THE Test Suite SHALL test both error capture from existing failure points and error detection from new instrumentation
10. THE Development Process SHALL ensure all new code passes tests before integration with existing systems

### Requirement 10: Integration with Existing Process Error Points

**User Story:** As a developer, I want to integrate error capture seamlessly with existing user processing and directory pull workflows, so that current functionality is preserved while adding comprehensive error notification capabilities.

#### Acceptance Criteria

1. THE User Event Collector SHALL integrate with existing error logging points in UserProcess classes without modifying core processing logic
2. THE User Event Collector SHALL extend existing logging calls to capture structured error events in addition to log messages
3. THE User Event Collector SHALL use existing user entry objects and registry person objects to extract context information
4. THE User Event Collector SHALL integrate with the existing NotificationClient infrastructure and extend it for error notifications
5. THE User Event Collector SHALL preserve all existing logging behavior and error handling while adding event capture
6. THE User Event Collector SHALL use existing API connections (COManage, Flywheel) for additional context gathering when needed
7. THE User Event Collector SHALL support both error capture from existing failure points and error detection from additional instrumentation
8. THE User Event Collector SHALL maintain backward compatibility with existing gear configurations and parameter store settings
9. THE User Event Collector SHALL use the existing AWS SES template system for error notification delivery
10. THE User Event Collector SHALL follow existing patterns for error handling and logging to maintain code consistency

### Requirement 11: Batch Job Reliability and Error Handling

**User Story:** As a system administrator, I want the error handling system to be reliable and fail appropriately for batch job execution, so that failures are clearly logged and the job exits with proper status codes.

#### Acceptance Criteria

1. WHEN critical external service failures occur (COManage, Flywheel, Parameter Store), THE Error Handler SHALL log detailed error information and exit the gear with a non-zero status code
2. THE Error Handler SHALL implement reasonable timeouts for all external API calls to prevent the batch job from hanging indefinitely
3. THE Error Handler SHALL cache API responses within a single gear run to avoid duplicate calls for the same data
4. WHEN non-critical errors occur during user processing (individual user failures), THE Error Handler SHALL collect error events and continue processing remaining users
5. WHEN the notification email fails to send, THE Error Handler SHALL log the failure with full details but SHALL NOT fail the entire gear run
6. THE Error Handler SHALL complete error processing within reasonable time limits (target: 30 seconds per user) to ensure timely batch job completion