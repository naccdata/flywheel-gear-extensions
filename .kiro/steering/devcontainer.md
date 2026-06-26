# Dev Container Workflow

This project uses dev containers for consistent development environments.

## Kiro Pants Power (Recommended)

**PREFERRED METHOD**: Use the `kiro-pants-power` for automated devcontainer and Pants command execution. The power automatically manages container lifecycle and wraps all Pants commands.

Available power tools:
- `pants_fix` - Format code and auto-fix linting issues
- `pants_lint` - Run linters on code
- `pants_check` - Run type checking with mypy
- `pants_test` - Run tests (supports test_filter for specific test names)
- `pants_package` - Build packages
- `full_quality_check` - Run complete workflow (fix → lint → check → test)
- `container_start`, `container_stop`, `container_rebuild` - Container lifecycle management

The power handles all container management automatically, ensuring the container is running before executing commands.

### Intent-Based Parameters

All Pants tools now support intent-based parameters for simpler usage:

- `scope` (optional): What to operate on
  - `'all'` - Entire codebase (default)
  - `'directory'` - Specific directory
  - `'file'` - Single file

- `path` (required for 'directory' and 'file' scopes): Directory or file path
  - Examples: `'common/src/python'`, `'gear/user_management/src/python/main.py'`

- `recursive` (optional, default: true): Include subdirectories
  - Only applies to 'directory' scope

- `test_filter` (optional, pants_test only): Filter tests by name pattern
  - Uses pytest-style filtering
  - Examples: `'test_create'`, `'test_create or test_update'`, `'not test_slow'`

### Usage Examples

```
# Run on all code
pants_fix with scope="all"
pants_test with scope="all"

# Run on specific directory
pants_lint with scope="directory", path="common/src/python"
pants_test with scope="directory", path="common/test/python", recursive=true

# Run on single file
pants_check with scope="file", path="common/src/python/users/models.py"

# Run specific tests by name
pants_test with scope="directory", path="common/test/python", test_filter="test_create"
pants_test with scope="all", test_filter="not test_slow"

# Legacy target syntax (deprecated but still supported)
pants_fix with target="::"
pants_test with target="common/test/python::"
```

## Manual Scripts (Fallback)

If the power is unavailable, use the devcontainer scripts in the `bin/` directory.

**IMPORTANT**: All Pants commands and setup scripts should be executed inside the running dev container, not on the host machine.

**CRITICAL**: Before executing any commands in the container, ALWAYS check if the container is running first by running `./bin/start-devcontainer.sh`. This command is idempotent - it will start the container if stopped, or do nothing if already running.

### Commands to Run in Container

Use `./bin/exec-in-devcontainer.sh` to execute these commands:

#### Setup
```bash
./bin/exec-in-devcontainer.sh bash get-pants.sh
```

#### Code Quality
```bash
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
```

#### Testing
```bash
./bin/exec-in-devcontainer.sh pants test ::
./bin/exec-in-devcontainer.sh pants test common/test/python::
./bin/exec-in-devcontainer.sh pants test path/to/test_file.py
```

#### Running Scripts
```bash
./bin/exec-in-devcontainer.sh pants run scripts/example_script/src/python:main
```

### Interactive Shell

For multiple commands or interactive work, open a shell in the container:

```bash
./bin/terminal.sh
```

Then run commands directly:
```bash
pants fix ::
pants lint ::
pants test ::
```

## Container Management

### Start Container
```bash
./bin/start-devcontainer.sh
```

### Stop Container
```bash
./bin/stop-devcontainer.sh
```

### Rebuild Container
After changing `.devcontainer/` configuration:
```bash
./bin/build-container.sh
./bin/start-devcontainer.sh
```

## Python Environment

### Execution (Dev Container)

The dev container provides Python 3.12 pre-installed. No need for pyenv or manual Python installation — the container handles all execution (tests, linting, type checking, packaging).

### IDE Support (Host .venv)

A separate host-native `.venv` exists for IDE features like autocomplete, type checking, and package inspection. This venv is **not** used for execution.

```bash
# Create or refresh the host .venv
./bin/create-host-venv.sh
```

This script:
- Reads the required Python version from `.python-version`
- Creates a `.venv` in the project root with dependencies from `requirements.txt`
- Configures `.env` with `PYTHONPATH` pointing to all Pants source roots

**Important**: The host `.venv` is for IDE analysis only. Always use the devcontainer (via Pants power or manual scripts) for running code, tests, and quality checks.

## Workflow Example

```bash
# Always start/ensure container is running first
./bin/start-devcontainer.sh

# Run commands in the container
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
./bin/exec-in-devcontainer.sh pants test ::

# Or open an interactive shell
./bin/terminal.sh

# Stop when done
./bin/stop-devcontainer.sh
```

## Kiro AI Assistant Workflow

### Using Kiro Pants Power (Recommended)

When the `kiro-pants-power` is available:

1. Use power tools directly (e.g., `pants_fix`, `pants_lint`, `pants_test`)
2. The power automatically manages container lifecycle
3. Use `full_quality_check` for complete validation workflow

### Using Manual Scripts (Fallback)

When the power is unavailable:

1. **ALWAYS** run `./bin/start-devcontainer.sh` first to ensure the container is running
2. Then execute the desired command with `./bin/exec-in-devcontainer.sh`
3. The start command is safe to run multiple times - it won't restart a running container
