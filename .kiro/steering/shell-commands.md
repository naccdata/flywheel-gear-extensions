# Shell Command Execution Rules

## Use `cwd` parameter, never `cd` prefix

**CRITICAL**: When running shell commands with `execute_bash`, always use the `cwd` parameter to set the working directory. Never prefix commands with `cd /path/to/dir &&`.

The workspace root is: `/Users/bjkeller/Documents/workspace/naccdata/flywheel-gear-extensions`

### Why

When commands are prefixed with a long `cd` path, the user cannot easily see the actual command being run in the UI.

### Correct

```
execute_bash(command="git branch -a", cwd="/Users/bjkeller/Documents/workspace/naccdata/flywheel-gear-extensions")
```

### Incorrect

```
execute_bash(command="cd /Users/bjkeller/Documents/workspace/naccdata/flywheel-gear-extensions && git branch -a")
```

### Also Incorrect

Using `&&` to chain multiple commands. Run them as separate `execute_bash` calls instead.
