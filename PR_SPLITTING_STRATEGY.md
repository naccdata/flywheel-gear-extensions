# PR Splitting Strategy for Event Logging Feature Branch

## Overview

The `feature/add-event-logging` branch contains 242 commits affecting 138 files with ~18,000 lines of changes. This document outlines a strategy to split this massive PR into smaller, more reviewable chunks while minimizing impact on other team members' work.

## Current Branch Stats

- **Branch**: `feature/add-event-logging`
- **Commits**: 242 commits ahead of main
- **Files Changed**: 138 files
- **Lines Added**: ~17,948 additions, 898 deletions
- **Key Areas**: Event logging infrastructure, form scheduler refactoring, identifier lookup refactoring, common library extensions

## Splitting Strategy (Team-Safe Approach)

### PR #1: Infrastructure & Tooling Changes
**Branch**: `infra/dev-container-improvements`
**Risk Level**: Low
**Team Impact**: Minimal

**Files**:
- `bin/` directory scripts (dev container management)
- `.vscode/` configuration files
- Build configuration updates (`mypy.lock`, `python-default.lock`, `requirements.txt`)
- `ruff.toml` configuration changes
- `.kiro/steering/tech.md` updates

**Why First**: These are infrastructure improvements that don't affect business logic or APIs. Safe to merge without impacting ongoing development.

### PR #2: Common Library Additions (Additive Only)
**Branch**: `feat/common-library-extensions`
**Risk Level**: Low
**Team Impact**: Zero (purely additive)

**Files**:
- **New packages** (no existing code modified):
  - `common/src/python/event_logging/` (complete new package)
  - `common/src/python/metrics/` (complete new package)
- **New S3 interface**: `common/src/python/s3/s3_bucket.py` (enhanced S3 operations)
- **New test utilities**:
  - `common/src/python/test_mocks/mock_event_logging.py`
- **Type stubs enhancements**: `mypy-stubs/src/python/flywheel/models/`
- **Complete test coverage**: Tests for all new packages

**Why Second**: Purely additive changes. Existing code continues to work unchanged. Provides foundation for later PRs.

**Note**: Some originally planned items (error_logging, center_validator, mock_factories, strategies) were moved to later PRs due to dependencies on nacc-common changes not yet available.

### PR #3: NACC Common Library - Backward Compatible Updates
**Branch**: `feat/nacc-common-v2.1.0`
**Risk Level**: Low-Medium
**Team Impact**: Minimal (backward compatible)

**Files**:
- `nacc-common/` package updates
- `nacc-common/src/python/nacc_common/error_models.py` (enhanced, backward compatible)
- `nacc-common/src/python/nacc_common/qc_report.py` (enhanced, backward compatible)
- `nacc-common/src/python/nacc_common/visit_submission_status.py` (new methods)
- Version bump to v2.1.0
- `docs/nacc_common/CHANGELOG.md`

**Why Third**: Establishes new APIs while maintaining backward compatibility. Existing gear code continues to work.

### PR #4: Gear Updates - Coordinated Atomic Changes
**Branch**: `feat/gear-updates-event-logging`
**Risk Level**: Medium
**Team Impact**: High (coordinate with team)

**Files** (All gear updates together):
- `gear/form_qc_checker/`
- `gear/form_qc_coordinator/`
- `gear/form_screening/`
- `gear/form_transformer/`
- `gear/csv_center_splitter/`
- `gear/gather_submission_status/`
- `gear/identifier_provisioning/`
- `gear/participant_transfer/`
- `gear/pull_metadata/`
- `gear/redcap_fw_transfer/`
- `gear/regression_curator/`

**Why Together**: 
- Prevents partial integration states
- Ensures all gears work with new common libraries
- Single coordination point with team
- Atomic update reduces conflict window

**Team Coordination Required**:
- Announce changes in advance
- Short merge window (1-2 days)
- Coordinate with developers working on these gears

### PR #5: Identifier Lookup Complete Refactor
**Branch**: `feat/identifier-lookup-refactor`
**Risk Level**: High
**Team Impact**: Medium (single gear focus)

**Files**:
- Complete `gear/identifier_lookup/` refactoring
- All property-based tests for identifier lookup
- Related common library changes specific to identifier lookup
- `gear/identifier_lookup/REFACTORING_BACKUP.md`

**Why Fifth**: Complete refactoring of single gear with extensive testing. Isolated impact.

### PR #6: Form Scheduler Event Logging
**Branch**: `feat/form-scheduler-event-logging`
**Risk Level**: High
**Team Impact**: Medium (single gear focus)

**Files**:
- Complete `gear/form_scheduler/` event logging implementation
- Event accumulator implementations
- Integration and property-based tests
- Form scheduler documentation updates

**Why Sixth**: Major feature implementation with comprehensive testing. Single gear focus.

### PR #7: Documentation & Specifications
**Branch**: `docs/event-logging-specs`
**Risk Level**: Low
**Team Impact**: None

**Files**:
- `.kiro/specs/` directories (all specification documents)
- `docs/form_scheduler/event-logging.md`
- `docs/identifier_lookup/index.md`
- Design and requirements documentation

**Why Last**: Pure documentation changes. Easy to review independently.

## Implementation Steps

### 1. Create Feature Branches
```bash
# From main branch
git checkout main
git pull origin main

# Create each branch
git checkout -b infra/dev-container-improvements main
git checkout -b feat/common-library-extensions main
git checkout -b feat/nacc-common-v2.1.0 main
git checkout -b feat/gear-updates-event-logging main
git checkout -b feat/identifier-lookup-refactor main
git checkout -b feat/form-scheduler-event-logging main
git checkout -b docs/event-logging-specs main
```

### 2. Cherry-Pick Commits
Use `git log --oneline main..feature/add-event-logging` to identify commits for each PR, then cherry-pick them to appropriate branches.

### 3. Test Each Branch
Ensure each branch builds and passes tests independently:
```bash
./bin/start-devcontainer.sh
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
./bin/exec-in-devcontainer.sh pants test ::
```

### 4. Submit PRs in Order
Submit PRs with clear dependency notes and merge in sequence.

## Alternative Approaches

### Option A: Freeze-and-Coordinate
1. Coordinate with team - announce upcoming changes
2. Create all PRs simultaneously but merge in order
3. Short merge window (1-2 days) to minimize conflicts

### Option B: Feature Flag Approach
1. Add feature flags to control new behavior
2. Merge changes with flags disabled
3. Enable flags incrementally per gear
4. Remove flags in final cleanup PR

## Risk Mitigation

- **Communication**: Announce strategy to team in advance
- **Testing**: Each PR must pass full test suite
- **Rollback Plan**: Each PR can be reverted independently
- **Dependencies**: Clear documentation of PR dependencies
- **Coordination**: Especially important for PR #4 (gear updates)

## Benefits

1. **Reviewable Chunks**: Each PR focuses on specific functionality
2. **Team Safety**: Minimizes disruption to ongoing development
3. **Atomic Updates**: Prevents partial integration states
4. **Clear Dependencies**: Logical progression of changes
5. **Rollback Safety**: Issues can be isolated to specific PRs

---

**Created**: December 22, 2025
**Branch**: `feature/add-event-logging`
**Status**: Planning Phase