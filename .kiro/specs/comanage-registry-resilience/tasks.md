# Implementation Plan: COManage Registry Resilience

## Overview

Incremental implementation of domain-aware fallback lookup, name-based duplicate detection, incomplete claim state, multi-email skeleton creation, wrong-IdP detection, and near-miss diagnostic events. Tasks are ordered so foundational pieces (config models, RegistryPerson state methods) come before the components that depend on them (UserRegistry indexes, ActiveUserProcess changes, FailureAnalyzer changes, gear wiring).

## Tasks

- [x] 1. Create domain configuration models
  - [x] 1.1 Create `common/src/python/users/domain_config.py` with `Domain` annotated type, `canonicalize_domain`, `ParentChildMapping`, `AffiliatedDomainGroup`, and `DomainRelationshipConfig`
    - Implement `canonicalize_domain` AfterValidator (lowercase, strip, remove trailing dots)
    - Implement `ParentChildMapping(BaseModel)` with `child: Domain` and `parent: Domain`
    - Implement `AffiliatedDomainGroup(BaseModel)` with `name: str`, `domains: list[Domain]`, and `at_least_two_domains` field validator
    - Implement `DomainRelationshipConfig(BaseModel)` with `parent_child: list[ParentChildMapping]`, `affiliated_groups: list[AffiliatedDomainGroup]`
    - Implement `resolve_parent(domain)` — check explicit parent_child mappings, fall back to last-two-segments extraction
    - Implement `get_domain_group(domain)` — return union of domain itself, parent domain siblings, and affiliated domains
    - Implement `validate_no_contradictions` model_validator (no domain in multiple affiliated groups)
    - Implement `build_lookup_indexes` model_validator to build internal dicts for efficient lookup
    - Add BUILD file entry for the new module
    - _Requirements: 1.4, 1.6, 9.1, 9.3, 9.5, 9.6_

  - [x] 1.2 Add `InstitutionalIdPMapping`, `IdPDomainConfig` to `domain_config.py`
    - Implement `InstitutionalIdPMapping(BaseModel)` with `domain: Domain` and `idp_name: str`
    - Implement `IdPDomainConfig(BaseModel)` with `institutional_idp: list[InstitutionalIdPMapping]`, `fallback_domains: list[Domain]`, `fallback_idp: str = "ORCID"`
    - Implement `get_expected_idp(domain, domain_config)` — canonicalize, resolve subdomains via DomainRelationshipConfig, return IdP name or None
    - Implement `is_fallback_domain(domain, domain_config)` — canonicalize, check fallback_domains and parent resolution
    - Implement `validate_no_overlap` model_validator (no domain in both institutional_idp and fallback_domains)
    - Implement `build_lookup_indexes` model_validator for efficient lookup
    - _Requirements: 8.5, 9.1, 9.4, 9.6_

  - [x] 1.3 Add `default_name_normalizer` helper function to `domain_config.py`
    - Implement `default_name_normalizer(name: str) -> str` — lowercase, strip, collapse whitespace
    - _Requirements: 5.5_

  - [x] 1.4 Write unit tests for configuration models in `common/test/python/user_test/test_domain_config.py`
    - Test `canonicalize_domain` with uppercase, whitespace, trailing dots
    - Test `ParentChildMapping` and `AffiliatedDomainGroup` validation
    - Test `DomainRelationshipConfig.resolve_parent()` with explicit mappings and default extraction
    - Test `DomainRelationshipConfig.get_domain_group()` with parent-child and affiliated domains
    - Test `IdPDomainConfig.get_expected_idp()` and `is_fallback_domain()`
    - Test validation rejects contradictions (domain in multiple groups, domain in both institutional and fallback)
    - Test `default_name_normalizer` with various inputs
    - _Requirements: 9.1, 9.3, 9.5, 9.6_

  - [x] 1.5 Write property tests for configuration models (P9, P10, P11)
    - **Property 9: Configuration round-trip and canonicalization** — Validates: Requirements 9.1
    - **Property 10: Default domain resolution** — Validates: Requirements 9.5
    - **Property 11: Configuration validation rejects contradictions** — Validates: Requirements 9.6
    - Add to `common/test/python/user_test/test_domain_config.py`
    - Use Hypothesis to generate valid config instances, serialize, deserialize, assert equivalence
    - Use Hypothesis to generate random domain strings with 2-5 segments for default resolution
    - Use Hypothesis to generate configs with intentional contradictions and assert `ValidationError`

