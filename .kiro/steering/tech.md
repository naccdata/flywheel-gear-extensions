# Technology Stack

## Build System

**Pants Build System** (v2.27.0) - https://www.pantsbuild.org

Pants is used for all builds, testing, linting, and packaging in this monorepo.

## Language & Runtime

- **Python 3.11** (strict interpreter constraint: `==3.11.*`)
- Type checking with mypy
- Pydantic v2.5.2+ for data validation

## Key Dependencies

### Core Libraries
- `flywheel-sdk>=20.0.0` - Flywheel platform SDK
- `flywheel-gear-toolkit>=0.2` - Gear development toolkit
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

- Default repository: `naccdata/{name}`
- Build platform: `linux/amd64`
- Hadolint for Dockerfile linting

## Common Commands

### Setup
```bash
# Install Pants
bash get-pants.sh
```

### Building
```bash
# Build all targets
pants package ::

# Build specific package (e.g., nacc-common)
pants package nacc-common::

# Build distributions (creates wheel and sdist in dist/)
pants package nacc-common:dist
```

### Code Quality
```bash
# Format code
pants fix ::

# Run linters
pants lint ::

# Type check
pants check ::

# Run all checks
pants lint :: && pants check ::
```

### Testing
```bash
# Run all tests
pants test ::

# Run tests for specific module
pants test common/test/python::

# Run specific test file
pants test path/to/test_file.py
```

### Development Workflow
```bash
# Format, lint, and check before committing
pants fix :: && pants lint :: && pants check ::

# Run tests
pants test ::
```

## Python Interpreter Setup

Pants searches for Python interpreters in:
1. System PATH
2. pyenv installations

Ensure Python 3.11 is available via one of these methods.

## Package Distribution

Distributions are built as both wheel (`.whl`) and source (`.tar.gz`) formats and placed in the `dist/` directory.
