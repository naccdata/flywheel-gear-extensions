# Requirements Document

## Introduction

A shared Python client library that wraps the NACC Authorization API, providing typed, idempotent access to authorization operations. The library lives in `common/src/python/authorization/` and is usable by any gear or script in the monorepo. It is the first increment toward using the Authorization Service as the centralized authorization store — gears populate and maintain the store, and the Portal queries it for permission checks.

## Glossary

- **Authorization_Client**: The Python client class that sends HTTP requests to the Authorization API with SigV4 signing.
- **Authorization_API**: The deployed REST service (AWS Lambda + API Gateway) that manages authorization relationships in OpenFGA.
- **Grant_Operation**: An operation that creates a user-to-resource relationship (user, relation, type, resource_id).
- **Revoke_Operation**: An operation that removes a user-to-resource relationship.
- **Batch_Operation**: A single grant or revoke item within a batch request.
- **Batch_Chunk**: A group of up to 100 batch operations sent in one API call.
- **SigV4_Signing**: AWS Signature Version 4 request signing for `execute-api` service authentication.
- **Idempotent_Success**: Treating HTTP 409 (conflict on grant) and HTTP 404 (not found on revoke) as successful outcomes.
- **Resource_Type**: A type in the authorization model (study, research_center, community, data_pipeline, dashboard, page).
- **Relation**: A named relationship between a user and a resource (e.g., member, admin, viewer, submitter, auditor, editor).
- **Parent_Relationship**: A structural link from a resource to a parent organization (e.g., parent_study, parent_center, parent_community).
- **Registry_ID**: The user identifier (ePPN from CILogon) passed as-is to the API.

## Requirements

### Requirement 1: Client Instantiation and Configuration

**User Story:** As a gear developer, I want to create an Authorization_Client with a configurable API endpoint, so that I can target different environments without code changes.

#### Acceptance Criteria

1. THE Authorization_Client SHALL accept an API base URL as a parameter.
2. THE Authorization_Client SHALL support reading the API base URL from an environment variable as an alternative to an explicit parameter.
3. IF no API base URL is resolvable, THEN THE Authorization_Client SHALL raise a configuration error.
4. THE Authorization_Client SHALL use the standard AWS credential chain for SigV4 signing without requiring explicit credential parameters.

### Requirement 2: Single Grant Operation

**User Story:** As a gear developer, I want to grant a user a relation on a resource with a single method call, so that I can synchronize access without managing HTTP details.

#### Acceptance Criteria

1. WHEN a grant request is sent with a valid user_id, resource_type, resource_id, and relation, THE Authorization_Client SHALL send a POST request to `/grants` with the appropriate JSON body signed with SigV4.
2. WHEN the API returns HTTP 201, THE Authorization_Client SHALL return a success result containing the granted relationship details.
3. WHEN the API returns HTTP 409 (grant already exists), THE Authorization_Client SHALL treat the response as a successful outcome and return a success result.
4. WHEN the API returns HTTP 400 (validation error), THE Authorization_Client SHALL raise an error containing the API error message.
5. WHEN the API returns HTTP 503 (service unavailable), THE Authorization_Client SHALL retry the request with exponential backoff.
6. IF the API returns an unexpected HTTP error (any 4xx other than 400 or 409, or any 5xx other than 503), THEN THE Authorization_Client SHALL raise an error immediately without retrying.

### Requirement 3: Single Revoke Operation

**User Story:** As a gear developer, I want to revoke a user's relation on a resource with a single method call, so that I can remove access without managing HTTP details.

#### Acceptance Criteria

1. WHEN a revoke request is sent with a valid user_id, resource_type, resource_id, and relation, THE Authorization_Client SHALL send a DELETE request to `/grants` with the appropriate JSON body signed with SigV4.
2. WHEN the API returns HTTP 200, THE Authorization_Client SHALL return a success result containing the revoked relationship details.
3. WHEN the API returns HTTP 404 (grant does not exist), THE Authorization_Client SHALL treat the response as a successful outcome and return a success result.
4. WHEN the API returns HTTP 400 (validation error), THE Authorization_Client SHALL raise an error containing the API error message.
5. WHEN the API returns HTTP 503 (service unavailable), THE Authorization_Client SHALL retry the request with exponential backoff.
6. IF the API returns an unexpected HTTP error (any 4xx other than 400 or 404, or any 5xx other than 503), THEN THE Authorization_Client SHALL raise an error immediately without retrying.

### Requirement 4: Batch Grant and Revoke Operations

**User Story:** As a gear developer, I want to submit a list of grant and revoke operations in bulk, so that I can synchronize many access changes efficiently.

#### Acceptance Criteria