- [x] 2. Add RegistryPerson state methods and multi-email creation
  - [x] 2.1 Add `is_incomplete_claim()` and `is_unclaimed()` methods to `RegistryPerson` in `user_registry.py`
    - `is_incomplete_claim()` returns True iff record has oidcsub identifier but no verified email
    - `is_unclaimed()` returns True iff record has no oidcsub identifier
    - Existing `is_claimed()` remains unchanged
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 2.2 Modify `RegistryPerson.create()` to accept `email: str | list[str]` in `user_registry.py`
    - When a list is provided, create one `EmailAddress(type="official", verified=True)` per entry
    - When a single string is provided, wrap in list internally (backward compatible)
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 2.3 Update existing tests in `common/test/python/user_test/test_registry_person_status.py`
    - Add tests for `is_incomplete_claim()` with oidcsub but no verified email
    - Add tests for `is_unclaimed()` with no oidcsub identifier
    - Verify `is_claimed()` behavior is unchanged
    - Verify trichotomy: exactly one of the three methods returns True for any active record
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 2.4 Update existing tests in `common/test/python/user_test/test_registry_person_email.py`
    - Add tests for `RegistryPerson.create()` with a list of emails
    - Verify each email produces an `EmailAddress` with type="official"
    - Verify single-string backward compatibility
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 2.5 Write property test for claim state trichotomy (P3)
    - **Property 3: Claim state trichotomy** — Validates: Requirements 3.1, 3.2, 3.3
    - Create `common/test/python/user_test/test_registry_person_state.py`
    - Use Hypothesis to generate CoPersonMessage objects with random combinations of status, verified emails, and oidcsub identifiers
    - Assert exactly one of `is_claimed()`, `is_incomplete_claim()`, `is_unclaimed()` is True for any active RegistryPerson

  - [x] 2.6 Write property test for multi-email skeleton creation (P4)
    - **Property 4: Multi-email skeleton creation** — Validates: Requirements 4.1, 4.2
    - Use Hypothesis to generate random lists of 1-5 email strings
    - Assert `RegistryPerson.create(email=emails)` produces exactly one EmailAddress per input, each with type="official"

- [x] 3. Add new UserRegistry indexes and lookup methods
  - [x] 3.1 Fix registry-ID indexing to include records without email in `UserRegistry.__add_person()` in `user_registry.py`
    - Move `registry_id` indexing outside the `if person.email_addresses` branch so any record with a registry ID is added to `__registry_map_by_id`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Add `__parent_domain_map` index and `get_by_parent_domain()` method to `UserRegistry` in `user_registry.py`
    - Add `DomainCandidate` dataclass with `person`, `matched_email`, `query_domain`, `candidate_domain`, `parent_domain` fields
    - Accept `domain_config: DomainRelationshipConfig | None = None` in `UserRegistry.__init__()`
    - In `__add_person`, for each email address, extract parent domain via `domain_config.resolve_parent()` and add to `__parent_domain_map`
    - Implement `get_by_parent_domain(email)` — extract parent domain from query email, return `list[DomainCandidate]` with match context
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [x] 3.3 Add `__name_map` index and `get_by_name()` method to `UserRegistry` in `user_registry.py`
    - Accept `name_normalizer: Callable[[str], str] | None = None` in `UserRegistry.__init__()`
    - In `__add_person`, if record has primary_name, normalize and add to `__name_map`
    - Implement `get_by_name(full_name)` — normalize query name, return `list[RegistryPerson]`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.4 Write unit tests for new indexes and lookup methods in `common/test/python/user_test/test_user_registry_indexes.py`
    - Test `find_by_registry_id()` returns records without email
    - Test `get_by_parent_domain()` with explicit parent-child mappings and default extraction
    - Test `get_by_parent_domain()` returns `DomainCandidate` with correct context fields
    - Test `get_by_name()` with normalized name matching
    - Test `get_by_name()` returns all matching records regardless of claim state
    - Test backward compatibility: `UserRegistry` without `domain_config` or `name_normalizer`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 5.1, 5.2, 5.3_

  - [x] 3.5 Write property test for registry indexing invariant (P2)
    - **Property 2: Registry indexing invariant** — Validates: Requirements 2.1, 2.3
    - Add to `common/test/python/user_test/test_user_registry_indexes.py`
    - Use Hypothesis to generate CoPersonMessage objects with random combinations of emails, registry IDs, and oidcsub identifiers
    - Assert: `find_by_registry_id(id)` returns record iff it has that registry ID; `get(email)` contains record iff it has that email

  - [ ]* 3.6 Write property test for domain-aware lookup (P1)
    - **Property 1: Domain-aware lookup returns correct candidates with context** — Validates: Requirements 1.1, 1.2, 1.3, 1.6
    - Add to `common/test/python/user_test/test_user_registry_indexes.py`
    - Use Hypothesis to generate random email addresses with related domains and random DomainRelationshipConfig
    - Assert all returned DomainCandidate objects have matching parent_domain and non-empty context fields

  - [ ]* 3.7 Write property test for name-based index completeness (P5)
    - **Property 5: Name-based index completeness** — Validates: Requirements 5.1, 5.2, 5.3, 5.4
    - Add to `common/test/python/user_test/test_user_registry_indexes.py`
    - Use Hypothesis to generate records with random names including duplicates and whitespace variations
    - Assert `get_by_name(normalized_name)` returns all matching records and no non-matching records

