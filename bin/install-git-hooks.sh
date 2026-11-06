#!/usr/bin/env bash
#
# Enable the repository's tracked git hooks for this clone.
#
# Points git at bin/git-hooks via core.hooksPath, so the version-controlled
# pre-commit hook (bin/pre-commit-hook.sh) runs on every commit. Run once per
# clone:
#
#     ./bin/install-git-hooks.sh
#
# To disable later:
#
#     git config --unset core.hooksPath

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

chmod +x bin/pre-commit-hook.sh bin/git-hooks/pre-commit

git config core.hooksPath bin/git-hooks

echo "Installed git hooks: core.hooksPath -> bin/git-hooks"
echo "The pre-commit hook now runs 'pants lint' on staged Python files (mirrors CI)."
echo "Bypass a single commit with: git commit --no-verify"
