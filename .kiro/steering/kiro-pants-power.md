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

## Intent-Based Parameters

All Pants tools support these parameters:

- `scope` (optional): What to operate on
  - `'all'` - Entire codebase (default)
  - `'directory'` - Specific directory
  - `'file'` - Single file

- `path` (required for 'directory' and 'file'): Directory or file path
  - Examples: `'common/src/python'`, `'gear/user_management/src/python/main.py'`

- `recursive` (optional, default: true): Include subdirectories (directory scope only)

- `test_filter` (optional, pants_test only): Filter tests by name pattern
  - Examples: `'test_create'`, `'test_create or test_update'`, `'not test_slow'`

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

### Important: Do NOT retry blindly

When a Pants tool fails, the structured error response already contains sufficient detail to diagnose the issue. Do NOT:
- Re-run the same command hoping for more output
- Fall back to `container_exec` to re-run the command manually
- Try to narrow scope file-by-file to find errors

Instead, read the structured error response and act on it directly.

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

## Manual Scripts Fallback

If the power is unavailable, use scripts in `bin/`:

- `./bin/start-devcontainer.sh` - Start container
- `./bin/exec-in-devcontainer.sh <command>` - Execute command
- `./bin/terminal.sh` - Open interactive shell

## Additional Resources

- Power documentation: Activate the power to see full documentation
- Pants documentation: <https://www.pantsbuild.org>
- DevContainer CLI: <https://github.com/devcontainers/cli>
