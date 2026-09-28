# Implementation Plan: Authorization API Structured Resource Migration

## Overview

This is a **targeted migration** of the existing authorization client library
(`common/src/python/authorization/`) and auth sync orchestration
(`common/src/python/authorization_sync/`) to the structured `resource` contract.
Every task edits an existing file in place — no new modules, no renamed classes.

The implementation order follows the design's dependency chain: shared models
first (nothing works until requests are accepted), then write-request
construction in the client, then `DesiredGrant`/translator, then response
parsing, then the diff, and finally the `build_resource_id` disposition plus
migrating existing flat-shape tests. Within each wave, source changes come first
and their tests come last; shared code (models) precedes its consumers (client,
translator, sync_service).

Test directories are `_test`-suffixed per repo structure rules:
`common/test/python/authorization_test/` (client + models) and
`common/test/python/authorization_sync_test/` (translator + sync service).

## Tasks

- [x] 1. Correct `ResourceObject` in place to match the API schema
  - [x] 1.1 Rework `ResourceObject` fields and request serialization in `common/src/python/authorization/models.py`
    - Replace the removed `id` field with a required `label: str = Field(min_length=1)`
    - Add `flat_id: str | None = Field(default=None, alias="flatId")` as an optional read-only handle
    - Keep `type`, `name`, and add/confirm optional parent fields `study`, `center`, `community`
    - Set `model_config = ConfigDict(populate_by_name=True, extra="ignore")` so incoming `id` is dropped, never serialized
    - Add a `request_dump()` method that serializes with `by_alias=True, exclude_none=True, exclude={"flat_id"}` so requests never emit `flat_id`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.1_
  - [x] 1.2 Add the per-type parent-field `check_parent_fields` model validator to `ResourceObject`
    - Add a module-level set of organization type names used to recognize organization types
    - Implement `@model_validator(mode="after")` enforcing the per-type combination table: organization type → no parents; `data_pipeline` → (study+center) or (study); `dashboard` → (study+center) or (study) or (community); `page` → (study+center) or (study) or (center) or (community)
    - Raise `ValueError` naming the offending type on violation; leave unknown/forward-compatible types unconstrained beyond the label rule
    - _Requirements: 2.6, 2.7, 2.8, 2.9_
  - [x] 1.3 Write property test for per-type parent-field validation in `common/test/python/authorization_test/test_property_models.py`
    - **Property 7: Parent-field combinations are valid per resource type**
    - **Validates: Requirements 2.5, 2.6, 2.7, 2.8, 2.9**
    - Generate resource types and every parent-field combination; assert construction succeeds iff permitted and rejects with a type-naming error otherwise
  - [ ]* 1.4 Write unit tests for `ResourceObject` field rules in `common/test/python/authorization_test/test_property_models.py`
    - Empty/missing `label` raises a validation error (Req 2.1)
    - Incoming `id` is ignored and absent from serialized output (Req 2.2)
    - `flat_id` populated on parse, excluded from `request_dump()` output (Req 2.3, 2.4)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2. Migrate write-request models and client request construction to structured `resource`
  - [x] 2.1 Embed structured `resource` in the four write-request models in `common/src/python/authorization/models.py`
    - Give `GrantRequest`, `RevokeRequest`, `PermissionCheckRequest` a `resource: ResourceObject` field and a `request_body()`/serialization path that emits `{userId, relation, resource: resource.request_dump()}`
    - Give `BatchOperationModel` a `resource: ResourceObject` field; keep `action`/`user_id`/`relation`
    - Remove the legacy top-level `type`/`resourceId` fields from all four models so they cannot be emitted
    - Remove or narrow `_ResourceObjectValidatorMixin` so its concatenated-length rule no longer applies to these write models (retain only if a non-write model still needs it)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.1, 10.2_
  - [x] 2.2 Add structured fields to the `BatchOperation` domain type in `common/src/python/authorization/models.py`
    - Add `resource_type`, `resource_label`, `relation`, and optional `center`/`study`/`community`; keep `action` and `user_id`
    - _Requirements: 3.5, 10.3_
  - [x] 2.3 Update `grant`/`revoke`/`check_permission` request construction in `common/src/python/authorization/client.py`
    - Change signatures from `(user_id, resource_type, resource_id, relation)` to accept structured identity (discrete parent params or a `ResourceObject`/`DesiredGrant`)
    - Build a `ResourceObject` from `(resource_type, resource_label, center, study, community)` and serialize via `request_body`/`request_dump` — no top-level `type`/`resourceId`, no `flat_id`
    - Reject before any HTTP call when type is missing, label empty, or the parent-field combination is invalid, returning an error naming the missing/invalid component (Req 1.7)
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7_
  - [x] 2.4 Update batch request construction and idempotent 409/404 result construction in `common/src/python/authorization/client.py`
    - `_execute_batch_chunk` builds each `BatchOperationModel` with a `ResourceObject` from the structured `BatchOperation` fields
    - Build synthesized `GrantResult`/`RevokeResult` for idempotent 409 (grant) / 404 (revoke) from the request's structured `ResourceObject`, not from `type`/`resource_id`
    - Leave `_BATCH_CHUNK_SIZE`, `retry_on_503`, and `_IDEMPOTENT_ERROR_CODES` unchanged
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.3, 9.4_
  - [x] 2.5 Write property test that requests carry structured identity and never flat identity in `common/test/python/authorization_test/test_property_grant_revoke.py`
    - **Property 1: Requests carry structured identity and never flat identity**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.3, 2.4**
    - Generate valid Structured Identities; assert serialized `GrantRequest`/`RevokeRequest`/`BatchOperationModel`/`PermissionCheckRequest` payloads contain a `resource` with non-empty `label` and no `flat_id`, top-level `type`, or top-level `resourceId`
  - [ ]* 2.6 Write property test for batch chunking in `common/test/python/authorization_test/test_property_batch.py`
    - **Property 8: Batch chunking preserves order and bounds chunk size**
    - **Validates: Requirements 9.4**
    - Generate operation lists spanning several chunk boundaries; assert each chunk is at most 100 ops and in-order concatenation equals the original list
  - [x] 2.7 Update/extend client unit tests for structured requests and idempotency in `common/test/python/authorization_test/test_client_grant.py`, `test_client_revoke.py`, `test_client_batch.py`
    - Build calls with structured identity; assert structured `resource` payloads with no `flat_id`
    - Assert 409-on-grant and 404-on-revoke are idempotent successes (no retry, no raise) with results built from the structured resource
    - Assert per-op `conflict`/`not_found` excluded from failure count; other codes counted as failures
    - _Requirements: 1.1, 1.2, 1.3, 8.1, 8.2, 8.3, 8.4_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Carry structured identity through `DesiredGrant` and the translator
  - [x] 4.1 Rework `DesiredGrant` to carry the Structured Identity in `common/src/python/authorization_sync/models.py`
    - Keep it a `@dataclass(frozen=True)`; replace the flat `resource_id` with `resource_label` plus optional `center`/`study`/`community`; keep `user_id`, `resource_type`, `relation`
    - Add `__post_init__` raising `ValueError` when `resource_type` or `resource_label` is missing (Req 3.2)
    - Add `identity()` returning `(resource_type, relation, resource_label, center, study, community)`
    - Add `to_resource()` building a `ResourceObject`, and `to_batch_op(action)` building a structured `BatchOperation`
    - _Requirements: 3.1, 3.2, 3.5, 10.3_
  - [x] 4.2 Populate structured fields in `translate()` in `common/src/python/authorization_sync/translator.py`
    - Obtain the label from `build_label_for_resource_prefix` (keep) and construct each `DesiredGrant` with `resource_label`, `resource_type`, and applicable parent fields
    - Set `center` to the center group id (None for general scope), `study` from `StudyAuthorizations` else None, `community=None` (grant path never targets community)
    - Leave inapplicable parent fields None (no placeholders); stop importing/calling `build_resource_id` on the grant path
    - Leave `ACTIVITY_RELATION_MAP`, `validate_activity_relation_map`, `check_assignable` unchanged
    - _Requirements: 3.3, 3.4, 3.5, 9.1, 9.2, 10.3, 10.4_
  - [x] 4.3 Tighten `build_label_for_resource_prefix` unknown-prefix handling in `common/src/python/authorization_sync/resource_ids.py`
    - Map exactly `datatype`→`ingest`, `dashboard`→`dashboard`, `page`→`page`
    - Reject a prefix outside `{datatype, dashboard, page}` with an error indicating an unsupported prefix instead of returning the bare name
    - _Requirements: 3.6, 3.7, 10.4_
  - [ ]* 4.4 Write property test for label split/rejoin round-trip in `common/test/python/authorization_sync_test/test_translator.py`
    - **Property 4: Label split/rejoin round-trip**
    - **Validates: Requirements 3.3, 3.6**
    - Generate labels of form `{kind}-{name}` including the `accepted` special case and hyphenated names; assert split at the first `-` only and rejoin yields the original
  - [x] 4.5 Update/extend translator unit tests for structured `DesiredGrant` in `common/test/python/authorization_sync_test/test_translator.py`
    - Remove the `_build_resource_id` mirror and flat-id assertions; assert structured `DesiredGrant` fields (label + parents) and `identity()` tuple
    - Assert the prefix→kind mapping table (Req 3.6) and unknown-prefix rejection (Req 3.7)
    - _Requirements: 3.2, 3.3, 3.4, 3.6, 3.7_

