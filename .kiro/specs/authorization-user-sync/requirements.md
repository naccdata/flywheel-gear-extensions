# Requirements Document

## Introduction

Integrate the user_management gear with the NACC Authorization API so that when the gear processes user authorizations, it writes the corresponding grants to the Authorization Service in addition to its existing Flywheel role assignment. The gear's internal authorization vocabulary (Activity = action + Resource) is translated to the API's vocabulary (type + relation + resource_id), and a diff-based sync ensures the user's grants in the Authorization API match their computed authorizations.

This feature depends on the shared Authorization_Client library (see `authorization-client-library` spec) and assumes the resource hierarchy is seeded by the project_management gear (see `authorization-resource-hierarchy` spec).

## Glossary

- **Authorization_Sync**: The process that synchronizes a user's grants in the Authorization API to match their computed authorizations from the gear.
- **Activity_Translator**: The module that converts the gear's Activity (action + Resource) into the Authorization API's grant vocabulary (resource type, relation, resource ID).
- **Authorization_Client**: The shared Python client class that sends HTTP requests to the Authorization API (defined in the `authorization-client-library` spec).
- **Grant**: A user-to-resource relationship in the Authorization API, consisting of user_id, resource_type, resource_id, and relation.
- **Desired_Grants**: The complete set of grants a user should hold, as computed from their directory authorizations.
- **Current_Grants**: The set of grants a user currently holds in the Authorization API, retrieved via the client library.
- **Activity**: A gear-internal model combining an action (`submit-audit` or `view`) with a Resource (`DatatypeResource`, `DashboardResource`, or `PageResource`).
- **Registry_ID**: The user's registry identifier (ePPN from CILogon), used as the user ID in the Authorization API.
- **Center_Group_ID**: The Flywheel group ID for a research center (e.g., `washington`, `upenn-ftld`), resolved by the caller and passed to the translator.
- **Resource_ID**: The identifier for a resource in the Authorization API, following the Flywheel project label naming convention.
- **UserEventCollector**: The existing event collection mechanism used by the gear to report errors and successes for operator visibility.
- **Batch_Operation**: A single grant or revoke item within a batch request to the Authorization API.

## Requirements

### Requirement 1: Activity-to-Grant Type Mapping

**User Story:** As a gear developer, I want a mapping from the gear's Activity vocabulary to the Authorization API's type and relation pairs, so that the translator can convert internal authorizations to API grants.

#### Acceptance Criteria

1. THE Activity_Translator SHALL map each combination of gear action and Resource type to zero or more Authorization API (resource type, relation) pairs as enumerated in criteria 2 through 5, and SHALL treat any combination not listed in criteria 2 through 5 as unmapped.
2. WHEN the gear action is `submit-audit` and the Resource is a DatatypeResource, THE Activity_Translator SHALL produce both a `submitter` relation and a `viewer` relation on the `data_pipeline` resource type.
3. WHEN the gear action is `view` and the Resource is a DatatypeResource, THE Activity_Translator SHALL produce a `viewer` relation on the `data_pipeline` resource type.
4. WHEN the gear action is `view` and the Resource is a DashboardResource, THE Activity_Translator SHALL produce a `viewer` relation on the `dashboard` resource type.
5. WHEN the gear action is `view` and the Resource is a PageResource, THE Activity_Translator SHALL produce a `viewer` relation on the `page` resource type.
6. THE Activity_Translator SHALL co-locate the mapping as a module-level constant within the translator module.
7. THE Activity_Translator SHALL only define mappings for the action-Resource combinations listed in criteria 2 through 5; the combinations `submit-audit` + DashboardResource and `submit-audit` + PageResource SHALL have no mapping entries.

### Requirement 2: Resource ID Resolution

**User Story:** As a gear developer, I want the translator to produce resource IDs that match the resources registered in the Authorization API by the resource-hierarchy seeder, so that grants reference the correct resources.

#### Acceptance Criteria

1. THE resource ID in each produced Grant SHALL equal the Flywheel project label for the corresponding resource, which is the same label the resource-hierarchy seeder uses when registering that resource in the Authorization API.
2. WHEN translating a center-scoped activity, THE Activity_Translator SHALL include the center group ID as a scope prefix in the resource ID (e.g., `{center_group_id}/{project_label}`).
3. WHEN translating a general (non-center, non-study) activity with a PageResource, THE Activity_Translator SHALL use the project label with no center or study prefix as the resource ID.
4. THE Activity_Translator SHALL receive the already-resolved center group ID from the caller without performing adcid-to-group-ID lookup.
5. IF the Activity cannot be resolved to a valid resource ID (e.g., missing required context), THEN THE Activity_Translator SHALL log a warning and skip the activity without raising an error.

