# Versioning and Changelog Guidelines

## Version Number Management

**CRITICAL RULE: Never automatically bump version numbers in CHANGELOG files.**

### When Making Code Changes

When making code changes to gears or packages:

1. **DO NOT** add new version entries to CHANGELOG.md files
2. **DO NOT** increment version numbers in any files
3. **DO** document what changes were made in your summary
4. **DO** wait for explicit user instruction before creating version entries

### Only Update Versions When Explicitly Asked

Version numbers should only be updated when the user explicitly requests it with phrases like:
- "Create a new version"
- "Bump the version to X.Y.Z"
- "Add a changelog entry for version X.Y.Z"
- "Prepare a release"

### Why This Rule Exists

Version management involves several coordinated steps:
- Updating CHANGELOG.md
- Updating version in manifest files
- Updating version in pyproject.toml (for packages)
- Creating git tags
- Building and publishing releases

These steps require human oversight and coordination. Automatically bumping versions can cause:
- Version conflicts
- Incomplete release preparation
- Confusion about what's been released vs. what's in development

## What To Do Instead

When you make changes that would normally warrant a version bump:

1. **Document the changes clearly** in your summary
2. **List the modified files**
3. **Explain what the changes accomplish**
4. **Suggest** that a version bump may be needed, but don't do it automatically

Example:
```
## Changes Made

- Fixed email notification template to display user list
- Updated ConsolidatedNotificationData model

## Files Modified
- common/src/python/users/event_notifications.py
- deployed-template.json

## Note
These changes may warrant a version bump when ready to release.
```

## Changelog Best Practices

When the user DOES ask you to create a changelog entry:

1. Follow the existing format in the CHANGELOG.md file
2. Use clear, concise bullet points
3. Focus on user-facing changes
4. Include any breaking changes prominently
5. Note any required deployment steps or migrations

## Exception: Documentation-Only Changes

For documentation-only changes (README updates, comment improvements, etc.) that don't affect functionality:
- No version bump is needed
- No changelog entry is needed
- Just document what was updated in your summary
