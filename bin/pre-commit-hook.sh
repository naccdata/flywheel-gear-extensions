#!/usr/bin/env bash
#
# Pre-commit hook that mirrors the CI "Lint" step in .github/workflows/pants.yml.
#
# WHY THIS EXISTS
# ---------------
# `pants fix ::` (a directory/recursive target) and `pants fix <file>.py` (a
# single-file target) run DIFFERENT fixer pipelines. The recursive form adds a
# "Format with Ruff" step ahead of `ruff check --fix`, which can leave ruff's
# import-sort rule (I001) unfixed. CI only runs `pants lint` (ruff check in
# check mode, no --fix), so a tree that `pants fix ::` reported as "clean" can
# still fail CI with I001. This hook closes that gap: it runs the SAME check CI
# runs, on the staged Python files, before the commit is recorded.
#
# BEHAVIOR
# --------
#   1. Collect staged *.py files (added/copied/modified).
#   2. Run `pants lint` on exactly those files, inside the devcontainer, the
#      same tool/version/config CI uses.
#   3. Pass  -> commit proceeds.
#   4. Fail  -> run file-scoped `pants fix` on those files (which DOES apply
#      I001), then ABORT the commit so you can review, re-stage, and commit
#      again. We do not auto-stage: staging stays explicit and human-approved.
#
# INSTALL
# -------
#   git config core.hooksPath bin/git-hooks
# (the installer symlinks/points this script in as `pre-commit`; see
# bin/install-git-hooks.sh)
#
# BYPASS
# ------
#   git commit --no-verify        # skip this hook (use sparingly)
#   PRE_COMMIT_SKIP=1 git commit   # same effect

set -euo pipefail

if [ "${PRE_COMMIT_SKIP:-0}" = "1" ]; then
    echo "pre-commit: skipped (PRE_COMMIT_SKIP=1)"
    exit 0
fi

# Resolve repo root so the hook works regardless of the cwd git invokes it from.
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Staged Python files (Added, Copied, Modified). Renames/deletes of the old path
# are excluded; the new path of a rename shows up as Added. Read with a NUL
# delimiter so paths with spaces or newlines are handled correctly, into a plain
# array (no `mapfile`, which is absent on macOS's bash 3.2).
STAGED_PY=()
while IFS= read -r -d '' file; do
    STAGED_PY+=("$file")
done < <(git diff --cached --name-only -z --diff-filter=ACM -- '*.py')

if [ "${#STAGED_PY[@]}" -eq 0 ]; then
    # No Python staged; nothing ruff/pants-lint would flag. Let the commit run.
    exit 0
fi

EXEC="$REPO_ROOT/bin/exec-in-devcontainer.sh"
if [ ! -x "$EXEC" ]; then
    echo "pre-commit: cannot find $EXEC; is this the repo root?" >&2
    exit 1
fi

echo "pre-commit: linting ${#STAGED_PY[@]} staged Python file(s) the way CI does..."

# Run `pants lint` on just the staged files (file-scoped targets). This matches
# the CI "Lint" step, which runs `pants lint` (ruff check, no --fix).
if "$EXEC" pants lint "${STAGED_PY[@]}"; then
    echo "pre-commit: lint clean."
    exit 0
fi

echo ""
echo "pre-commit: lint FAILED on staged files (CI would reject this)."
echo "pre-commit: running file-scoped 'pants fix' to correct it..."
echo ""

# File-scoped fix applies ruff's I001 autofix (unlike 'pants fix ::').
"$EXEC" pants fix "${STAGED_PY[@]}" || true

echo ""
echo "pre-commit: COMMIT ABORTED."
echo "pre-commit: 'pants fix' may have modified files. Review the changes, then:"
echo ""
echo "    git add <the fixed files>"
echo "    git commit ..."
echo ""
echo "pre-commit: to bypass this check, commit with --no-verify."
exit 1
