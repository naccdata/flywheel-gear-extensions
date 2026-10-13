#!/bin/sh
ROOTS=$(pants roots)
PYTHONPATH_LINE=$(python3 -c "print('PYTHONPATH=\"./' + ':./'.join('''${ROOTS}'''.split('\n')) + ':\$PYTHONPATH\"')")

# Update or add PYTHONPATH in .env while preserving other variables
if [ -f .env ]; then
    # If PYTHONPATH exists, update it; otherwise, append it
    if grep -q "^PYTHONPATH=" .env; then
        # Use a temporary file to avoid issues with in-place editing
        grep -v "^PYTHONPATH=" .env > .env.tmp
        echo "$PYTHONPATH_LINE" >> .env.tmp
        mv .env.tmp .env
    else
        echo "$PYTHONPATH_LINE" >> .env
    fi
else
    # Create new .env file if it doesn't exist
    echo "$PYTHONPATH_LINE" > .env
fi

if [ ! -e python-default.lock ]; then
    pants generate-lockfiles
else
    echo "Skipping generation of lock file"
fi

pants export --py-resolve-format=symlinked_immutable_virtualenv --resolve=python-default

# Link .venv to the exported virtualenv for the latest Python version.
# The link has to point at the version directory rather than the resolve
# directory, pyvenv.cfg lives in the version directory and Python looks for it
# next to the parent of the interpreter. Without it Python does not detect a
# virtualenv and falls back to the system interpreter, so the editor reports
# every third party import as unresolved.
EXPORT_DIR=dist/export/python/virtualenvs/python-default
LATEST_PY_VERSION=$(ls -1 "${EXPORT_DIR}" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1)
if [ -z "$LATEST_PY_VERSION" ]; then
    echo "Error: Could not find a Python version directory in ${EXPORT_DIR}"
    exit 1
fi

ln -snf "${EXPORT_DIR}/${LATEST_PY_VERSION}" ./.venv
echo "Created .venv symlink pointing to Python $LATEST_PY_VERSION"