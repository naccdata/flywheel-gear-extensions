# AWS SES Email Templates Required

## Overview

The automated error handling system sends consolidated error notifications to support staff using AWS SES templates. This document specifies all templates that need to be created in AWS SES.

## Template Requirements

### Primary Template

**Template Name:** `error-consolidated`

**Purpose:** Main template for consolidated error notifications sent at the end of gear runs

**Template Data Structure:**

The template data uses a **flat structure** where user context fields are at the same level as error details (no nested `user_context` object). This is achieved through Pydantic's custom serialization.

```json
{
  "gear_name": "user_management",
  "execution_timestamp": "2026-01-27T15:30:00.000000",
  "total_events": 5,
  "events_by_category": {
    "Unclaimed Records": 2,
    "Bad ORCID Claims": 1,
    "Insufficient Permissions": 2
  },
  "error_summaries": [
    "Unclaimed Records: user@example.com - Active user not in registry",
    "Bad ORCID Claims: user2@example.com - User has incomplete claim with ORCID identity provider"
  ],
  "affected_users": [
    "user@example.com",
    "user2@example.com",
    "user3@example.com"
  ],
  "unclaimed_records": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-01-27T15:25:00.000000",
      "event_type": "error",
      "category": "unclaimed_records",
      "message": "Active user not in registry",
      "email": "user@example.com",
      "name": "John Doe",
      "auth_email": "john.doe@institution.edu",
      "action_needed": "send_claim_email"
    }
  ],
  "bad_orcid_claims": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440001",
      "timestamp": "2026-01-27T15:26:00.000000",
      "event_type": "error",
      "category": "bad_orcid_claims",
      "message": "User has incomplete claim with ORCID identity provider",
      "email": "user2@example.com",
      "name": "Jane Smith",
      "action_needed": "delete_bad_record_and_reclaim_with_institutional_idp"
    }
  ],
  "insufficient_permissions": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440002",
      "timestamp": "2026-01-27T15:27:00.000000",
      "event_type": "error",
      "category": "insufficient_permissions",
      "message": "User entry has no authorizations listed",
      "email": "user3@example.com",
      "name": "Bob Johnson",
      "registry_id": "CO123456",
      "action_needed": "contact_center_administrator_for_permissions"
    }
  ]
}
```

**Important Notes on Data Structure:**

1. **Flat Structure**: All error objects have user context fields (email, name, etc.) at the top level, NOT nested under a `user_context` key
2. **Category Field Names**: Category names are converted to snake_case for field names (e.g., "Bad ORCID Claims" → "bad_orcid_claims")
3. **Standard Fields**: Each error object includes `event_id`, `timestamp`, `event_type`, `category`, and `message`
4. **Optional Fields**: Fields like `registry_id`, `auth_email`, `center_id`, and `action_needed` are only included when available
5. **Serialization**: The flat structure is achieved through Pydantic's `@model_serializer` decorator which flattens nested objects during serialization

**Template Variables Available:**

**Summary Fields:**

- `{{gear_name}}` - Name of the gear that generated errors (e.g., "user_management", "pull_directory")
- `{{execution_timestamp}}` - ISO timestamp of when the gear ran
- `{{total_events}}` - Total number of events (errors) detected
- `{{affected_users}}` - Array of unique user email addresses affected

**Category Counts:**

- `{{errors_by_category}}` - Dictionary mapping category names to counts

**Error Summaries:**

- `{{error_summaries}}` - Array of one-line error summaries

**Category-Specific Error Lists:**

Each category has an optional array field with detailed error information:

1. `{{unclaimed_records}}` - Array of unclaimed record errors
2. `{{incomplete_claims}}` - Array of incomplete claim errors
3. `{{bad_orcid_claims}}` - Array of bad ORCID claim errors
4. `{{missing_directory_permissions}}` - Array of missing directory permission errors
5. `{{missing_directory_data}}` - Array of missing directory data errors
6. `{{missing_registry_data}}` - Array of missing registry data errors
7. `{{insufficient_permissions}}` - Array of insufficient permission errors
8. `{{duplicate_user_records}}` - Array of duplicate user record errors
9. `{{flywheel_errors}}` - Array of Flywheel API errors

**Error Object Structure:**

Each error object in the category arrays contains these fields (all flattened at the top level):