- [x] 5. Parse responses from the structured `resource`
  - [x] 5.1 Read identity from `resource` in the response models in `common/src/python/authorization/models.py`
    - For `PermissionEntry`, `GrantResult`, `RevokeResult`, `ResourceParents`, `ResourceListItem`, read identity solely from `resource: ResourceObject | None`
    - Remove (or retain only as ignored input) the top-level `resource_id`/`resourceId` alias fields so parsing cannot fall back to them
    - Treat `resource is None` as no Structured Identity (no partial reconstruction); treat `flat_id` as opaque (never split/parse); echo `flat_id` byte-for-byte as a GET `{resourceId}` path segment
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  - [x] 5.2 Update `UserPermissions.to_grants` factory contract in `common/src/python/authorization/models.py`
    - Change the factory signature to `(user_id, resource, relation)` and build grants from `entry.resource` structured fields
    - Skip entries where `entry.resource is None`, logging a catalog-gap warning, and complete successfully
    - _Requirements: 4.1, 4.3, 6.1, 6.4_
  - [ ]* 5.3 Write/extend example test for verbatim `flat_id` echo on GET reads in `common/test/python/authorization_test/test_client_parents.py`
    - Assert a received `flat_id` is echoed unmodified as the `{resourceId}` path segment
    - _Requirements: 4.5, 4.6_
  - [x] 5.4 Update response-parsing unit tests to read from structured `resource` in `common/test/python/authorization_test/test_client_query.py`, `test_property_models.py`
    - Assert identity read from `resource`; assert no fallback to a top-level `resourceId`; assert `resource is None` yields no identity
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6. Key the diff on the Structured Identity Tuple in the sync service
  - [x] 6.1 Build `DesiredGrant` from `entry.resource` in `_grants_in_scope` and the `to_grants` factory in `common/src/python/authorization_sync/sync_service.py`
    - In `_grants_in_scope`, skip entries failing `_entry_in_scope` (covers `resource is None` and out-of-scope), then build `DesiredGrant` from `resource.label`, `resource.center`, `resource.study`, `resource.community`
    - Pass the new `(user_id, resource, relation)` factory to `to_grants` so the full current set is built from structured fields, never a flat id
    - Keep `grants_to_add = desired - current` and `grants_to_revoke = in_scope_current - desired`; the tuple key follows from `DesiredGrant` equality
    - _Requirements: 4.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.6_
  - [x] 6.2 Preserve scope-aware revocation in `_entry_in_scope` in `common/src/python/authorization_sync/sync_service.py`
    - Confirm/keep: return False when `resource is None`, when `resource.community is not None`, or when `resource.center` does not exactly (case-sensitive) equal the reconciled center group id
    - Read `center`/`community` directly from the structured `resource`; never parse from a flat string
    - Preserve per-type query loop, batch apply, and partial-failure event reporting
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 8.5, 8.6, 9.5, 9.6_
  - [x] 6.3 Write property test that the diff round-trips on structured identity independent of `flat_id` in `common/test/python/authorization_sync_test/test_multi_study_sync.py`
    - **Property 2: The diff round-trips on structured identity, independent of flat_id**
    - **Validates: Requirements 4.1, 4.2, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.6**
    - Build the current set from the desired set with arbitrary/differing `flat_id`s; assert `grants_to_add` and `grants_to_revoke` are both empty
  - [x] 6.4 Write property test that a None-resource entry is never revoked in `common/test/python/authorization_sync_test/test_multi_study_sync.py`
    - **Property 3: An entry with no structured resource is never revoked**
    - **Validates: Requirements 4.3, 6.1, 6.2, 6.3, 6.4, 7.5**
    - Generate entries with `resource is None`; assert they never appear in add or revoke and the diff completes successfully
  - [x] 6.5 Write property test that community-scoped entries are never revoked in `common/test/python/authorization_sync_test/test_multi_study_sync.py`
    - **Property 5: Community-scoped entries are never revoked**
    - **Validates: Requirements 7.3**
    - Generate entries with non-null `resource.community`; assert they never appear in `grants_to_revoke`
  - [x] 6.6 Write property test that revoke candidacy is center-keyed in `common/test/python/authorization_sync_test/test_multi_study_sync.py`
    - **Property 6: Revoke candidacy is center-keyed**
    - **Validates: Requirements 7.1, 7.2, 7.4**
    - Generate entries with non-null `resource` and no `community`; assert an entry is a revoke candidate iff `resource.center` equals (case-sensitive) the reconciled center group id
  - [x] 6.7 Update sync-service diff unit tests to key on the Structured Identity Tuple in `common/test/python/authorization_sync_test/test_fault_isolation.py`, `test_pipeline_integration.py`, `test_sync_profile.py`
    - Re-key diff assertions on the tuple instead of flat `resource_id`; confirm one-request-per-type wiring (Req 8.5, 8.6), constancy of `_SYNC_RESOURCE_TYPES`/`ACTIVITY_RELATION_MAP` (Req 9.1, 9.2), 503 retry (Req 9.3), and partial-failure reporting (Req 9.5)
    - _Requirements: 8.5, 8.6, 9.1, 9.2, 9.3, 9.5, 9.6_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Dispose of `build_resource_id` and reconcile the seed path
  - [x] 8.1 Confirm `build_resource_id` retention and remove it from the grant path
    - Verify `build_resource_id` still has a live consumer via the seed path in `common/src/python/projects/study_mapping.py` (`__auth_resource_id*`); per Req 10.5 retain it unchanged
    - Ensure `translator.py` no longer imports or calls `build_resource_id`; keep the `authorization_sync/__init__.py` re-export for the seed path's public surface
    - Leave `common/src/python/projects/hierarchy_seeder.py` and its `set_resource_parents` path-segment usage unchanged (seed path not migrated)
    - _Requirements: 10.4, 10.5_
  - [ ]* 8.2 Verify seed-path tests still pass in `common/test/python/projects_test/test_property_hierarchy_seeder.py`
    - Confirm the seeder tests pass unchanged since `build_resource_id` is retained and the parents endpoint body is not migrated
    - _Requirements: 10.4, 10.5_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (test sub-tasks) and are not implemented by
  the executing agent when marked optional; core implementation sub-tasks are
  always implemented.
