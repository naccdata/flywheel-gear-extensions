# Technology Stack

## Kiro Pants Power

**RECOMMENDED**: This project uses the `kiro-pants-power` for automated Pants build system and devcontainer management.

The power provides MCP tools that automatically handle:
- Container lifecycle (start, stop, rebuild)
- Pants commands (fix, lint, check, test, package)
- Workflow orchestration (full_quality_check for complete validation)

All power tools automatically ensure the devcontainer is running before execution. Manual scripts in `bin/` are available as fallback.

## Development Environment

**Dev Container** - Consistent development environment using Docker

This project uses dev containers for reproducible development environments. All commands should be executed inside the dev container.

### Container Management Scripts

Located in `bin/` directory:

- `start-devcontainer.sh` - Start the dev container (idempotent, safe to run multiple times)
- `stop-devcontainer.sh` - Stop the dev container
- `build-container.sh` - Rebuild the container after configuration changes
- `exec-in-devcontainer.sh` - Execute a command in the running container
- `terminal.sh` - Open an interactive shell in the container
- `create-host-venv.sh` - Create/refresh a host-native `.venv` for IDE support (not for execution)

**CRITICAL**: Always run `./bin/start-devcontainer.sh` before executing any commands to ensure the container is running.

## Build System

**Pants Build System** (v2.27.0) - <https://www.pantsbuild.org>

Pants is used for all builds, testing, linting, and packaging in this monorepo.

## Language & Runtime

- **Python 3.12** (strict interpreter constraint: `==3.12.*`)
- Type checking with mypy
- Pydantic v2.5.2+ for data validation
- Dev container provides Python 3.12 pre-installed

## Key Dependencies

### Core Libraries

- `flywheel-sdk>=20.0.0` - Flywheel platform SDK
- `fw-gear>=0.3.5` - Gear development toolkit
- `fw-client>=0.7.0`, `fw-utils>=3` - Flywheel utilities
- `pydantic>=2.5.2` - Data validation and settings management
- `pandas>=2.1.1` - Data manipulation

### AWS Integration

- `boto3>=1.28.53` - AWS SDK
- `moto[s3,ssm,ses]==5.1.14` - AWS mocking for tests

### NACC Packages

- `nacc_form_validator` - Form validation
- `nacc_attribute_deriver` - Attribute derivation
- `redcap_api` - REDCap integration

## Code Quality Tools

### Linting & Formatting

- **Ruff** - Fast Python linter and formatter
  - Line length: 88 characters
  - Indent: 4 spaces
  - Selected rules: A, B, E, W, F, I, RUF, SIM, C90, PLW0406, COM818, SLF001
  - Excludes: `comanage/` directory

### Type Checking

- **mypy** with Pydantic plugin
- `warn_unused_configs = True`
- `check_untyped_defs = True`

### Testing

- **pytest** with verbose output (`-vv`)

## Docker

### Dev Container

- Base image: Python 3.12 dev container
- Features: Docker-in-Docker, Go tooling
- VS Code extensions: Python, Docker, Ruff, Code Spell Checker
- Configuration: `.devcontainer/devcontainer.json`

### Gear Images

- Default repository: `naccdata/{name}`
- Build platform: `linux/amd64`
- Hadolint for Dockerfile linting

## Common Commands

### Using Kiro Pants Power (Recommended)

**PREFERRED METHOD**: Use the `kiro-pants-power` tools for all Pants and devcontainer operations. The power automatically manages container lifecycle.

The power now supports intent-based parameters for simpler usage:
- `scope`: 'all' (entire codebase), 'directory' (specific directory), or 'file' (single file)
- `path`: Directory or file path (required for 'directory' and 'file' scopes)
- `recursive`: Include subdirectories (default: true, only for 'directory' scope)
- `test_filter`: Filter tests by name pattern (pytest-style, only for pants_test)

#### Code Quality Workflow

```
# Complete quality check (fix → lint → check → test)
Use: full_quality_check tool

# Individual steps - all code
Use: pants_fix tool with scope="all"
Use: pants_lint tool with scope="all"
Use: pants_check tool with scope="all"
Use: pants_test tool with scope="all"

# Individual steps - specific directory
Use: pants_fix tool with scope="directory", path="common/src/python"
Use: pants_lint tool with scope="directory", path="common/src/python"

# Individual steps - single file
Use: pants_check tool with scope="file", path="common/src/python/users/models.py"

# Run specific tests by name
Use: pants_test tool with scope="directory", path="common/test/python", test_filter="test_create"
```

