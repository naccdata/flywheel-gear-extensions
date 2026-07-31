---
inclusion: manual
description: Detailed reference for kiro-pants-power tool parameters and usage patterns
---

# Kiro Pants Power — Reference

All tools require `workspace_folder="/Users/bjkeller/Documents/workspace/naccdata/flywheel-gear-extensions"`.

## Intent-Based Parameters

The Pants tools (`pants_fix`, `pants_lint`, `pants_check`, `pants_test`, `pants_package`) support:

- `workspace_folder` (required): Absolute path to repo root containing `.devcontainer/`
- `scope` (optional): `'all'` (default), `'directory'`, or `'file'`
- `path` (required for directory/file): e.g. `'common/src/python'`, `'gear/user_management/src/python/main.py'`
- `recursive` (optional, default: true): Include subdirectories (directory scope only)
- `test_filter` (optional, pants_test only): pytest-style name filter, e.g. `'test_create'`, `'not test_slow'`

`full_quality_check`, `pants_workflow`, and `pants_tailor` use `workspace_folder` plus `target` (legacy syntax). `pants_workflow` also requires `workflow` (`"fix-lint"`, `"check-test"`, `"fix-lint-check"`).

## Common Invocations

```text
full_quality_check with workspace_folder="..."
pants_workflow with workspace_folder="...", workflow="fix-lint"
pants_fix with workspace_folder="...", scope="all"
pants_fix with workspace_folder="...", scope="directory", path="gear/form_qc_checker/src/python"
pants_fix with workspace_folder="...", scope="file", path="common/src/python/users/models.py"
pants_test with workspace_folder="...", scope="directory", path="common/test/python", test_filter="test_create"
pants_tailor with workspace_folder="..."
pants_package with workspace_folder="...", scope="directory", path="nacc-common"
container_exec with workspace_folder="...", command="bash get-pants.sh"
pants_clear_cache with workspace_folder="..."
container_rebuild with workspace_folder="..."
```

## Legacy Target Syntax (deprecated)

| Legacy `target` | Intent-based equivalent |
|---|---|
| `"::"` | `scope="all"` |
| `"gear/gather_form_data::"` | `scope="directory", path="gear/gather_form_data"` |
| `"gear/gather_form_data:"` | `scope="directory", path="gear/gather_form_data", recursive=false` |
| `"path/to/file.py"` | `scope="file", path="path/to/file.py"` |

## Error Resolution

- **Test failures**: Use file path and assertion details from output to locate and fix
- **Type errors**: Fix by file; error code (`arg-type`, `return-value`) indicates category
- **Missing BUILD files**: Run `pants_tailor`
- **Fallback errors with no structured detail**: Narrow scope (separate src from test, then narrow to files)
- **Stale cache / weird file-not-found**: Run `pants_clear_cache`, then retry
- Act on structured error output directly — don't re-run hoping for different results
- Fix all issues in a category before re-running, not one at a time
- Re-run only what failed (use `pants_workflow` for partial retries)
