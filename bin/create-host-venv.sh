#!/bin/bash
# Creates a host-native .venv for IDE analysis (autocomplete, type checking, package inspection).
# This venv is NOT used for execution — Pants in the devcontainer handles that.
#
# Usage: ./bin/create-host-venv.sh
#
# The required Python version is read from .python-version in the project root.
# Ensure that version is available via pyenv, system install, or PATH.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Read required version from .python-version
if [ ! -f .python-version ]; then
    echo "Error: .python-version file not found in project root."
    echo "Create one with the desired Python version (e.g., 3.12.11)."
    exit 1
fi

REQUIRED_VERSION=$(head -1 .python-version | tr -d '[:space:]')
REQUIRED_MAJOR_MINOR=$(echo "$REQUIRED_VERSION" | grep -oE '^[0-9]+\.[0-9]+')

if [ -z "$REQUIRED_MAJOR_MINOR" ]; then
    echo "Error: Could not parse version from .python-version (got: '$REQUIRED_VERSION')."
    exit 1
fi

echo "Required Python: $REQUIRED_MAJOR_MINOR.x (from .python-version: $REQUIRED_VERSION)"

# Find a matching Python interpreter
find_python() {
    local major_minor="$1"

    # Check for exact versioned command (e.g., python3.12)
    local cmd="python${major_minor}"
    if command -v "$cmd" &>/dev/null; then
        echo "$cmd"
        return
    fi

    # Check if python3 matches
    if command -v python3 &>/dev/null; then
        local version
        version=$(python3 --version 2>&1 | grep -oE "${major_minor}\.[0-9]+")
        if [ -n "$version" ]; then
            echo "python3"
            return
        fi
    fi

    # Check pyenv versions
    if command -v pyenv &>/dev/null; then
        local pyenv_root
        pyenv_root=$(pyenv root)
        local match
        match=$(ls -1 "$pyenv_root/versions/" 2>/dev/null | grep -E "^${major_minor}\." | sort -V | tail -1)
        if [ -n "$match" ]; then
            echo "$pyenv_root/versions/$match/bin/python3"
            return
        fi
    fi

    echo ""
}

PYTHON=$(find_python "$REQUIRED_MAJOR_MINOR")

if [ -z "$PYTHON" ]; then
    echo "Error: Python $REQUIRED_MAJOR_MINOR not found."
    echo "Install it via: pyenv install $REQUIRED_VERSION"
    exit 1
fi

echo "Using: $PYTHON ($($PYTHON --version))"

# Create or refresh the venv
if [ -L .venv ]; then
    echo "Removing existing .venv symlink..."
    rm .venv
fi

if [ -d .venv ]; then
    echo "Updating existing .venv..."
    "$PYTHON" -m venv .venv --upgrade
else
    echo "Creating .venv..."
    "$PYTHON" -m venv .venv
fi

echo "Installing dependencies from requirements.txt..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# Set up PYTHONPATH in .env for source roots so the IDE resolves local packages
echo "Configuring .env with source roots..."

# These are the Pants source roots for this project
SOURCE_ROOTS=(
    "common/src/python"
    "nacc-common/src/python"
    "ssm_parameter_store/src/python"
)

# Add gear source roots
for gear_dir in gear/*/src/python; do
    if [ -d "$gear_dir" ]; then
        SOURCE_ROOTS+=("$gear_dir")
    fi
done

PYTHONPATH_VALUE=""
for root in "${SOURCE_ROOTS[@]}"; do
    if [ -z "$PYTHONPATH_VALUE" ]; then
        PYTHONPATH_VALUE="./$root"
    else
        PYTHONPATH_VALUE="$PYTHONPATH_VALUE:./$root"
    fi
done

# Update or add PYTHONPATH in .env
if [ -f .env ]; then
    if grep -q "^PYTHONPATH=" .env; then
        grep -v "^PYTHONPATH=" .env > .env.tmp
        echo "PYTHONPATH=\"$PYTHONPATH_VALUE\"" >> .env.tmp
        mv .env.tmp .env
    else
        echo "PYTHONPATH=\"$PYTHONPATH_VALUE\"" >> .env
    fi
else
    echo "PYTHONPATH=\"$PYTHONPATH_VALUE\"" > .env
fi

echo ""
echo "Done. Host .venv is ready for IDE analysis."
echo "  Python: $(.venv/bin/python --version)"
echo "  Packages: $(.venv/bin/pip list --format=columns 2>/dev/null | wc -l | tr -d ' ') installed"
echo ""
echo "Note: This venv is for IDE support only. Use the devcontainer for execution (pants test/lint/check)."
