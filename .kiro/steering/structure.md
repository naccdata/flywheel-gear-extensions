# Project Structure

## Monorepo Organization

This is a Pants-managed monorepo with multiple packages and gears organized by functionality.

## Top-Level Directories

### Core Packages

- **`nacc-common/`** - Shared Python package for NACC Data Platform utilities
  - Distributed as a standalone package via GitHub releases
  - Used by centers to access NACC Data Platform
  - Based on `flywheel-sdk`
  - Structure: `src/python/nacc_common/`, `test/`

- **`common/`** - Shared internal libraries used across gears
  - Not distributed separately
  - Contains modules for: centers, identifiers, data processing, Flywheel adapters, jobs, pipelines, etc.
  - Structure: `src/python/`, `test/python/`

- **`ssm_parameter_store/`** - AWS SSM Parameter Store utilities
  - Structure: `src/python/ssm_parameter_store/`, `test/`

### Gears

- **`gear/`** - Contains 26+ Flywheel gears, each in its own subdirectory
  - Each gear follows a consistent structure:
    - `src/docker/` - Dockerfile and Docker-related files
    - `src/python/{app_name}/` - Python application code
    - `test/python/` - Tests
    - `data/` - Test data and configuration files

  - Example gears:
    - `project_management/` - Project creation and management
    - `user_management/` - User and role management
    - `form_qc_checker/`, `form_scheduler/`, `form_transformer/` - Form processing
    - `identifier_lookup/`, `identifier_provisioning/` - Identifier management
    - `csv_center_splitter/`, `csv_subject_splitter/` - CSV processing
    - `attribute_curator/` - Data curation

### Configuration & Build

- **`BUILD`** - Root Pants build configuration
- **`pants.toml`** - Pants configuration file
- **`ruff.toml`** - Ruff linter/formatter configuration
- **`mypy.ini`** - mypy type checker configuration
- **`requirements.txt`** - Python dependencies
- **`*.lock`** - Pants lock files for dependency resolution

### Documentation

- **`docs/`** - MkDocs documentation
  - `index.md` - Main documentation index
  - Subdirectories for each gear and process
  - Published to GitHub Pages
  - **IMPORTANT**: Each gear and package has its CHANGELOG.md in `docs/{component_name}/CHANGELOG.md`
    - Example: `docs/user_management/CHANGELOG.md`
    - Example: `docs/nacc_common/CHANGELOG.md`
    - Example: `docs/form_qc_checker/CHANGELOG.md`

### Templates

- **`templates/`** - Cookiecutter templates for creating new components
  - `common/` - Template for common packages
  - `gear/` - Template for new gears
  - `docs/` - Template for documentation

### Other

- **`comanage/`** - COmanage API integration
- **`bin/`** - Utility scripts
- **`.devcontainer/`** - VSCode dev container configuration
- **`.github/`** - GitHub Actions workflows
- **`mypy-stubs/`** - Type stubs for external packages

## Source Code Conventions

### Python Package Structure

Standard layout for Python packages:
```
package-name/
├── BUILD                    # Pants build file
├── pyproject.toml          # Package metadata (if distributed) - contains version
├── README.md
├── src/python/
│   └── package_name/       # Python module
│       ├── BUILD
│       └── *.py
└── test/python/
    └── package_name_test/  # Tests use _test suffix to avoid namespace conflicts
        ├── BUILD
        ├── __init__.py     # Required when using conftest.py
        ├── conftest.py     # Pytest fixtures (optional)
        └── test_*.py
```

**Note**: Package CHANGELOGs are located in `docs/{package-name}/CHANGELOG.md`, NOT in the package directory itself.

**CRITICAL - Test Directory Naming**: Test directories MUST use the `_test` suffix (e.g., `projects_test`, `users_test`) to avoid namespace conflicts:
- **Problem**: When adding `conftest.py` to a test directory, mypy encounters a naming conflict if the test directory name matches the source package name
- **Wrong Solution**: Adding `__init__.py` to fix mypy causes pytest import errors for the source package
- **Correct Solution**: Name test directories with `_test` suffix to keep test and source namespaces distinct
- **Example**: For source `common/src/python/projects/`, use test directory `common/test/python/projects_test/` (not `projects/`)
- **Templates**: The cookiecutter templates enforce this pattern for new packages

### Gear Structure

Standard layout for gears:
```
gear/gear-name/
├── src/
│   ├── docker/
│   │   ├── BUILD
│   │   ├── Dockerfile
│   │   └── manifest.json   # Contains version number
│   └── python/
│       └── app_name/
│           ├── BUILD
│           ├── run.py      # Entry point
│           └── *.py
├── test/python/
│   └── test_*.py
└── data/
    └── *.yaml              # Test data
```

**Note**: Gear CHANGELOGs are located in `docs/{gear-name}/CHANGELOG.md`, NOT in the gear directory itself.

### BUILD Files

Each directory with Python code has a `BUILD` file defining Pants targets:
- `python_sources(name="lib")` - For source code
- `python_tests(name="tests")` - For test files
- `python_distribution()` - For distributable packages
- `docker_image()` - For Docker images

## Import Conventions

- Common libraries are imported from their module paths (e.g., `from centers import ...`, `from identifiers import ...`)
- nacc-common is imported as `from nacc_common import ...`
- Flywheel SDK: `import flywheel`

## Ignored Directories

Pants ignores:
- `.devcontainer/`
- `.vscode/`
- `bin/`
- `templates/`
- `comanage/` (excluded from Ruff linting)