#### Building

```
# Build all packages
Use: pants_package tool with scope="all"

# Build specific directory (e.g., nacc-common)
Use: pants_package tool with scope="directory", path="nacc-common"

# Build single file/target
Use: pants_package tool with scope="file", path="gear/user_management/src/docker/BUILD"
```

#### Container Management

```
Use: container_start tool    # Start container
Use: container_stop tool     # Stop container
Use: container_rebuild tool  # Rebuild after config changes
```

#### Legacy Target Syntax (Deprecated)

The old `target` parameter still works but is deprecated:
```
Use: pants_fix tool with target="::"              # All code
Use: pants_test tool with target="common/test/python::"  # Specific directory
```

### Using Manual Scripts (Fallback)

**IMPORTANT**: All commands must be executed inside the dev container. Use the wrapper scripts in `bin/` or open an interactive shell.

#### Setup

```bash
# Ensure container is running (always run this first)
./bin/start-devcontainer.sh

# Install Pants
./bin/exec-in-devcontainer.sh bash get-pants.sh
```

#### Building

```bash
# Build all targets
./bin/exec-in-devcontainer.sh pants package ::

# Build specific package (e.g., nacc-common)
./bin/exec-in-devcontainer.sh pants package nacc-common::

# Build distributions (creates wheel and sdist in dist/)
./bin/exec-in-devcontainer.sh pants package nacc-common:dist
```

#### Code Quality

**IMPORTANT**: Always run `pants fix` before `pants lint` to automatically fix formatting and import issues.

```bash
# Format code (ALWAYS run this first)
./bin/exec-in-devcontainer.sh pants fix ::

# Run linters (after fix)
./bin/exec-in-devcontainer.sh pants lint ::

# Type check
./bin/exec-in-devcontainer.sh pants check ::

# Run all checks (ALWAYS run fix first to auto-fix issues)
./bin/exec-in-devcontainer.sh pants fix :: && pants lint :: && pants check ::
```

#### Testing

```bash
# Run all tests
./bin/exec-in-devcontainer.sh pants test ::

# Run tests for specific module
./bin/exec-in-devcontainer.sh pants test common/test/python::

# Run specific test file
./bin/exec-in-devcontainer.sh pants test path/to/test_file.py
```

#### Interactive Shell (Recommended for Multiple Commands)

```bash
# Open shell in container
./bin/terminal.sh

# Then run commands directly:
pants fix ::
pants lint ::
pants check ::
pants test ::
```

#### Development Workflow

```bash
# Ensure container is running
./bin/start-devcontainer.sh

# Option 1: Run commands via wrapper
./bin/exec-in-devcontainer.sh pants fix ::
./bin/exec-in-devcontainer.sh pants lint ::
./bin/exec-in-devcontainer.sh pants check ::
./bin/exec-in-devcontainer.sh pants test ::

# Option 2: Open interactive shell
./bin/terminal.sh
# Then run: pants fix :: && pants lint :: && pants check :: && pants test ::

# Stop container when done
./bin/stop-devcontainer.sh
```

## Python Interpreter Setup

### Execution Environment (Dev Container)

The dev container provides Python 3.12 pre-installed. No manual Python installation needed for running code.

### IDE Environment (Host .venv)

A host-native `.venv` provides IDE support (autocomplete, type checking, go-to-definition) without depending on the devcontainer.

```bash
# Create or refresh the host .venv
./bin/create-host-venv.sh
```

This script:
- Reads the required Python version from `.python-version`
- Finds a matching interpreter via `python3.12`, `python3`, or pyenv
- Creates `.venv` with all dependencies from `requirements.txt`
- Configures `.env` with `PYTHONPATH` for all Pants source roots (so the IDE resolves local packages)

**Note**: The host `.venv` is for IDE analysis only. All execution (tests, linting, builds) happens in the devcontainer via Pants.

For the host venv to work, ensure Python 3.12 is available on the host via:
1. System PATH (e.g., `python3.12`)
2. pyenv installations

## Package Distribution

Distributions are built as both wheel (`.whl`) and source (`.tar.gz`) formats and placed in the `dist/` directory.
