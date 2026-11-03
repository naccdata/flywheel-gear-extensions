# Agent guide

Conventions for AI coding agents working in this repository. This is the
cross-agent entry point; it summarizes the few rules that are easy to miss and
points to the authoritative documents rather than restating them.

Kiro-specific steering lives in `.kiro/steering/*.md`. Those files are the
detailed source of truth; the most load-bearing points are summarized below so
agents that do not read `.kiro/steering/` still follow them.

## Build, test, and lint run through Pants in a devcontainer

- This is a Pants monorepo (Python 3.12). All builds, tests, linting, and type
  checking run through Pants **inside a devcontainer** — not against the host
  Python.
- Use the scripts in `bin/` (e.g. `./bin/start-devcontainer.sh`, then
  `./bin/exec-in-devcontainer.sh pants ...`) or the Kiro Pants power. Always
  ensure the container is running first.
- Common commands: `pants fix ::` (format + autofix), `pants lint ::`,
  `pants check ::` (mypy), `pants test ::`. Run `pants fix` before `pants lint`.
- See `.kiro/steering/tech.md` and `.kiro/steering/devcontainer.md`.

## Import grouping: maintain `known-first-party` in `ruff.toml`

Ruff's `I001` import-grouping rule relies on an explicit `known-first-party`
list in `ruff.toml`. **It is maintained by hand.**

- **When you add a new gear, package, or test package, add its top-level
  package name(s) to `known-first-party` in `ruff.toml`.** For a gear: the
  `app_name` under `src/python/` and the `{app_name}_test` under
  `test/python/`. For a library package: the module name under `src/python/`
  and its `{name}_test` package.
- A missing entry causes a confusing failure: imports pass a file-scoped
  `pants fix` locally but fail CI's wider-scoped `pants lint` with an `I001`
  error on the new package, and re-sorting does not durably fix it.
- The comment at the top of the `[lint.isort]` section in `ruff.toml` is the
  source of truth; it includes the command to regenerate the full list.

## Test files go in an `_test` package with `__init__.py`

- Put test files in a `{app_name}_test/` (or `{package_name}_test/`) directory
  containing an **empty `__init__.py`**, not directly under `test/python/`.
- Without the package `__init__.py`, two test files that share a module name
  (e.g. two gears each with `test/python/test_main.py`) make mypy fail
  repo-wide with a `Duplicate module named "..."` error that only appears at
  repo scope, so it can slip past a gear-scoped check and fail CI.
- See `.kiro/steering/structure.md` ("Test Directory Naming").

## Git, versioning, and releases

- Stage explicit paths and commit as separate `git add` / `git commit` steps;
  do not use `git commit -a`/`-am`. One logical change per commit.
- Do **not** bump version numbers or edit `CHANGELOG.md` files unless explicitly
  asked. CHANGELOGs live under `docs/{component}/CHANGELOG.md`.
- See `.kiro/steering/git-and-pr.md`, `.kiro/steering/versioning.md`, and
  `.kiro/steering/releasing.md`.
