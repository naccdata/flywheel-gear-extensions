---
inclusion: auto
description: Guidance for using the kiro-pants-power to automate Pants build system and devcontainer operations
---

# Kiro Pants Power Usage

## Overview

The `kiro-pants-power` automates Pants build system and devcontainer operations for this repository. Use power tools instead of manual scripts whenever possible.

The power now supports intent-based parameters for simpler usage without needing to understand Pants target syntax.

## MCP Configuration

The power discovers the workspace folder automatically using MCP protocol roots (provided by Kiro at first tool call) or the process CWD as a fallback. No explicit `WORKSPACE_FOLDER` env var is needed.

The MCP config in `.kiro/settings/mcp.json` should include:

```json
{
  "command": "uvx",
  "args": [
    "--from", "git+https://github.com/naccdata/kiro-pants-power",
    "pants-devcontainer-power"
  ]
}
```

**Do NOT add a `WORKSPACE_FOLDER` env var to the config.** Kiro does not support `${workspaceFolder}` variable substitution in MCP env blocks. The power handles workspace discovery automatically via MCP roots and CWD fallback.

## Quick Reference

### Most Common Operations

**Complete Quality Check** (recommended before commits):

```text
Use: full_quality_check tool
```

**Partial Workflows** (when you don't need all steps):

```text
Use: pants_workflow tool with workflow="fix-lint"        # Format then lint
Use: pants_workflow tool with workflow="check-test"      # Type check then test
Use: pants_workflow tool with workflow="fix-lint-check"  # Format, lint, type check
```

**Individual Steps**:

```text
Use: pants_fix tool with scope="all"      # Format all code (always run first)
Use: pants_lint tool with scope="all"     # Check linting
Use: pants_check tool with scope="all"    # Type checking
Use: pants_test tool with scope="all"     # Run all tests
```

**Build Packages**:

```text
Use: pants_package tool with scope="all"
Use: pants_package tool with scope="directory", path="nacc-common"
```

**Generate/Update BUILD Files** (after adding new Python files):

```text
Use: pants_tailor tool                    # Generate BUILD files for all new sources
```

**Run Arbitrary Commands in Container**:

```text
Use: container_exec tool with command="pants --version"
Use: container_exec tool with command="bash get-pants.sh"
```

## Intent-Based Parameters

The individual Pants tools (`pants_fix`, `pants_lint`, `pants_check`, `pants_test`, `pants_package`) support intent-based parameters:

- `scope` (optional): What to operate on
  - `'all'` - Entire codebase (default)
  - `'directory'` - Specific directory
  - `'file'` - Single file

- `path` (required for 'directory' and 'file'): Directory or file path
  - Examples: `'common/src/python'`, `'gear/user_management/src/python/main.py'`

- `recursive` (optional, default: true): Include subdirectories (directory scope only)

- `test_filter` (optional, pants_test only): Filter tests by name pattern
  - Examples: `'test_create'`, `'test_create or test_update'`, `'not test_slow'`

**Note**: `full_quality_check` and `pants_workflow` only support the `target` parameter (legacy syntax), not intent-based parameters.

### Migration from Legacy Target Syntax

| Legacy `target` value | Intent-based equivalent |
|---|---|
| `"::"` | `scope="all"` |
| `"gear/gather_form_data::"` | `scope="directory", path="gear/gather_form_data", recursive=true` |
| `"gear/gather_form_data:"` | `scope="directory", path="gear/gather_form_data", recursive=false` |
| `"gear/gather_form_data/src/python/run.py"` | `scope="file", path="gear/gather_form_data/src/python/run.py"` |

Key differences: no `::` or `:` suffixes needed (the `recursive` flag handles this), paths are validated upfront, and error messages reference your intent rather than raw Pants target errors.

## Workflow Best Practices

### Before Committing Code

Always run the complete quality check:

```text
Use: full_quality_check tool
```

This runs: fix → lint → check → test in sequence and stops on first failure.

### During Development

Focus on specific areas you're changing:

```text
Use: pants_test tool with scope="directory", path="common/test/python"
Use: pants_fix tool with scope="directory", path="gear/form_qc_checker/src/python"
```

### Run Specific Tests

Filter tests by name without needing to know exact file paths:

```text
Use: pants_test tool with scope="all", test_filter="test_create"
Use: pants_test tool with scope="directory", path="common/test/python", test_filter="not test_slow"
```

### When Tests Fail

Run tests for specific module to isolate issues:

```text
Use: pants_test tool with scope="file", path="common/test/python/test_identifier.py"
Use: pants_test tool with scope="directory", path="common/test/python/identifiers"
```

### When Seeing Weird Errors

Clear Pants cache to resolve stale state:

```text
Use: pants_clear_cache tool
```

### After Dependency Changes

Rebuild the devcontainer:

```text
Use: container_rebuild tool
```

## Container Management

The power automatically starts the container when needed. Manual control is rarely required, but available:

```text
Use: container_start tool     # Idempotent - safe to call multiple times
Use: container_stop tool      # Stop container
Use: container_rebuild tool   # Rebuild from scratch
Use: container_exec tool with command="<cmd>"  # Run arbitrary command in container
```

## Understanding Error Output

When a Pants tool fails, the power parses raw Pants output into structured, actionable summaries rather than dumping the full console log. The response comes back as plain text in the MCP tool response.

### Successful commands

A successful response starts with a formatted summary if structured output was parsed, or falls back to:

```text
Command completed successfully: <command>
<stdout + stderr output>
```

### Failed commands — structured error responses

Failures are returned as formatted text with structured sections depending on what failed.

#### Test failures (`pants_test`)

```text
Test Results: <N> failed, <N> passed, <N> skipped out of <N> total

Failed Tests:
- <test_name>
  File: <file_path>
  Class: <class_name>  (if applicable)
  Type: <exception_type>
  Message: <failure_message>
  Stack trace: <first few lines>
```

Pytest assertion details may also appear:

```text
Pytest Failures: <N> tests failed
- <test_name>
  File: <file_path>
  Expected: <value>
  Actual: <value>
  Operator: ==
```

#### Type checking failures (`pants_check`)

```text
Type Checking: <N> errors found

Errors by file:
<file_path>: <N> errors
  - Line <N>, Column <N>: [<error_code>] <message>
  - Line <N>: [<error_code>] <message>
```

#### Coverage metrics (included with test results)

```text
Coverage: <percent>%
Report: <path>
Per-file coverage:
  <file_path>: <percent>% (<covered>/<total> lines)
  Uncovered lines: 45-52, 67-70
```

#### Sandbox paths (included on failure when `--keep-sandboxes=on_failure`)

```text
Preserved Sandboxes:
- <sandbox_path>
  Process: <description>
```

These paths point to temporary directories inside the container where you can inspect the exact inputs and run script (`__run.sh`) that Pants used.

#### Intent-based error translation

When using intent parameters (`scope`, `path`, `recursive`), common Pants errors are translated into user-friendly messages:

| Pants error pattern | Translated message |
|---|---|
| "No targets found" | "No tests found in {scope} {path}" |
| "BUILD file not found" | "Directory not configured for Pants. Run 'pants tailor' to set up BUILD files" |
| "No such file or directory" | "Path does not exist: {path}" |

The translated error may include a suggestion (e.g., `"pants tailor"`) indicating a remediation command.

#### Fallback behavior

If structured parsing fails or no parsers match the command type, the response falls back to:

```text
Command execution failed: <command>

Exit code: <N>

Output:
<raw stdout + stderr>
```

### How to act on errors

- **Test failures**: Look at the file path and test name to locate the failing code. Use assertion details (expected vs. actual) to understand the mismatch.
- **Type errors**: Fix in order by file. The error code (e.g., `arg-type`, `return-value`) tells you the category of type issue.
- **Missing BUILD files**: Run `pants_tailor` to auto-generate them.
- **Sandbox paths**: Use `container_exec` to inspect sandbox contents or re-run `__run.sh` for reproduction.
- **Coverage gaps**: Check uncovered line ranges to identify untested code paths.

### When structured detail IS present

Read the error output and act on it directly. Do NOT:
- Re-run the same command hoping for different output
- Fall back to `container_exec` to re-run the command manually
- Use `2>&1 | tail` tricks via `container_exec` — the power already captures both streams
- Pass `--no-local-cache` — cached results aren't the issue when output is missing

### When structured detail is NOT captured (fallback errors)

Sometimes the parser cannot extract structured detail and you see:

```text
Type Checking Failed (no structured detail captured)
Raw output:
✕ mypy failed.
```

In this case, narrow the scope to get detail:

1. Separate source from tests:
   - `pants_check` with `scope="directory"`, `path="<module>/src/python"`
   - `pants_check` with `scope="directory"`, `path="<module>/test/python"`
2. Whichever fails, narrow further to individual files if needed
3. Most common root cause after refactoring: test files importing removed/renamed symbols

### Efficient error resolution

1. Run `full_quality_check` first to get the full picture
2. Fix issues by category — fix all type errors before re-running, not one at a time
3. Re-run only what failed — if lint passed but check failed, use `pants_workflow` with `workflow="check-test"` for the retry, not `full_quality_check` again
4. Always update imports and test references before running checks after renaming/removing code

## Anti-Patterns to Avoid

- **Don't fall back to `container_exec` or manual scripts when a power tool fails** — if a power tool returns an error (container won't start, Pants not found, unexpected crash), STOP and report the error to the user. Do not attempt workarounds with raw commands. When the power isn't working correctly, executing spec tasks with manual fallbacks creates compounding complexity.
- **Don't use `container_exec` with raw pants commands** when a dedicated tool exists — use `pants_check`, `pants_lint`, etc. instead
- **Don't retry the same failing command more than once** — if it fails with the same output twice, STOP and report the situation to the user
- **Don't use legacy `target` syntax** in individual Pants tools — prefer intent-based params for better error messages and path validation
- **Don't run `full_quality_check` repeatedly** — if only one step fails, re-run just that step or use `pants_workflow` for the remaining steps

