# Authorization API Client Library — Spec Prompt

## Goal

Create a shared Python client library in `common/src/python/` that wraps the NACC Authorization API. This library will be used by both the user_management gear (for grant/revoke sync) and the project_management gear (for resource hierarchy seeding).

This is the first increment toward using the Authorization Service as the centralized authorization store. The Portal will query the Authorization API for permission checks (pull model). The gears populate and maintain the store.

## Context

### Authorization API (deployed, production)

The Authorization API is a REST service (AWS Lambda + API Gateway, IAM/SigV4 auth) with 13 endpoints. It stores authorization relationships in OpenFGA. Key endpoints:

- `POST /grants` — grant a user a relation on a resource (returns 201, or 409 if already exists)
- `DELETE /grants` — revoke a user's relation on a resource (returns 200, or 404 if not found)
- `POST /grants/batch` — bulk grant/revoke (up to 100 operations per call)
- `GET /users/{userId}/permissions` — get all resources a user can access
- `PUT /resources/{type}/{resourceId}/parents` — set parent organizations on a resource
- `GET /health` — health check

API authentication: AWS SigV4 signing against the `execute-api` service.

### Authorization Model (types and relations)

The Authorization API enforces this model:

**Organization types:**

- `study` — relations: `member`, `admin`
- `research_center` — relations: `member`, `admin`
- `community` — relations: `member`

**Resource types:**

- `data_pipeline` — relations: `viewer`, `submitter`, `auditor`; parents: `parent_study`, `parent_center`
- `dashboard` — relations: `viewer`, `editor`; parents: `parent_study`, `parent_center`, `parent_community`
- `page` — relations: `viewer`; parents: `parent_study`, `parent_center`, `parent_community`

### Idempotency Semantics

- Granting something that already exists → 409 (treat as success)
- Revoking something that doesn't exist → 404 (treat as success)

### Batch Operation Semantics

`POST /grants/batch` has two phases:

- **Validation** (all-or-nothing): if any operation has invalid input (bad type, bad relation), the entire batch is rejected with 400.
- **Execution** (individual): each operation executes sequentially. Failures are collected per-operation.

The response includes `total`, `succeeded`, `failed`, and an `errors` array with the index of each failed operation. The client should:

- Treat `conflict` (409) and `not_found` (404) as acceptable (idempotent)
- Retry on `service_unavailable` (503 — OpenFGA unreachable)
- Alert/log on unexpected failures

### Rate Limits

No explicit rate limits are configured. At current scale (hundreds of users, nightly runs, sequential batch calls), throttling is not a concern. No backoff needed for normal operation — only retry on 503.

### User ID Format

The `userId` is the `registry_id` (ePPN from CILogon), passed as-is. The API prefixes it with `user:` internally when talking to OpenFGA.

## Requirements

### Client Library

Create a Python client library in `common/src/python/` that wraps the Authorization API:

- SigV4 request signing (AWS credential chain)
- Methods for:
  - `grant(user_id, resource_type, resource_id, relation)` — single grant
  - `revoke(user_id, resource_type, resource_id, relation)` — single revoke
  - `batch(operations)` — bulk grant/revoke (chunks into multiple calls if > 100 operations)
  - `get_user_permissions(user_id)` — get all resources a user can access
  - `set_resource_parents(resource_type, resource_id, parents)` — set parent organizations
  - `health_check()` — health check
- Handles 409 (duplicate grant) as success
- Handles 404 (revoke non-existent) as success
- Configurable API endpoint URL (from environment or parameter)
- Retry on 503 with exponential backoff; fail immediately on other 4xx/5xx
- Proper error handling and logging
- Not coupled to any specific gear — usable by any gear or script in the monorepo

## Design Considerations

- The 100-operation batch limit is not a concern for a single user (typical max ~30-50 grants). The client should still handle chunking transparently.
- The library should expose typed request/response models (Pydantic) for the API payloads.
- SigV4 signing should use the standard AWS credential chain (environment variables, IAM role, etc.). The implementation may use an OpenAPI-generated HTTP client, a hand-written client, or any approach that satisfies the behavioral requirements.
- The library should be testable with mocked HTTP responses (no real AWS calls in tests).

## References

- Authorization API OpenAPI spec: #[[file:openapi.yaml]]
- Authorization model definition: `user-management/components/authorization-api/src/python/authorization_api/auth_model.py`
- OpenFGA schema: `user-management/components/authorization-service/models/schema.json`
