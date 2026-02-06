# Technology Stack

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

**IMPORTANT**: All commands must be executed inside the dev container. Use the wrapper scripts in `bin/` or open an interactive shell.

### Setup

```bash
# Ensure container is running (always run this first)
./bin/start-devcontainer.sh

# Install Pants
./bin/exec-in-devcontainer.sh bash get-pants.sh
```

### Building

```bash
# Build all targets
./bin/exec-in-devcontainer.sh pants package ::

# Build specific package (e.g., nacc-common)
./bin/exec-in-devcontainer.sh pants package nacc-common::

# Build distributions (creates wheel and sdist in dist/)
./bin/exec-in-devcontainer.sh pants package nacc-common:dist
```

### Code Quality

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

### Testing

```bash
# Run all tests
./bin/exec-in-devcontainer.sh pants test ::

# Run tests for specific module
./bin/exec-in-devcontainer.sh pants test common/test/python::

# Run specific test file
./bin/exec-in-devcontainer.sh pants test path/to/test_file.py
```

### Interactive Shell (Recommended for Multiple Commands)

```bash
# Open shell in container
./bin/terminal.sh

# Then run commands directly:
pants fix ::
pants lint ::
pants check ::
pants test ::
```

### Development Workflow

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

The dev container provides Python 3.12 pre-installed. No manual Python installation needed.

For local development outside the container, Pants searches for Python interpreters in:

1. System PATH
2. pyenv installations

Ensure Python 3.12 is available via one of these methods.

## Design Principles

### Dependency Injection over Flag Parameters

**Prefer dependency injection over boolean flags for configurable behavior.**

When designing classes that need configurable behavior, use dependency injection with strategy patterns rather than boolean flag parameters.

**❌ Avoid:**

```python
class MyProcessor:
    def __init__(self, data: List[str], use_fast_mode: bool = False):
        self.data = data
        self.use_fast_mode = use_fast_mode
    
    def process(self):
        if self.use_fast_mode:
            return self._fast_process()
        else:
            return self._slow_process()
```

**✅ Prefer:**

```python
ProcessingStrategy = Callable[[List[str]], Any]

def fast_strategy(data: List[str]) -> Any:
    # Fast processing implementation
    pass

def thorough_strategy(data: List[str]) -> Any:
    # Thorough processing implementation
    pass

class MyProcessor:
    def __init__(self, data: List[str], strategy: ProcessingStrategy = thorough_strategy):
        self.data = data
        self.strategy = strategy
    
    def process(self):
        return self.strategy(self.data)
```

**Benefits:**

- **Extensibility**: Easy to add new strategies without modifying existing code
- **Testability**: Each strategy can be tested independently
- **Single Responsibility**: Each strategy focuses on one approach
- **Open/Closed Principle**: Open for extension, closed for modification
- **Clear Intent**: Strategy names are more descriptive than boolean flags

**Example in Codebase:**
See `AggregateCSVVisitor` in `common/src/python/inputs/csv_reader.py` which uses `strategy_builder` parameter with `short_circuit_strategy` and `visit_all_strategy` functions instead of a `short_circuit: bool` flag.

## Package Distribution

Distributions are built as both wheel (`.whl`) and source (`.tar.gz`) formats and placed in the `dist/` directory.
