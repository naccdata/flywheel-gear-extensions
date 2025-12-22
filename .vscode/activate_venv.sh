#!/bin/bash
# Automatically activate the virtual environment for this workspace
if [ -f "${WORKSPACE_FOLDER:-.}/.venv/bin/activate" ]; then
    source "${WORKSPACE_FOLDER:-.}/.venv/bin/activate"
fi