**Standard Fields (always present):**

- `event_id` - Unique identifier for the event (UUID string)
- `timestamp` - ISO timestamp when error occurred
- `event_type` - Type of event (always "error" for error notifications)
- `category` - Snake-case category name (e.g., "unclaimed_records", "bad_orcid_claims")
- `message` - Human-readable error message
- `email` - User's email address
- `name` - User's full name (may be "Unknown" if not available)

**Optional Fields (included when available):**

- `registry_id` - COManage registry ID (optional)
- `auth_email` - Authentication email address (optional)
- `center_id` - Center ID number (optional)
- `action_needed` - Recommended action code (optional)

### Template HTML Structure Recommendation

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NACC User Management Error Report</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .header { background-color: #d32f2f; color: white; padding: 20px; }
        .summary { background-color: #f5f5f5; padding: 15px; margin: 20px 0; }
        .error-category { margin: 20px 0; border-left: 4px solid #ff9800; padding-left: 15px; }
        .error-item { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-radius: 4px; }
        .action-needed { background-color: #fff9c4; padding: 5px 10px; border-radius: 3px; font-weight: bold; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f5f5f5; }
    </style>
</head>
<body>
    <div class="header">
        <h1>NACC User Management Error Report</h1>
        <p>Gear: {{gear_name}}</p>
        <p>Execution Time: {{execution_timestamp}}</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total Events:</strong> {{total_events}}</p>
        <p><strong>Affected Users:</strong> {{affected_users_count}}</p>
        
        <h3>Errors by Category</h3>
        <table>
            <tr>
                <th>Category</th>
                <th>Count</th>
            </tr>
            {{#each errors_by_category}}
            <tr>
                <td>{{@key}}</td>
                <td>{{this}}</td>
            </tr>
            {{/each}}
        </table>
        
        <h3>Affected User Emails</h3>
        <ul>
        {{#each affected_users}}
            <li>{{this}}</li>
        {{/each}}
        </ul>
    </div>
    
    {{#if unclaimed_records}}
    <div class="error-category">
        <h2>Unclaimed Records ({{unclaimed_records.length}})</h2>
        <p><strong>Issue:</strong> Users who need to claim their COManage registry account.</p>
        <p><strong>Action:</strong> Verify claim email was sent and follow up with users.</p>
        
        {{#each unclaimed_records}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Auth Email:</strong> {{auth_email}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if bad_orcid_claims}}
    <div class="error-category">
        <h2>Bad ORCID Claims ({{bad_orcid_claims.length}})</h2>
        <p><strong>Issue:</strong> Users claimed their account using ORCID but ORCID did not return email address.</p>
        <p><strong>Action:</strong> Contact user to delete bad record and reclaim using institutional identity provider (NOT ORCID).</p>
        
        {{#each bad_orcid_claims}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if incomplete_claims}}
    <div class="error-category">
        <h2>Incomplete Claims ({{incomplete_claims.length}})</h2>
        <p><strong>Issue:</strong> Users claimed their account but identity provider did not return complete information.</p>
        <p><strong>Action:</strong> Verify identity provider configuration and have user reclaim account.</p>
        
        {{#each incomplete_claims}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if missing_directory_permissions}}
    <div class="error-category">
        <h2>Missing Directory Permissions ({{missing_directory_permissions.length}})</h2>
        <p><strong>Issue:</strong> User does not have required permissions in NACC directory.</p>
        <p><strong>Action:</strong> Contact center administrator to assign permissions.</p>
        
        {{#each missing_directory_permissions}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if missing_directory_data}}
    <div class="error-category">
        <h2>Missing Directory Data ({{missing_directory_data.length}})</h2>
        <p><strong>Issue:</strong> Required data is missing from directory entry.</p>
        <p><strong>Action:</strong> Update directory entry with required information.</p>
        
        {{#each missing_directory_data}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if missing_registry_data}}
    <div class="error-category">
        <h2>Missing Registry Data ({{missing_registry_data.length}})</h2>
        <p><strong>Issue:</strong> Expected user record not found in COManage registry.</p>
        <p><strong>Action:</strong> Verify registry record exists or was deleted.</p>
        
        {{#each missing_registry_data}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Registry ID:</strong> {{registry_id}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if insufficient_permissions}}
    <div class="error-category">
        <h2>Insufficient Permissions ({{insufficient_permissions.length}})</h2>
        <p><strong>Issue:</strong> User has no authorizations listed in directory entry.</p>
        <p><strong>Action:</strong> Contact center administrator to assign authorizations.</p>
        
        {{#each insufficient_permissions}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Registry ID:</strong> {{registry_id}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if duplicate_user_records}}
    <div class="error-category">
        <h2>Duplicate User Records ({{duplicate_user_records.length}})</h2>
        <p><strong>Issue:</strong> User already exists in Flywheel or duplicate records detected.</p>
        <p><strong>Action:</strong> Deactivate duplicate user and clear OIDC cache.</p>
        
        {{#each duplicate_user_records}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Registry ID:</strong> {{registry_id}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    {{#if flywheel_errors}}
    <div class="error-category">
        <h2>Flywheel Errors ({{flywheel_errors.length}})</h2>
        <p><strong>Issue:</strong> Flywheel API errors occurred during user processing.</p>
        <p><strong>Action:</strong> Check Flywheel logs and service status.</p>
        
        {{#each flywheel_errors}}
        <div class="error-item">
            <p><strong>User:</strong> {{name}} ({{email}})</p>
            <p><strong>Registry ID:</strong> {{registry_id}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            {{#if action_needed}}
            <p class="action-needed">Action: {{action_needed}}</p>
            {{/if}}
        </div>
        {{/each}}
    </div>
    {{/if}}
    
    <div style="margin-top: 40px; padding: 20px; background-color: #f5f5f5; border-top: 2px solid #ddd;">
        <p><strong>Note:</strong> This is an automated notification from the NACC Data Platform user management system.</p>
        <p>For questions or issues, please contact the NACC technical team.</p>
    </div>
</body>
</html>
```

### Template Text Version (Plain Text)

AWS SES requires both HTML and text versions. Here's the text version structure:

```text
NACC User Management Error Report
==================================

Gear: {{gear_name}}
Execution Time: {{execution_timestamp}}

SUMMARY
-------
Total Events: {{total_events}}
Affected Users: {{affected_users_count}}

Affected User Emails:
{{#each affected_users}}
- {{this}}
{{/each}}

Errors by Category:
{{#each errors_by_category}}
- {{@key}}: {{this}}
{{/each}}

{{#if unclaimed_records}}
UNCLAIMED RECORDS ({{unclaimed_records.length}})
-------------------------------------------------
Issue: Users who need to claim their COManage registry account.
Action: Verify claim email was sent and follow up with users.

{{#each unclaimed_records}}
User: {{name}} ({{email}})
Auth Email: {{auth_email}}
Message: {{message}}
Time: {{timestamp}}
{{#if action_needed}}Action: {{action_needed}}{{/if}}

{{/each}}
{{/if}}

{{#if bad_orcid_claims}}
BAD ORCID CLAIMS ({{bad_orcid_claims.length}})
----------------------------------------------
Issue: Users claimed their account using ORCID but ORCID did not return email address.
Action: Contact user to delete bad record and reclaim using institutional identity provider (NOT ORCID).

{{#each bad_orcid_claims}}
User: {{name}} ({{email}})
Message: {{message}}
Time: {{timestamp}}
{{#if action_needed}}Action: {{action_needed}}{{/if}}

{{/each}}
{{/if}}

[Continue with similar sections for all other error categories...]

---
Note: This is an automated notification from the NACC Data Platform user management system.
For questions or issues, please contact the NACC technical team.
```

## Category-Specific Templates

**Status:** ❌ **NOT IMPLEMENTED**

The original design included individual templates for each error category, but these were **removed from the implementation** as they are not needed. The system uses only the consolidated template which handles all error categories in a single email.

The following template names were originally planned but are **not used and should not be created**:

- `error-unclaimed-records`
- `error-email-mismatch`
- `error-unverified-email`
- `error-incomplete-claim`
- `error-bad-orcid-claims`
- `error-missing-directory-permissions`
- `error-missing-directory-data`
- `error-missing-registry-data`
- `error-insufficient-permissions`
- `error-duplicate-user-records`
- `error-flywheel-error`

**Note:** If category-specific notifications are needed in the future, these templates can be created and the code can be updated to use them.

## AWS SES Template Creation Steps

### Using AWS CLI

```bash
# Create the template
aws ses create-template --cli-input-json file://error-consolidated-template.json

# Update the template (if it already exists)
aws ses update-template --cli-input-json file://error-consolidated-template.json

# List all templates
aws ses list-templates

# Get template details
aws ses get-template --template-name error-consolidated

# Delete template (if needed)
aws ses delete-template --template-name error-consolidated
```

### Template JSON File Format

Create a file named `error-consolidated-template.json`:

```json
{
  "Template": {
    "TemplateName": "error-consolidated",
    "SubjectPart": "NACC User Management Errors - {{gear_name}} - {{total_events}} errors",
    "HtmlPart": "[Insert HTML template here]",
    "TextPart": "[Insert text template here]"
  }
}
```

### Using AWS Console

1. Navigate to Amazon SES in AWS Console
2. Go to "Email Templates" in the left sidebar
3. Click "Create template"
4. Enter template name: `error-consolidated`
5. Enter subject: `NACC User Management Errors - {{gear_name}} - {{total_events}} errors`
6. Paste HTML content in HTML part
7. Paste text content in Text part
8. Click "Create template"

## Testing the Template

### Test Data File

Create `test-template-data.json`:

```json
{
  "gear_name": "user_management",
  "execution_timestamp": "2026-01-27T15:30:00.000000",
  "total_events": 2,
  "events_by_category": {
    "Unclaimed Records": 1,
    "Bad ORCID Claims": 1
  },
  "error_summaries": [
    "Unclaimed Records: test@example.com - Active user not in registry",
    "Bad ORCID Claims: test2@example.com - User has incomplete claim with ORCID"
  ],
  "affected_users": ["test@example.com", "test2@example.com"],
  "unclaimed_records": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-01-27T15:25:00.000000",
      "event_type": "error",
      "category": "unclaimed_records",
      "message": "Active user not in registry",
      "email": "test@example.com",
      "name": "Test User",
      "auth_email": "test@institution.edu",
      "action_needed": "send_claim_email"
    }
  ],
  "bad_orcid_claims": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440001",
      "timestamp": "2026-01-27T15:26:00.000000",
      "event_type": "error",
      "category": "bad_orcid_claims",
      "message": "User has incomplete claim with ORCID identity provider",
      "email": "test2@example.com",
      "name": "Test User 2",
      "action_needed": "delete_bad_record_and_reclaim_with_institutional_idp"
    }
  ]
}
```

### Send Test Email

```bash
aws ses send-templated-email \
  --source "noreply@nacc.example.com" \
  --destination "ToAddresses=your-test-email@example.com" \
  --template error-consolidated \
  --template-data file://test-template-data.json \
  --configuration-set-name your-ses-config-set
```

## Environment-Specific Considerations

### Development Environment

- Use test email addresses
- Consider using SES sandbox mode
- Verify email addresses before sending

### Staging Environment

- Use staging-specific support email distribution list
- Test with realistic data volumes

### Production Environment

- Use production support email distribution list
- Ensure SES sending limits are appropriate
- Monitor bounce and complaint rates

## Required AWS SES Configuration

1. **Verified Email Addresses/Domains:**
   - Source email address (e.g., `noreply@nacc.example.com`)
   - Support staff email addresses (or use verified domain)

2. **Configuration Set:**
   - Create or use existing configuration set
   - Configure event publishing (optional but recommended)
   - Set up bounce and complaint handling

3. **Sending Limits:**
   - Ensure SES account is out of sandbox mode for production
   - Verify sending limits are sufficient for expected volume

4. **IAM Permissions:**
   - Gear execution role needs `ses:SendTemplatedEmail` permission
   - Gear execution role needs `ses:SendEmail` permission (for fallback)

## Summary

**Required for Implementation:**

- ✅ 1 AWS SES template: `error-consolidated`
- ✅ Both HTML and text versions
- ✅ Verified source email address
- ✅ Verified destination email addresses (or domain)
- ✅ SES configuration set
- ✅ IAM permissions for gear execution role

**Not Used:**

- ❌ Category-specific templates (removed from implementation)

**Next Steps:**

1. Create the `error-consolidated` template in AWS SES
2. Test with sample data
3. Verify support staff email addresses are configured in Parameter Store
4. Deploy and monitor