- [x] 4. Add new event categories and update ActiveUserProcess
  - [x] 4.1 Add new event categories to `EventCategory` enum in `event_models.py`
    - Add `DOMAIN_NEAR_MISS = "Domain Near-Miss"`
    - Add `NAME_NEAR_MISS = "Name Near-Miss"`
    - Add `COMBINED_NEAR_MISS = "Combined Signal Near-Miss"`
    - Add `WRONG_IDP_SELECTION = "Wrong IdP Selection"`
    - _Requirements: 7.1, 7.2, 7.3, 8.2_

  - [x] 4.2 Add `domain_config` and `idp_config` optional parameters to `UserProcessEnvironment.__init__()` in `user_process_environment.py`
    - Add `domain_config: DomainRelationshipConfig | None = None` and `idp_config: IdPDomainConfig | None = None` with corresponding properties
    - Existing callers without these parameters continue to work (backward compatible)
    - _Requirements: 9.1_

  - [x] 4.3 Update `ActiveUserProcess.visit()` in `user_processes.py` to add domain-aware and name-based fallback steps
    - After bad-claim check and before skeleton creation, call `get_by_parent_domain(entry.auth_email)` and `get_by_name(entry.full_name)`
    - If any candidates found, emit near-miss events via `__emit_near_miss_events()` and return (do NOT create skeleton)
    - If no candidates, proceed to create skeleton as today
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 4.4 Implement `__emit_near_miss_events()` helper in `ActiveUserProcess` in `user_processes.py`
    - Determine category: `COMBINED_NEAR_MISS` if any candidate appears in both domain and name results, `DOMAIN_NEAR_MISS` if only domain candidates, `NAME_NEAR_MISS` if only name candidates
    - Include user context (email, name, center ID) and candidate record details (email, name, registry ID) in the event
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 4.5 Modify `__add_to_registry()` in `ActiveUserProcess` to pass both contact email and auth email to `RegistryPerson.create()`
    - When `entry.email` and `entry.auth_email` are both available and distinct, pass `email=[entry.auth_email, entry.email]`
    - When they are the same or contact email is missing, pass single email (backward compatible)
    - _Requirements: 4.4_

  - [x] 4.6 Update existing tests in `common/test/python/user_test/test_event_models.py`
    - Add tests for new `EventCategory` values (`DOMAIN_NEAR_MISS`, `NAME_NEAR_MISS`, `COMBINED_NEAR_MISS`, `WRONG_IDP_SELECTION`)
    - Verify new categories serialize correctly in `UserProcessEvent`
    - _Requirements: 7.1, 7.2, 7.3, 8.2_

  - [x] 4.7 Update existing tests in `common/test/python/user_test/test_user_process_integration.py`
    - Add tests for `ActiveUserProcess.visit()` with domain-aware candidates found (verify near-miss event emitted, no skeleton created)
    - Add tests for `ActiveUserProcess.visit()` with name-based candidates found (verify near-miss event emitted, no skeleton created)
    - Add tests for `ActiveUserProcess.visit()` with combined candidates (verify combined near-miss event)
    - Add tests for `ActiveUserProcess.visit()` with no candidates (verify skeleton still created)
    - Add tests for `__add_to_registry()` passing multiple emails when both contact and auth email are distinct
    - Update `mock_environment` fixture to include `get_by_parent_domain` and `get_by_name` mock methods
    - _Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 4.4_

  - [x] 4.8 Update `common/test/python/user_test/conftest.py` fixtures if needed
    - Add or update fixtures for `UserProcessEnvironment` to support `domain_config` and `idp_config` parameters
    - _Requirements: 9.1_

  - [ ]* 4.9 Write property test for skeleton creation decision (P6)
    - **Property 6: Skeleton creation decision** — Validates: Requirements 6.1, 6.2, 6.3
    - Create `common/test/python/user_test/test_active_user_process.py`
    - Use Hypothesis to generate ActiveUserEntry objects with mocked registry returning various combinations of empty/non-empty results
    - Assert skeleton created iff all lookups return empty; diagnostic event emitted iff any candidate found

  - [ ]* 4.10 Write property test for near-miss event categorization (P7)
    - **Property 7: Near-miss event categorization** — Validates: Requirements 7.1, 7.2, 7.3, 7.4
    - Use Hypothesis to generate combinations of domain candidates and name candidates with overlapping/non-overlapping persons
    - Assert correct category assignment and event content

