---
inclusion: manual
description: Release process for gears and packages including version locations, tag conventions, and automated workflows
---

# Releasing

## Version Number Locations

### nacc-common (package)

Three files must have matching versions:

1. `nacc-common/pyproject.toml` — `version` field under `[project]`
2. `nacc-common/BUILD` — `version` argument in `python_artifact()`
3. Tag: `nacc-common/vX.Y.Z`

### Gears

Three files must have matching versions:

1. `gear/{gear-name}/src/docker/manifest.json` — both the top-level `"version"` field and `"custom"."gear-builder"."image"` tag
2. `gear/{gear-name}/src/docker/BUILD` — `image_tags` list (version tag + `"latest"`)
3. Tag: `gear/{gear-name}/vX.Y.Z`

## Automated Release Workflows

### nacc-common

Workflow: `.github/workflows/release-nacc-common.yml`

**Trigger**: Pushing a tag matching `nacc-common/v*`

**What it does**:
1. Checks out the code at the tagged commit
2. Verifies version consistency — tag version must match both `pyproject.toml` AND `nacc-common/BUILD`
3. Builds wheel and sdist with `pants package nacc-common:dist`
4. Verifies the package installs and imports
5. Creates a GitHub Release with built artifacts attached
6. Runs compatibility checks on Python 3.10, 3.11, 3.12

**If the workflow fails**: Check that all three version locations match. A common miss is `nacc-common/BUILD` which is easy to forget.

### Gears

Gears do not currently have automated release workflows. They are built and deployed manually or via separate CI processes.

## Release Checklist

### nacc-common

1. Update version in `nacc-common/pyproject.toml`
2. Update version in `nacc-common/BUILD`
3. Add changelog entry in `docs/nacc_common/CHANGELOG.md`
4. Commit, push, and merge to main
5. Tag the merge commit: `git tag nacc-common/vX.Y.Z <commit>`
6. Push the tag: `git push origin nacc-common/vX.Y.Z`
7. The release workflow runs automatically and creates the GitHub Release

### Gears

1. Update version in `gear/{gear-name}/src/docker/manifest.json` (both `version` and `image` fields)
2. Update `image_tags` in `gear/{gear-name}/src/docker/BUILD`
3. Add changelog entry in `docs/{gear_name}/CHANGELOG.md`
4. Commit, push, and merge to main
5. Tag the merge commit: `git tag gear/{gear-name}/vX.Y.Z <commit>`
6. Push the tag: `git push origin gear/{gear-name}/vX.Y.Z`

## Tag Naming Convention

- **Packages**: `{package-name}/v{version}` (e.g., `nacc-common/v3.1.2`)
- **Gears**: `gear/{gear-name}/v{version}` (e.g., `gear/gather_submission_status/v1.4.1`)

## Fixing a Failed Release

If the nacc-common workflow fails due to a version mismatch:

1. Fix the version in the mismatched file(s)
2. Commit and push to main
3. Move the tag to the new commit: `git tag -f nacc-common/vX.Y.Z <new-commit>`
4. Force-push the tag: `git push -f origin nacc-common/vX.Y.Z`
5. The workflow retriggers automatically
