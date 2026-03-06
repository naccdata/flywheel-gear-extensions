---
inclusion: auto
---

# Kiro Pants Power Usage

## Overview

The `kiro-pants-power` automates Pants build system and devcontainer operations for this repository. Use power tools instead of manual scripts whenever possible.

## Quick Reference

### Most Common Operations

**Complete Quality Check** (recommended before commits):
```
Use: full_quality_check tool
```

**Individual Steps**:
```
Use: pants_fix tool      # Format code (always run first)
Use: pants_lint tool     # Check linting
Use: pants_check tool    # Type checking
Use: pants_test tool     # Run tests
```

**Build Packages**:
```
Use: pants_package tool
Use: pants_package tool with target="specific/path::"
```

### Target Specifications

- Default (no target): All targets in repository (`"::"`)
- Specific directory: `"common/src/python::"` (directory and subdirectories)
- Specific file: `"path/to/file.py"`
- Specific target: `"path/to/dir:target"`

## Workflow Best Practices

### Before Committing Code

Always run the complete quality check:
```
Use: full_quality_check tool
```

This runs: fix → lint → check → test in sequence and stops on first failure.

### During Development

Focus on specific areas you're changing:
```
Use: pants_test tool with target="common/test/python::"
Use: pants_fix tool with target="gear/form_qc_checker::"
```

### When Tests Fail

Run tests for specific module to isolate issues:
```
Use: pants_test tool with target="path/to/failing/test.py"
```

### When Seeing Weird Errors

Clear Pants cache to resolve stale state:
```
Use: pants_clear_cache tool
```

### After Dependency Changes

Rebuild the devcontainer:
```
Use: container_rebuild tool
```

## Container Management

The power automatically starts the container when needed. Manual control is rarely required, but available:

```
Use: container_start tool     # Idempotent - safe to call multiple times
Use: container_stop tool      # Stop container
Use: container_rebuild tool   # Rebuild from scratch
```

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

### Test or lint failures
- Review error output carefully
- Fix reported issues
- Use: pants_fix tool to auto-fix formatting
- Re-run the failing command

## Manual Scripts Fallback

If the power is unavailable, use scripts in `bin/`:
- `./bin/start-devcontainer.sh` - Start container
- `./bin/exec-in-devcontainer.sh <command>` - Execute command
- `./bin/terminal.sh` - Open interactive shell

## Additional Resources

- Power documentation: Activate the power to see full documentation
- Pants documentation: https://www.pantsbuild.org
- DevContainer CLI: https://github.com/devcontainers/cli