- [x] 5. Update FailureAnalyzer for wrong-IdP detection
  - [x] 5.1 Extend `FailureAnalyzer.__init__()` to accept `idp_config` and `domain_config` in `failure_analyzer.py`
    - Add `idp_config: IdPDomainConfig | None = None` and `domain_config: DomainRelationshipConfig | None = None` parameters
    - When configs are not provided, fall back to existing ORCID-name-based detection (backward compatible)
    - _Requirements: 8.1, 8.5_

  - [x] 5.2 Implement `_detect_wrong_idp()` method in `FailureAnalyzer` in `failure_analyzer.py`
    - Extract email domain from skeleton email, resolve to parent domain via DomainRelationshipConfig
    - Look up expected IdP via IdPDomainConfig.get_expected_idp()
    - Check if claim was made through a different IdP (e.g., fallback IdP) by inspecting org_identities
    - If wrong IdP detected, return `UserProcessEvent` with `WRONG_IDP_SELECTION` category and actionable message
    - If domain is in fallback_domains, return None (correct IdP usage)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 5.3 Update `detect_incomplete_claim()` in `FailureAnalyzer` to call `_detect_wrong_idp()` when configs are available
    - Before falling through to generic incomplete-claim detection, check for wrong-IdP scenario
    - If `_detect_wrong_idp()` returns an event, use that instead of the generic one
    - Preserve existing behavior when configs are not provided
    - _Requirements: 8.1, 8.2_

  - [x] 5.4 Update existing tests in `common/test/python/user_test/test_failure_analyzer.py`
    - Add tests for `FailureAnalyzer` initialization with `idp_config` and `domain_config`
    - Add tests for `_detect_wrong_idp()` when domain maps to institutional IdP and claim was via fallback IdP
    - Add tests for `_detect_wrong_idp()` when domain is in fallback_domains (should not flag)
    - Add tests for `detect_incomplete_claim()` integration with wrong-IdP detection
    - Verify backward compatibility: `FailureAnalyzer` without config parameters falls back to existing behavior
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [ ]* 5.5 Write property test for wrong-IdP detection (P8)
    - **Property 8: Wrong-IdP detection** — Validates: Requirements 8.1, 8.2, 8.3
    - Create `common/test/python/user_test/test_failure_analyzer_props.py`
    - Use Hypothesis to generate email domains, IdP configs, and incomplete claim records with various org identities
    - Assert `WRONG_IDP_SELECTION` emitted iff domain maps to institutional IdP and claim was via different IdP; not emitted for fallback domains

