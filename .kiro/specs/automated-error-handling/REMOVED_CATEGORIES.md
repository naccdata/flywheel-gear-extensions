# Removed Error Categories

## Overview

This document describes error categories that were removed from the automated error handling system because they don't have realistic use cases in the current implementation. These scenarios are documented here so that audit tools can be created to detect them if needed in the future.

**Date Removed:** January 27, 2026

## Removed Categories

### 1. EMAIL_MISMATCH - "Authentication Email Mismatch"

**Original Intent:**
Detect when a user's directory email doesn't match any email in their COManage registry record, but a registry record exists for that user (found by name).

**Why Removed:**
The COManage registry API only supports searching by:

- Email address (`get(email)`)
- Registry ID (`find_by_registry_id(registry_id)`)
- Name for bad claims only (`get_bad_claim(name)`)

There is no general "search by name" capability, so we cannot find a registry record by name to compare emails. The only name-based search is for bad claims (incomplete claims without email), which is already handled by `BAD_ORCID_CLAIMS` and `INCOMPLETE_CLAIM` categories.

**Potential Future Use Case:**
If the registry API is enhanced to support general name-based searches, this category could be reinstated to detect:

- User exists in registry under a different email
- Directory email is outdated or incorrect
- User has multiple registry records with different emails

**Audit Tool Recommendation:**
Create a periodic audit script that:

1. Exports all registry records
2. Exports all directory records
3. Performs fuzzy name matching between the two datasets
4. Identifies cases where names match but emails don't
5. Reports these as potential email mismatches requiring manual review

**Example Scenario:**

```
Directory Record:
  Name: John Doe
  Email: john.doe@newuniversity.edu

Registry Record (if searchable by name):
  Name: John Doe
  Email: j.doe@olduniversity.edu
  
Action: Update directory or registry to use consistent email
```

---

### 2. UNVERIFIED_EMAIL - "Unverified Email"

**Original Intent:**
Detect when a user has a registry record but their email address is not verified in COManage.

**Why Removed:**
The current user management flow already handles unverified emails through the claim process:

- Users without verified emails are not considered "claimed" (see `RegistryPerson.is_claimed()`)
- Unclaimed users go through the `UnclaimedUserProcess` which sends claim emails
- Once users claim their account (log in via identity provider), their email becomes verified
- The `UNCLAIMED_RECORDS` category already covers users who need to verify their email by claiming

The verification status is inherently tied to the claim status, so having a separate category for unverified emails would be redundant.

**Potential Future Use Case:**
If the system needs to distinguish between:

- Users who have never logged in (unclaimed)
- Users who have logged in but whose email verification expired or was revoked
- Users with multiple emails where some are verified and some are not

**Audit Tool Recommendation:**
Create a periodic audit script that:

1. Queries all registry records
2. Identifies users with `status="A"` (active) but no verified emails
3. Checks if these users have logged in (have oidcsub identifier)
4. Reports anomalies where users are active and have logged in but lack verified emails
5. This would indicate a data integrity issue in COManage

**Example Scenario:**

```
Registry Record:
  Name: Jane Smith
  Status: Active
  Emails:
    - jane.smith@university.edu (verified=False)
    - j.smith@university.edu (verified=False)
  Has logged in: Yes (has oidcsub)
  
Issue: User has logged in but no verified email (data integrity problem)
Action: Investigate COManage configuration or manually verify email
```

---

## Implementation Notes

### Code Locations Where These Were Defined

**Enum Definition:**

- File: `common/src/python/users/event_models.py`
- Class: `EventCategory`
- Removed values:
  - `EMAIL_MISMATCH = "Authentication Email Mismatch"`
  - `UNVERIFIED_EMAIL = "Unverified Email"`

**Notification Template Mapping:**

- File: `common/src/python/users/error_notifications.py`
- Class: `ErrorNotificationGenerator`
- Method: `_category_to_field_name()`
- Removed mappings:
  - `EventCategory.EMAIL_MISMATCH: "email_mismatches"`
  - `EventCategory.UNVERIFIED_EMAIL: "unverified_emails"`

**Template Data Model:**

- File: `common/src/python/users/error_notifications.py`
- Class: `ConsolidatedNotificationData`
- Removed fields:
  - `email_mismatches: Optional[List[Dict[str, str]]] = None`
  - `unverified_emails: Optional[List[Dict[str, str]]] = None`

**AWS SES Template:**

- File: `.kiro/specs/automated-error-handling/AWS_SES_TEMPLATES.md`
- Removed template sections for these categories

**Tests:**

- File: `common/test/python/user_test/test_error_notifications.py`
- File: `common/test/python/user_test/test_error_models.py`
- Tests using these categories were removed or updated

---

## Remaining Active Categories

After removal, the system has **9 error categories** (plus 1 success category):

**Success:**

1. USER_CREATED - User successfully created in Flywheel

**Errors:**

1. UNCLAIMED_RECORDS - User has not claimed their COManage registry account
2. INCOMPLETE_CLAIM - User claimed account but identity provider didn't return complete info
3. BAD_ORCID_CLAIMS - User claimed with ORCID but ORCID didn't return email
4. MISSING_DIRECTORY_PERMISSIONS - User lacks required permissions in NACC directory
5. MISSING_DIRECTORY_DATA - Required data missing from directory entry
6. MISSING_REGISTRY_DATA - Expected user record not found in COManage registry
7. INSUFFICIENT_PERMISSIONS - User has no authorizations listed
8. DUPLICATE_USER_RECORDS - User already exists or duplicate records detected
9. FLYWHEEL_ERROR - Flywheel API errors during user processing

---

## Reinstating These Categories

If future requirements or API enhancements make these categories useful again:

1. **Add enum values back** to `EventCategory` in `event_models.py`
2. **Add mapping entries** to `_category_to_field_name()` in `error_notifications.py`
3. **Add optional fields** to `ConsolidatedNotificationData` in `error_notifications.py`
4. **Update AWS SES template** to include sections for these categories
5. **Create error events** in the appropriate process classes where these conditions are detected
6. **Add tests** to verify the error events are created correctly
7. **Update requirements document** to include these categories in the list

---

## Related Documentation

- **Category Usage Analysis:** `.kiro/specs/automated-error-handling/CATEGORY_USAGE_ANALYSIS.md`
- **AWS SES Templates:** `.kiro/specs/automated-error-handling/AWS_SES_TEMPLATES.md`
- **Requirements:** `.kiro/specs/automated-error-handling/requirements.md`
- **Design:** `.kiro/specs/automated-error-handling/design.md`
