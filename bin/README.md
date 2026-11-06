# Dev Container Scripts

Helper scripts for managing the development container using the devcontainer CLI.

## Prerequisites

Install the devcontainer CLI:
```bash
npm install -g @devcontainers/cli
```

## Scripts

### `build-container.sh`
Build the dev container image.

```bash
./bin/build-container.sh
```

This reads the `.devcontainer/devcontainer.json` configuration and builds the container image with all specified features and dependencies.

### `start-devcontainer.sh`
Start the dev container.

```bash
./bin/start-devcontainer.sh
```

Starts the container and runs the `postCreateCommand` if it's the first time starting. The workspace folder is mounted at `/workspaces/<workspace-name>`.

### `stop-devcontainer.sh`
Stop and remove the running dev container.

```bash
./bin/stop-devcontainer.sh
```

Stops the container and cleans up resources.

### `terminal.sh`
Open an interactive shell in the running dev container.

```bash
./bin/terminal.sh
```

Opens a zsh shell as the `vscode` user in the workspace directory. The container must be running first.

### `exec-in-devcontainer.sh`
Execute a command in the running dev container.

```bash
./bin/exec-in-devcontainer.sh <command> [args...]
```

Examples:
```bash
# List files
./bin/exec-in-devcontainer.sh ls -la

# Run pants commands
./bin/exec-in-devcontainer.sh pants test ::

# Check Python version
./bin/exec-in-devcontainer.sh python --version
```

### `install-git-hooks.sh`
Enable the repository's tracked git hooks for your clone (run once per clone).

```bash
./bin/install-git-hooks.sh
```

Points git at `bin/git-hooks` via `core.hooksPath` so the version-controlled
pre-commit hook runs on every commit. Disable later with
`git config --unset core.hooksPath`.

### `pre-commit-hook.sh`
The pre-commit hook body (invoked by `bin/git-hooks/pre-commit`; you normally
do not run it directly).

On commit it runs `pants lint` on the staged Python files — the same check CI's
"Lint" step runs — before the commit is recorded. If lint passes the commit
proceeds; if it fails the hook runs a **file-scoped** `pants fix` to correct the
issue and then aborts the commit so you can review, re-stage, and commit again.

This exists because `pants fix ::` (a directory/recursive target) and
`pants fix <file>.py` (a single-file target) run different fixer pipelines: the
recursive form can leave ruff's import-sort rule (`I001`) unfixed, so a tree
that `pants fix ::` reported as clean can still fail CI. The hook closes that
gap. See the "Pants `fix` scope caveat" note in `.kiro/steering/devcontainer.md`
for the full explanation.

Bypass a single commit with `git commit --no-verify` (or
`PRE_COMMIT_SKIP=1 git commit`). The hook requires the devcontainer, since it
runs Pants inside it.

## Typical Workflow

1. Build the container (first time or after config changes):
   ```bash
   ./bin/build-container.sh
   ```

2. Start the container:
   ```bash
   ./bin/start-devcontainer.sh
   ```

3. Open a shell or execute commands:
   ```bash
   ./bin/terminal.sh
   # or
   ./bin/exec-in-devcontainer.sh pants lint ::
   ```

4. Stop the container when done:
   ```bash
   ./bin/stop-devcontainer.sh
   ```

## Notes

- All scripts check for the devcontainer CLI and provide installation instructions if missing
- The workspace folder is automatically mounted in the container
- Scripts use the current directory as the workspace folder