- Each task references specific requirements for traceability; property tasks
  reference the design's property number.
- This is an in-place migration: no new modules or renamed classes. All paths
  reference existing files.

### Quality-check strategy (per task-execution steering)

- Subagents run **targeted** checks on only the code they modified:
  - Source tasks: `pants_fix` (file scope) + `pants_check` (directory scope)
  - Test tasks: `pants_fix` (file scope) + `pants_test` (file scope)
  - Do NOT run a full quality check per subtask.
- The `post-task-quality-check` hook runs `full_quality_check` (fix → lint →
  check → test on all code) at wave boundaries (parent/top-level task
  completion), catching cross-file type errors and regressions.
- The `tailor-on-file-create` hook runs `pants_tailor` when new `.py` files are
  created (rare here — this migration edits existing files in place).
- Pre-existing mypy/lint errors in unrelated files are noted but do not block
  progress; only failures in code modified by this spec require fixing.
- Log each subagent's activity to
  `.kiro/specs/authorization-api-structured-resource-migration/execution-log.md`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4"] },
    { "id": 4, "tasks": ["2.5", "2.6", "2.7"] },
    { "id": 5, "tasks": ["4.1", "4.3"] },
    { "id": 6, "tasks": ["4.2"] },
    { "id": 7, "tasks": ["4.4", "4.5"] },
    { "id": 8, "tasks": ["5.1", "5.2"] },
    { "id": 9, "tasks": ["5.3", "5.4"] },
    { "id": 10, "tasks": ["6.1", "6.2"] },
    { "id": 11, "tasks": ["6.3", "6.4", "6.5", "6.6", "6.7"] },
    { "id": 12, "tasks": ["8.1"] },
    { "id": 13, "tasks": ["8.2"] }
  ]
}
```