- [x] 6. Wire configuration into gear entry point
  - [x] 6.1 Add `domain_config_file` optional file input to `gear/user_management/src/docker/manifest.json`
    - Add input with `"base": "file"`, `"optional": true`, `"type": {"enum": ["source code"]}`
    - _Requirements: 9.2_

  - [x] 6.2 Add `__get_domain_config()` and `__get_idp_config()` methods to `UserManagementVisitor` in `run.py`
    - Follow the same pattern as `__get_auth_map()`: read file path from GearContext, `load_from_stream`, `model_validate`
    - Parse a single YAML file containing both `domain_relationship` and `idp_domain` sections, or handle them as separate top-level keys
    - Return `(DomainRelationshipConfig, IdPDomainConfig)` tuple, or defaults if file not provided
    - _Requirements: 9.1, 9.2, 9.5_

  - [x] 6.3 Update `UserManagementVisitor.run()` to pass configs to `UserRegistry`, `UserProcessEnvironment`, and `FailureAnalyzer` in `run.py`
    - Pass `domain_config` to `UserRegistry` constructor
    - Pass `domain_config` and `idp_config` to `UserProcessEnvironment` constructor
    - Ensure `FailureAnalyzer` receives configs via the environment
    - _Requirements: 9.1_

## Notes

- Tasks marked with `*` are optional property-based tests that can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document (P1-P11)
- All new constructor parameters are optional with `None` defaults for backward compatibility
- The implementation language is Python, matching the existing codebase and design document

## Development Environment & Conventions

### Build System: Use the kiro-pants-power

All build, test, lint, and type-check commands MUST be run via the `kiro-pants-power` MCP tools — NOT via shell scripts or direct bash commands. The power automatically manages the devcontainer lifecycle.

To use the power: `kiroPowers action="use", powerName="kiro-pants-power", serverName="pants-devcontainer-power", toolName=<tool>, arguments={...}`

Available tools and their intent-based parameters:
- `pants_fix` — Format code (always run first). Args: `scope` ("all", "directory", "file"), `path` (for directory/file scope)
- `pants_lint` — Run linters. Same args as above.
- `pants_check` — Type check with mypy. Same args as above.
- `pants_test` — Run tests. Same args plus optional `test_filter` for pytest-style name filtering.
- `pants_package` — Build packages. Same args as fix/lint/check.

Example — run tests on a specific directory:
```
kiroPowers action="use", powerName="kiro-pants-power", serverName="pants-devcontainer-power", toolName="pants_test", arguments={"scope": "directory", "path": "common/test/python/user_test"}
```

Example — fix formatting on a single file:
```
kiroPowers action="use", powerName="kiro-pants-power", serverName="pants-devcontainer-power", toolName="pants_fix", arguments={"scope": "file", "path": "common/src/python/users/user_registry.py"}
```

### Quality Check Workflow

After implementing code changes, always run in this order:
1. `pants_fix` on modified files/directories
2. `pants_lint` on modified files/directories
3. `pants_check` on modified files/directories
4. `pants_test` on relevant test files/directories

### Coding Conventions

Refer to the workspace steering files in `.kiro/steering/` for full details. Key points:

- **Imports**: All imports at the top of Python files, immediately after the module docstring. No scattered imports.
- **Line length**: 88 characters (Ruff enforced)
- **Indent**: 4 spaces
- **Type checking**: mypy with Pydantic plugin. Use type annotations everywhere.
- **Test directory naming**: Test directories use `_test` suffix (e.g., `user_test/`) to avoid namespace conflicts with source packages.
- **Test style**: Test public interfaces, not private members. Use reusable mock fixtures in `conftest.py`. Use property-based testing (Hypothesis) for correctness properties.
- **Dependency injection over flags**: Prefer strategy patterns over boolean flag parameters.
- **Gear architecture**: Keep Flywheel context in `run.py`, business logic in `main.py`. Pass structured data (Pydantic models), not many simple args.
- **No version bumps**: Do not automatically bump version numbers or add changelog entries.
