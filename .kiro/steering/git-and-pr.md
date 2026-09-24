# Git and Pull Request Guidelines

## Creating Pull Requests

`gh pr create` always performs a `git push` internally, even when the branch is already up-to-date. This push handshake can be slow against the GitHub remote, causing timeouts.

### Recommended Approach

1. **Push explicitly first** — run `git push -u origin <branch>` as a separate step. This confirms the branch is up-to-date and completes quickly.
2. **Create the PR with a generous timeout** — use at least 120 seconds for `gh pr create` since the internal push + API call can take 60-90 seconds even when nothing needs pushing.
3. **Always specify `--head` and `--base`** — avoids ambiguity and interactive prompts.

```bash
# Step 1: Push (fast when already up-to-date)
git push -u origin my-branch

# Step 2: Create PR (120s+ timeout)
gh pr create --title "..." --body "..." --head my-branch --base main
```

### Fallback: Use the GitHub API Directly

If `gh pr create` keeps timing out, bypass it entirely with a direct API call that skips the push step:

```bash
gh api repos/{owner}/{repo}/pulls \
  -f title="..." \
  -f head="my-branch" \
  -f base="main" \
  -f body="..." \
  --jq '.html_url'
```

### Things That Do NOT Help

- Using a shorter PR body — the timeout is from the push handshake, not body size
- Creating with a placeholder body and editing after — same push delay applies
- Using `--no-maintainer-edit` — does not skip the push

## Logical Commits

When splitting a batch of changes into logical commits, the groups must
**partition** the changed set:

- Every changed or untracked file lands in exactly one commit.
- No file appears in two commits.
- The union of all groups equals the full set of changes.

Stage by explicit filename (never `git add -A` or `git add .`) so the partition
is enforced deliberately. After the last commit, run `git status` and confirm
the working tree is clean — a non-empty status means a file was missed and the
groups did not partition the set. If groups appear to overlap, resolve the
overlap by assigning each shared file to the single group where its change is
most significant.

Group by coherent concern (source vs. tests, one module vs. another, config/
bookkeeping on its own) and keep commit messages concise and in imperative mood.

## Branch Conventions

- Push to a new branch, never directly to main/master
- Use `-u` flag on first push to set up tracking
