---
inclusion: auto
description: Core rules for using the kiro-pants-power (detailed reference loaded on-demand via hook)
---

# Kiro Pants Power — Core Rules

## Workspace Folder

**All power tools require `workspace_folder` as a required parameter.** For this project:

```
workspace_folder="/Users/bjkeller/Documents/workspace/naccdata/flywheel-gear-extensions"
```

## Essential Rules

1. **Use power tools, not manual scripts** — use `pants_fix`, `pants_lint`, `pants_check`, `pants_test`, `pants_package`, `pants_tailor`, `full_quality_check`, `pants_workflow`, and container tools instead of `./bin/` scripts.

2. **Stop on infrastructure errors** — if a power tool fails due to container/MCP/infrastructure issues, STOP and report to the user. Do NOT fall back to manual scripts or `container_exec` with raw pants commands.

3. **Don't retry identical failures** — if a tool fails with the same output twice, stop and report.

4. **Prefer intent-based parameters** over legacy `target` syntax for individual Pants tools (better error messages, path validation).

5. **Don't use `container_exec` with raw pants commands** when a dedicated tool exists.

6. **Code-level failures are normal** — type errors, test failures, lint issues are development feedback. Read the output and fix the code.

## Detailed Reference

The full reference (error output formats, workflow examples, troubleshooting, parameter details) is in the `kiro-pants-power-reference` steering file. It is loaded automatically via hook when pants power tools are invoked.