1. WHEN a batch request contains 100 or fewer operations, THE Authorization_Client SHALL send a single POST request to `/grants/batch`.
2. WHEN a batch request contains more than 100 operations, THE Authorization_Client SHALL split the operations into chunks of at most 100 and send each chunk as a separate POST request to `/grants/batch`.
3. THE Authorization_Client SHALL preserve the original operation order when splitting into chunks.
4. WHEN the API returns a batch response, THE Authorization_Client SHALL classify per-operation errors with error code `conflict` or `not_found` as acceptable (idempotent) outcomes.
5. WHEN the API returns a batch response containing per-operation errors with error code `service_unavailable`, THE Authorization_Client SHALL report those operations as retriable failures.
6. WHEN the API returns HTTP 400 for the entire batch (validation failure), THE Authorization_Client SHALL raise an error containing the validation error message.
7. THE Authorization_Client SHALL return an aggregate result containing the total count, succeeded count, failed count, and details of each non-idempotent failure across all chunks.

### Requirement 5: Query User Permissions

**User Story:** As a gear developer, I want to retrieve all resources a user can access, so that I can inspect current authorization state.

#### Acceptance Criteria

1. WHEN a user permissions request is sent with a valid user_id, THE Authorization_Client SHALL send a GET request to `/users/{userId}/permissions` signed with SigV4.
2. THE Authorization_Client SHALL return a typed result containing the user's permissions grouped by resource type.
3. WHEN the API returns HTTP 503, THE Authorization_Client SHALL retry the request with exponential backoff.
4. IF the API returns an unexpected HTTP error, THEN THE Authorization_Client SHALL raise an error immediately without retrying.

### Requirement 6: Set Resource Parents

**User Story:** As a gear developer, I want to set the parent organizations of a resource, so that I can seed the resource hierarchy for inherited permissions.

#### Acceptance Criteria

1. WHEN a set-parents request is sent with a valid resource_type, resource_id, and list of parent relationships, THE Authorization_Client SHALL send a PUT request to `/resources/{type}/{resourceId}/parents` with the appropriate JSON body signed with SigV4.
2. WHEN the API returns HTTP 200, THE Authorization_Client SHALL return a success result containing the updated parent relationships.
3. WHEN the API returns HTTP 400 (validation error), THE Authorization_Client SHALL raise an error containing the API error message.
4. WHEN the API returns HTTP 503, THE Authorization_Client SHALL retry the request with exponential backoff.
5. IF the API returns an unexpected HTTP error, THEN THE Authorization_Client SHALL raise an error immediately without retrying.

### Requirement 7: Health Check

**User Story:** As a gear developer, I want to check the health of the Authorization API, so that I can verify connectivity before performing operations.

#### Acceptance Criteria

1. WHEN a health check request is sent, THE Authorization_Client SHALL send a GET request to `/health` signed with SigV4.
2. WHEN the API returns HTTP 200, THE Authorization_Client SHALL return a typed result containing the service health status and authorization engine connectivity status.
3. WHEN the API returns HTTP 503, THE Authorization_Client SHALL return a result indicating the service is unhealthy rather than raising an error.

### Requirement 8: Retry Behavior

**User Story:** As a gear developer, I want the client to automatically retry on transient failures, so that temporary outages do not require manual intervention.

#### Acceptance Criteria

1. WHEN the Authorization_Client retries a request, THE Authorization_Client SHALL use exponential backoff between retry attempts.
2. THE Authorization_Client SHALL limit the number of retry attempts to a configurable maximum before raising an error.
3. THE Authorization_Client SHALL log each retry attempt at warning level, including the attempt number and wait duration.
4. THE Authorization_Client SHALL only retry on HTTP 503 responses; all other error responses SHALL fail immediately.

### Requirement 9: Typed Request and Response Models

**User Story:** As a gear developer, I want typed Pydantic models for all API payloads, so that I get validation and IDE support when constructing requests and reading responses.

#### Acceptance Criteria

1. THE Authorization_Client SHALL expose Pydantic models for grant requests, revoke requests, batch operations, parent relationships, and all response types.
2. THE Authorization_Client SHALL parse API response bodies into typed Pydantic models.
3. IF a response body does not conform to the expected schema, THEN THE Authorization_Client SHALL raise a parse error with the raw response content.

### Requirement 10: Logging

**User Story:** As a gear developer, I want the client to log operations at appropriate levels, so that I can diagnose issues without excessive noise.

#### Acceptance Criteria

1. THE Authorization_Client SHALL log successful operations at debug level.
2. THE Authorization_Client SHALL log idempotent outcomes (409 on grant, 404 on revoke) at debug level.
3. THE Authorization_Client SHALL log retry attempts at warning level.
4. THE Authorization_Client SHALL log non-retriable errors at error level.
5. THE Authorization_Client SHALL use the standard Python logging module with a named logger.

### Requirement 11: Testability

**User Story:** As a gear developer, I want to test code that uses the Authorization_Client without making real HTTP calls, so that tests are fast and deterministic.

#### Acceptance Criteria

1. THE Authorization_Client SHALL support dependency injection of the HTTP transport layer so that tests can substitute a mock.
2. THE Authorization_Client SHALL not import or depend on any gear-specific modules.