### Requirement 3: Translate User Authorizations to Desired Grants

**User Story:** As a gear developer, I want to translate a user's complete set of authorizations (study and general) into the set of grants they should hold, so that the sync process can compute the diff.

#### Acceptance Criteria

1. WHEN given a CenterUserEntry with study_authorizations and a center_group_id, THE Activity_Translator SHALL translate each study's activities into grants where each Grant contains the user's Registry_ID, the resolved resource type, the resource ID scoped to the center_group_id and study_id, and the mapped relation.
2. WHEN given general authorizations (Authorizations object) and a user's Registry_ID, THE Activity_Translator SHALL translate each activity into grants scoped by resource name only, without center or study qualifiers.
3. THE Activity_Translator SHALL return the complete set of Desired_Grants as a collection of Grant objects each containing user_id, resource_type, resource_id, and relation fields matching the Authorization_Client batch operation input format.
4. IF an Activity has no mapping in the translation table, THEN THE Activity_Translator SHALL log a warning identifying the unmapped activity and skip it without raising an error.
5. THE Activity_Translator SHALL deduplicate the returned Desired_Grants such that no two Grant objects in the collection share the same combination of user_id, resource_type, resource_id, and relation.
6. WHEN a CenterUserEntry has an empty study_authorizations list and empty general authorizations, THE Activity_Translator SHALL return an empty Desired_Grants collection.

### Requirement 4: Query Current User Grants

**User Story:** As a gear developer, I want the sync process to retrieve a user's current grants from the Authorization API, so that it can compute the diff against the desired state.

#### Acceptance Criteria

1. WHEN synchronizing a user, THE Authorization_Sync SHALL query the user's current grants from the Authorization API using the Authorization_Client `query user permissions` method with the user's Registry_ID.
2. THE Authorization_Sync SHALL parse the returned permissions (grouped by resource type) into a flat set of Grant objects, each containing user_id, resource_type, resource_id, and relation, such that two Grant objects are equal when all four fields match.
3. IF the query fails with a non-retriable error, THEN THE Authorization_Sync SHALL log the error, report it via UserEventCollector with the user's Registry_ID and error details, and skip the sync for that user without blocking processing of subsequent users.
4. WHEN the Authorization_Client returns an empty permissions response for a user, THE Authorization_Sync SHALL treat the result as a valid empty set of Current_Grants.

### Requirement 5: Compute Grant Diff

**User Story:** As a gear developer, I want the sync process to compute the difference between desired and current grants, so that only the necessary adds and revokes are applied.

#### Acceptance Criteria

1. THE Authorization_Sync SHALL compute grants to add as the set of Desired_Grants minus Current_Grants.
2. THE Authorization_Sync SHALL compute grants to revoke as the set of Current_Grants minus Desired_Grants.
3. WHEN the Desired_Grants and Current_Grants are identical, THE Authorization_Sync SHALL perform no API calls for that user.
4. THE Authorization_Sync SHALL treat grants as equal when they match on all four fields: user_id, resource_type, resource_id, and relation, using case-sensitive string comparison.
5. IF the Desired_Grants set is empty and the Current_Grants set is non-empty, THEN THE Authorization_Sync SHALL compute all Current_Grants as grants to revoke.
6. IF the Current_Grants set is empty and the Desired_Grants set is non-empty, THEN THE Authorization_Sync SHALL compute all Desired_Grants as grants to add.

### Requirement 6: Apply Grant Changes via Batch

**User Story:** As a gear developer, I want the sync process to apply the computed adds and revokes via the batch API, so that the user's grants are updated efficiently.

#### Acceptance Criteria

1. WHEN there are grants to add or revoke, THE Authorization_Sync SHALL construct Batch_Operations (each specifying operation type, user_id, resource_type, resource_id, and relation) and submit them using the Authorization_Client batch method.
2. THE Authorization_Sync SHALL combine all grant and revoke operations for a user into a single batch call to the Authorization_Client.
3. THE Authorization_Sync SHALL rely on the Authorization_Client to chunk operations exceeding the 100-operation batch limit.
4. THE Authorization_Sync SHALL rely on the Authorization_Client for idempotent handling of conflicts (409 on grant) and not-found (404 on revoke).
5. IF the Authorization_Client batch method raises a non-idempotent error, THEN THE Authorization_Sync SHALL propagate the failure to the fault isolation layer defined in Requirement 7 without retrying at the sync level.

