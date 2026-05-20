# Implementation Plan: Authorization Client Library

## Overview

Implement a shared Python client library at `common/src/python/authorization/` that wraps the NACC Authorization API. The implementation follows the design's protocol-based transport abstraction, Pydantic v2 models, and retry logic with exponential backoff. Tests go in `common/test/python/authorization_test/`.

## Tasks

- [x] 1. Set up package structure and core types
  - [x] 1.1 Create package directory structure and BUILD files
    - Create `common/src/python/authorization/` with `__init__.py` and `BUILD`
    - Create `common/test/python/authorization_test/` with `__init__.py`, `conftest.py`, and `BUILD`
    - Configure Pants targets for sources and tests
    - _Requirements: 11.2_

  - [x] 1.2 Implement exception hierarchy
    - Create `common/src/python/authorization/exceptions.py`
    - Define `AuthorizationClientError`, `ConfigurationError`, `ValidationError`, `ServiceUnavailableError`, `UnexpectedError`, `ParseError`
    - Each exception includes the attributes specified in the design (e.g., `ParseError.raw_content`, `UnexpectedError.status_code`)
    - _Requirements: 2.4, 2.6, 3.4, 3.6, 9.3_

  - [x] 1.3 Implement Pydantic request and response models
    - Create `common/src/python/authorization/models.py`
    - Define all request models: `GrantRequest`, `RevokeRequest`, `BatchOperationModel`, `BatchRequestModel`, `SetParentsRequestModel`, `ParentRelationshipModel`
    - Define all response models: `GrantResult`, `RevokeResult`, `BatchError`, `BatchResult`, `InheritanceSource`, `PermissionEntry`, `UserPermissions`, `ParentRelationship`, `ResourceParents`, `HealthResult`, `ErrorResponse`
    - Define domain types: `BatchOperation`
    - Use Pydantic v2 `Field(alias=...)` for camelCase JSON serialization
    - _Requirements: 9.1, 9.2_

  - [x] 1.4 Define the HttpTransport protocol and HttpResponse protocol
    - Create `common/src/python/authorization/transport.py`
    - Define `HttpResponse` protocol with `status_code` and `body` properties
    - Define `HttpTransport` protocol with `request(method, path, body, query_params)` method
    - _Requirements: 11.1_

