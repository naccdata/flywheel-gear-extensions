# Requirements Document

## Introduction

The RegistryPerson class wraps COManage CoPersonMessage objects to represent users in the NACC registry. Currently, the class has inconsistent handling of multi-valued attributes (emails, names, identifiers) and lacks comprehensive testing. This specification addresses these issues by clarifying email selection semantics, adding comprehensive test coverage, and improving the API for working with multi-valued attributes while maintaining backward compatibility.

## Glossary

- **RegistryPerson**: A Python class that wraps COManage CoPersonMessage objects and provides convenient access to person attributes
- **COManage**: Identity and access management platform used by NACC for user registry
- **CoPersonMessage**: COManage API object containing person data including emails, names, identifiers, and organizational identities
- **EmailAddress**: COManage model representing an email address with properties like mail, type, and verified status
- **OrgIdentity**: Organizational identity in COManage representing a person's affiliation with an organization
- **Multi-valued Attribute**: An attribute that can have multiple values (e.g., a person can have multiple email addresses)
- **Official Email**: An email address marked with type="official" in COManage
- **Organizational Email**: An email address associated with a claimed organizational identity
- **Verified Email**: An email address marked as verified=True in COManage
- **Primary Name**: The name marked as primary_name=True in COManage
- **Registry ID**: The NACC identifier (type="naccid") for a person in the registry
- **Claimed Account**: A person record that has an oidcsub identifier indicating the user has logged in

## Requirements

### Requirement 1: Email Selection Strategy

**User Story:** As a developer using RegistryPerson, I want clear semantics for which email address to use in different contexts, so that I can reliably identify users and understand email priority.

#### Acceptance Criteria

1. WHEN accessing the primary email via email_address property, THE RegistryPerson SHALL return the first organizational email if one exists
2. WHEN no organizational email exists, THE RegistryPerson SHALL return the first official email if one exists
3. WHEN no organizational or official email exists, THE RegistryPerson SHALL return the first verified email if one exists
4. WHEN no organizational, official, or verified email exists, THE RegistryPerson SHALL return the first email if one exists
5. WHEN no emails exist, THE RegistryPerson SHALL return None for the primary email
6. THE RegistryPerson SHALL provide access to all email addresses as a list
7. THE RegistryPerson SHALL provide access to organizational email addresses as a separate list
8. THE RegistryPerson SHALL provide access to all official email addresses as a separate list
9. THE RegistryPerson SHALL provide a method to check if a specific email address exists across all email addresses for the person
10. WHEN checking if an account is claimed via is_claimed method, THE RegistryPerson SHALL verify that the person has at least one verified email address

### Requirement 2: Comprehensive Test Coverage

**User Story:** As a developer maintaining the NACC codebase, I want comprehensive unit tests for RegistryPerson, so that I can refactor safely and catch regressions early.

#### Acceptance Criteria

1. WHEN testing email selection, THE test suite SHALL verify all email priority scenarios
2. WHEN testing with no emails, THE test suite SHALL verify None is returned for primary email
3. WHEN testing with multiple emails, THE test suite SHALL verify correct email selection based on type and verification
4. WHEN testing name handling, THE test suite SHALL verify primary name extraction and formatting
5. WHEN testing identifier handling, THE test suite SHALL verify filtering with predicates
6. WHEN testing claimed status, THE test suite SHALL verify detection of oidcsub identifiers
7. WHEN testing registry ID, THE test suite SHALL verify extraction of naccid identifiers
8. WHEN testing active status, THE test suite SHALL verify CoPerson status checking
9. WHEN testing creation date, THE test suite SHALL verify metadata extraction
10. WHEN testing the create factory method, THE test suite SHALL verify proper object construction

### Requirement 3: Email Type Filtering

**User Story:** As a developer, I want to filter emails by type and verification status, so that I can select appropriate emails for different use cases and check all emails of a given type.

#### Acceptance Criteria

1. THE RegistryPerson SHALL provide a method to get all emails filtered by type
2. THE RegistryPerson SHALL provide a method to get all verified emails only
3. THE RegistryPerson SHALL provide a method to get all official emails
4. WHEN filtering emails, THE RegistryPerson SHALL return an empty list if no matches exist
5. WHEN filtering emails, THE RegistryPerson SHALL preserve the order of emails from COManage
6. WHEN checking if a person has a specific email, THE RegistryPerson SHALL search across all email addresses regardless of type

### Requirement 4: Backward Compatibility

**User Story:** As a developer maintaining existing code, I want the refactored RegistryPerson to maintain backward compatibility, so that existing code continues to work without changes.

#### Acceptance Criteria

1. THE RegistryPerson SHALL maintain the existing email_address property
2. THE RegistryPerson SHALL maintain the existing email_addresses property
3. THE RegistryPerson SHALL maintain the existing has_email method
4. THE RegistryPerson SHALL maintain the existing primary_name property
5. THE RegistryPerson SHALL maintain the existing identifiers method
6. THE RegistryPerson SHALL maintain the existing is_claimed method
7. THE RegistryPerson SHALL maintain the existing is_active method
8. THE RegistryPerson SHALL maintain the existing registry_id method
9. THE RegistryPerson SHALL maintain the existing create factory method
10. THE RegistryPerson SHALL maintain the existing organization_email_addresses property

### Requirement 5: Documentation and Type Safety

**User Story:** As a developer using RegistryPerson, I want clear documentation and type hints, so that I understand how to use the API correctly and catch errors at development time.

#### Acceptance Criteria

1. THE RegistryPerson SHALL have docstrings for all public methods explaining their behavior
2. THE RegistryPerson SHALL have type hints for all method parameters and return values
3. THE RegistryPerson SHALL document the email selection priority in the email_address property docstring
4. THE RegistryPerson SHALL document the difference between email_address and email_addresses
5. THE RegistryPerson SHALL document what constitutes a "claimed" account
6. THE RegistryPerson SHALL document what constitutes an "active" person