### Requirement 7: Fault Isolation from Flywheel Processing

**User Story:** As a gear operator, I want authorization sync failures to not block Flywheel user processing, so that the gear run completes even if the Authorization API is unavailable.

#### Acceptance Criteria

1. IF the Authorization_Sync encounters an error that the Authorization_Client does not retry (any error other than HTTP 503, or an HTTP 503 after retries are exhausted), THEN THE Authorization_Sync SHALL log the error at error level and continue processing the next user.
2. IF the Authorization_Sync encounters an HTTP 503 response, THEN THE Authorization_Sync SHALL rely on the Authorization_Client retry mechanism and treat the failure as non-retriable only after the Authorization_Client reports retries exhausted.
3. IF the Authorization_Sync fails for a user, THEN THE Authorization_Sync SHALL report the failure via the UserEventCollector including the user's Registry_ID, the operation attempted (query, grant, or revoke), and the error description.
4. THE Authorization_Sync SHALL not raise exceptions that propagate to the Flywheel user processing pipeline.

### Requirement 8: Integration with User Processing Pipeline

**User Story:** As a gear developer, I want the authorization sync to execute as a step in the existing user processing pipeline, so that grants are updated whenever user authorizations are processed.

#### Acceptance Criteria

1. WHEN the UpdateCenterUserProcess authorizes a user, THE User_Processing_Pipeline SHALL invoke the Authorization_Sync for that user after the CenterAuthorizationVisitor has been applied, passing the user's Registry_ID and the resolved center group ID (the Flywheel group ID of the center).
2. WHEN the UpdateUserProcess authorizes a user with general authorizations, THE User_Processing_Pipeline SHALL invoke the Authorization_Sync for that user's general grants, passing the user's Registry_ID and no center group ID.
3. THE User_Processing_Pipeline SHALL accept the Authorization_Sync as an optional dependency injected via `__init__`, following the existing pattern of passing collaborators to process constructors.
4. IF the Authorization_Sync dependency is not provided, THEN THE User_Processing_Pipeline SHALL skip the sync step and proceed with existing Flywheel role assignment only.
5. THE User_Processing_Pipeline SHALL complete existing Flywheel role assignment (CenterAuthorizationVisitor or GeneralAuthorizationVisitor processing) regardless of whether the Authorization_Sync succeeds or fails.

### Requirement 9: Sync Reporting via UserEventCollector

**User Story:** As a gear operator, I want visibility into authorization sync outcomes, so that I can diagnose issues and confirm successful synchronization.

#### Acceptance Criteria

1. WHEN the Authorization_Sync completes successfully for a user, THE Authorization_Sync SHALL log at info level the user's Registry_ID, the number of grants added, and the number of grants revoked.
2. WHEN the Authorization_Sync fails for a user, THE Authorization_Sync SHALL collect an error event via UserEventCollector containing a UserProcessEvent with EventType ERROR, the AUTHORIZATION_SYNC EventCategory, a UserContext including the user's Registry_ID, and a message indicating the failure reason and the sync operation that failed (e.g., connection to auth service, grant addition, or grant revocation).
3. THE Authorization_Sync SHALL use a dedicated EventCategory enum value named AUTHORIZATION_SYNC with a display value distinct from all existing EventCategory values, so that operators can filter authorization sync events separately from Flywheel role assignment errors.
4. IF the Authorization_Sync partially succeeds for a user (some grants applied but at least one grant addition or revocation fails), THEN THE Authorization_Sync SHALL log the successful grant changes at info level and collect an error event via UserEventCollector for each failed grant operation.

### Requirement 10: Submit-Audit Implies Viewer Invariant

**User Story:** As a gear developer, I want the translator to enforce the invariant that `submit-audit` always produces both `submitter` and `viewer` relations, so that the Authorization API state is consistent with the access model.

#### Acceptance Criteria

1. WHEN translating a `submit-audit` activity on a DatatypeResource, THE Activity_Translator SHALL produce two grants: one with relation `submitter` and one with relation `viewer`, both on the same `data_pipeline` resource with the same resource_id.
2. IF both a `submit-audit` activity and a `view` activity exist for the same DatatypeResource, THEN THE Activity_Translator SHALL produce the `viewer` grant only once in the Desired_Grants for that resource (no duplicate viewer entries).
3. THE Desired_Grants for any user with a `submit-audit` activity on a DatatypeResource SHALL contain both a `submitter` and a `viewer` grant matching on resource_type `data_pipeline`, the same resource_id, and the same user_id.
