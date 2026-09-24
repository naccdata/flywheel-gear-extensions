# Task Execution & Quality Check Strategy

## Overview

When executing spec tasks, quality checks should be layered to balance correctness with efficiency. Running a full codebase check after every subtask is wasteful — instead, use targeted checks per task and full checks at wave boundaries.

## Quality Check Layers

### Layer 1: Subagent Targeted Checks (per subtask)

Each subagent executing a task should run minimal, targeted checks on the code it modified:

- **Source code tasks**: `pants_fix` (file scope) + `pants_check` (directory scope)
- **Test code tasks**: `pants_fix` (file scope) + `pants_test` (file scope)
- **JSON/config-only tasks**: Validate well-formedness only, no Pants checks needed

These catch immediate issues (syntax, formatting, type errors in the modified file) without the overhead of checking the entire codebase.

### Layer 2: Full Quality Check (per wave)

Run `full_quality_check` (fix → lint → check → test on all code) at wave boundaries — i.e., when a parent/top-level task completes and all its subtasks are done. This catches:

- Cross-file type errors
- Lint issues that only appear in the full context
- Test regressions from interactions between changes

### Layer 3: Pre-existing Failures

Pre-existing mypy or lint errors in unrelated files should be **noted but not block progress**. Only failures in code modified by the current spec require fixing.

## Task Plan Structure for Efficiency

When writing task plans, structure them to minimize redundant quality checks:

### Wave-Based Dependency Graphs

Group related subtasks into parent tasks (waves). All subtasks in a wave share a single full quality check at the end:

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3"] }
  ]
}
```

### Task Ordering Within Waves

Order subtasks so that:
1. **Source code first, tests last** — source changes are validated by type checking during implementation, then tests validate behavior at the end of the wave
2. **Shared code before consumers** — models/utilities before the code that uses them
3. **Verification tasks can be no-ops** — if a prior task already implemented something (e.g., task 2.2 implemented `__write_output` that task 2.5 was supposed to add), the later task just verifies and skips

## Contract Changes Across Files

Some edits are not local to the file being changed — they alter a contract that
other files depend on. These are the most common source of failures that only
surface at the wave-boundary `full_quality_check`, forcing an extra fix pass.
Handle them deliberately:

### Field/method/class removals are contract changes

When a task **removes or renames** a field, method, or class on a shared model
(or removes a mixin/base class), the subagent must grep the repo for references
before finishing, and then either:

- update the references as part of the task, or
- explicitly list them in the execution log as "expected breakage owned by task
  X" so the wave-boundary check knows they are accounted for.

Treat a field removal as a repo-wide contract change, not a local edit. A task
that removes `Model.field` is not done when its own file type-checks — it is
done when every reader of `Model.field` has been reconciled or logged.

### A directory's `conftest.py` is a dependency of its whole test suite

Shared pytest fixtures and Hypothesis strategies in a directory's `conftest.py`
are imported by every test in that directory. When migrating a model, migrate
the test `conftest.py` **first**, as its own ordered step, before the test files
that import from it. A stale `conftest.py` breaks the entire directory's
collection, not just one file — so it must never be left as an incidental
cleanup folded into an unrelated task.

### Serialization-path parity

When more than one code path serializes the same model (e.g. a single-item
request builder and a batch request builder), verify they use the **same**
serialization method. Divergent serialization (one path excluding a field the
other emits) is a contract drift that unit tests exercising only one path will
not catch, and it typically slips through to a checkpoint. Prefer routing all
paths through one shared serialization helper.

### Task Notes Section

Include a Notes section in `tasks.md` documenting the quality check strategy:

```markdown
## Notes

- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- The `post-task-quality-check` hook runs `full_quality_check` at wave boundaries (parent task completion)
- The `tailor-on-file-create` hook runs `pants_tailor` when new `.py` files are created
```

## Execution Log

Task plans should include an execution log file at `.kiro/specs/{feature-name}/execution-log.md` to track:

- What each subagent did
- Which quality checks it ran
- Issues found and fixed

This provides visibility without consuming agent context. Format:

```markdown
# Execution Log

| Task | Quality Checks Run | Notes |
|------|-------------------|-------|
| 1.1 | None (JSON only) | Manifest update |
| 1.2 | pants_fix + pants_check (file) | Model created |
| Final | full_quality_check (all) | fix ✓, lint ✓, check ✓, test ✓ |
```

## Instructions for Subagents

When dispatching tasks to subagents, include quality check instructions in the prompt:

- **For source tasks**: "After making changes, run ONLY `pants_fix` and `pants_check` scoped to the file/directory you modified. Do NOT run a full quality check."
- **For test tasks**: "After writing the test, run `pants_fix` on the test file, then `pants_test` scoped to the test file. Do NOT run a full quality check."
- **For config-only tasks**: "Only validate the file is well-formed. No quality checks needed."
- **When the task removes/renames a shared field, method, or class**: "Grep the repo for references to the removed/renamed symbol. Update them or list each remaining reference in the execution log as expected breakage owned by a named later task. Do not consider the task done just because your own file type-checks."
- **Always**: "Log your activity to the execution-log.md file."