## Critical Rule: Stop on Power Errors

**If a power tool fails due to infrastructure issues (container errors, Pants not installed, MCP connection problems, or unexpected crashes), STOP execution immediately and report the error to the user.** Do NOT:

- Fall back to `./bin/exec-in-devcontainer.sh` or other manual scripts
- Try to use `container_exec` to run Pants commands directly
- Attempt to diagnose or fix container/infrastructure problems autonomously
- Continue executing spec tasks with degraded tooling

This rule exists because manual workarounds during spec task execution lead to cascading failures that are harder to debug than the original issue. Let the user fix the infrastructure problem first, then resume.

**This rule does NOT apply to code-level failures** (type errors, test failures, lint issues). Those are expected development feedback — read the error output and fix the code.

## Troubleshooting

### "Container not running" errors

- Power should auto-start container
- If it fails, check Docker Desktop is running
- Try: container_start tool explicitly

### "Pants not found" errors

- Pants needs to be installed in container
- Run: `devcontainer exec --workspace-folder . bash get-pants.sh`
- Or use: container_exec tool with command="bash get-pants.sh"

### Stale cache or "file not found" errors

- Use: pants_clear_cache tool
- Then retry the failing command

### Working directory or path resolution errors

- The power resolves workspace via MCP protocol roots (automatic) or CWD fallback
- Ensure the MCP config does NOT include a `WORKSPACE_FOLDER` env var (Kiro doesn't support `${workspaceFolder}` substitution)
- Reconnect the MCP server after config changes

### Test or lint failures

- Review the structured error output in the tool response
- Fix reported issues based on file paths and error codes
- Use: pants_fix tool with scope="all" to auto-fix formatting
- Re-run the failing command

## Manual Scripts (Reference Only)

The `bin/` scripts exist for human use when the power is unavailable. **Agents should NOT fall back to these scripts when power tools fail.** Instead, stop and report the error.

- `./bin/start-devcontainer.sh` - Start container
- `./bin/exec-in-devcontainer.sh <command>` - Execute command
- `./bin/terminal.sh` - Open interactive shell

## Additional Resources

- Power documentation: Activate the power to see full documentation
- Pants documentation: <https://www.pantsbuild.org>
- DevContainer CLI: <https://github.com/devcontainers/cli>