- [x] 2. Implement transport and retry logic
  - [x] 2.1 Implement SigV4Transport
    - Create `common/src/python/authorization/sigv4_transport.py`
    - Implement `SigV4Transport` class using `botocore.auth.SigV4Auth` with standard credential chain
    - Sign requests against `execute-api` service
    - Accept `base_url` and optional `region` parameters
    - _Requirements: 1.4, 2.1, 3.1, 5.1, 6.1_

  - [x] 2.2 Implement retry logic with exponential backoff
    - Create `common/src/python/authorization/retry.py`
    - Implement retry wrapper that retries only on HTTP 503
    - Use exponential backoff: `base_backoff × 2^(attempt-1)`
    - Accept configurable `max_retries` and `base_backoff`
    - Log each retry attempt at WARNING level with attempt number and wait duration
    - Raise `ServiceUnavailableError` when retries exhausted
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement AuthorizationClient operations
  - [x] 4.1 Implement grant and revoke methods
    - Create `common/src/python/authorization/client.py`
    - Implement `AuthorizationClient.__init__` accepting `transport`, `max_retries`, `base_backoff`
    - Implement `grant()`: POST to `/grants`, return `GrantResult`, treat 409 as success
    - Implement `revoke()`: DELETE to `/grants`, return `RevokeResult`, treat 404 as success
    - Raise `ValidationError` on 400, `UnexpectedError` on other errors
    - Use retry logic for 503 responses
    - Log successful operations at debug, idempotent outcomes at debug, errors at error level
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.1, 10.2, 10.4_

  - [x] 4.2 Write property tests for grant and revoke (Properties 1, 3, 4, 6)
    - **Property 1: Request construction correctness** — verify correct HTTP method, path, and JSON body for grant/revoke
    - **Property 3: Idempotent status codes yield success** — verify 409 on grant and 404 on revoke return success
    - **Property 4: Validation errors propagate message** — verify 400 raises ValidationError with API message
    - **Property 6: Immediate failure on non-retriable errors** — verify non-503/non-idempotent errors fail immediately
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.6, 3.1, 3.3, 3.4, 3.6**

  - [x] 4.3 Implement batch method with chunking
    - Implement `batch()` on `AuthorizationClient`
    - Split operations into chunks of ≤100, preserving order
    - POST each chunk to `/grants/batch`
    - Classify per-operation errors: `conflict`/`not_found` as idempotent success, `service_unavailable` as retriable
    - Raise `ValidationError` on 400 for entire batch
    - Return aggregate `BatchResult` with total, succeeded, failed, and error details
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 4.4 Write property tests for batch operations (Properties 7, 8, 9)
    - **Property 7: Batch chunking respects size limit** — verify ⌈N/100⌉ requests each with ≤100 operations
    - **Property 8: Batch chunking preserves order** — verify concatenation of chunks equals original list
    - **Property 9: Batch result aggregation** — verify aggregate totals across multi-chunk execution
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.7**

  - [x] 4.5 Implement get_user_permissions method
    - Implement `get_user_permissions()` on `AuthorizationClient`
    - GET to `/users/{userId}/permissions` with optional type and relation query params
    - Return typed `UserPermissions` model
    - Retry on 503, raise on other errors
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.6 Implement set_resource_parents method
    - Implement `set_resource_parents()` on `AuthorizationClient`
    - PUT to `/resources/{type}/{resourceId}/parents`
    - Return typed `ResourceParents` model
    - Raise `ValidationError` on 400, retry on 503, raise on other errors
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 4.7 Implement health_check method
    - Implement `health_check()` on `AuthorizationClient`
    - GET to `/health`
    - Return `HealthResult` on 200
    - Return `HealthResult(status="unhealthy")` on 503 (no exception)
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.8 Write property tests for query, parents, and retry (Properties 1, 5, 6)
    - **Property 1: Request construction correctness** — verify correct method, path, and body for get_user_permissions and set_resource_parents
    - **Property 5: Retry on 503 with exponential backoff** — verify retry count and delay pattern, then ServiceUnavailableError
    - **Property 6: Immediate failure on non-retriable errors** — verify non-503 errors fail immediately for query/parents
    - **Validates: Requirements 5.1, 5.3, 5.4, 6.1, 6.4, 6.5, 8.1, 8.2, 8.4**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement factory and response parsing
  - [x] 6.1 Implement factory function
    - Create `common/src/python/authorization/factory.py`
    - Implement `create_authorization_client()` that resolves base URL from parameter or `AUTHORIZATION_API_URL` env var
    - Raise `ConfigurationError` if no URL resolvable
    - Instantiate `SigV4Transport` and return configured `AuthorizationClient`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 6.2 Write property tests for response model round-trip and parse errors (Properties 2, 10)
    - **Property 2: Response model round-trip** — verify serialize-then-parse produces equivalent model for all response types
    - **Property 10: Malformed response raises ParseError with raw content** — verify non-conforming JSON raises ParseError with original bytes
    - **Validates: Requirements 9.2, 9.3**

  - [x] 6.3 Wire up package exports
    - Update `common/src/python/authorization/__init__.py` to export public API
    - Export: `AuthorizationClient`, `create_authorization_client`, all models, all exceptions, `HttpTransport`, `HttpResponse`
    - Ensure the package is importable as `from authorization import ...`
    - _Requirements: 11.2_

- [x] 7. Integration and unit tests
  - [x] 7.1 Write unit tests for client instantiation and configuration
    - Test explicit URL parameter, env var fallback, and missing URL raises ConfigurationError
    - Test default and custom max_retries/base_backoff values
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 7.2 Write unit tests for health check and logging behavior
    - Test health check request construction and response parsing
    - Test 503 on health returns unhealthy result (no exception)
    - Test logging: debug for success, warning for retry, error for failures
    - _Requirements: 7.1, 7.2, 7.3, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 7.3 Write unit tests for SigV4Transport signing
    - Test that SigV4Transport produces valid Authorization headers
    - Use botocore test utilities or moto for credential mocking
    - _Requirements: 1.4_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All test tasks are enabled and required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The mock transport pattern (inject a test double for `HttpTransport`) enables all property tests to run without network calls
- Test directory uses `authorization_test` suffix per project conventions to avoid namespace conflicts

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["4.1", "4.3", "4.5", "4.6", "4.7"] },
    { "id": 4, "tasks": ["4.2", "4.4", "4.8"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["6.3"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
