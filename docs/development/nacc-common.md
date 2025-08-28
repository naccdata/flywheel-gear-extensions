# nacc-common Python Developer Guide

This is a package of utilities that can be used by the centers accessing the NACC Data Platform to pull information about submissions.
The package is based on the `flywheel-sdk` package.
We encourage using these functions to avoid situations where data organization might be changed.

## Setup

This repository is setup to use [pants](pantsbuild.org) for developing and building the distributions.

Install pants with the command

```bash
bash get-pants.sh
```

You will need to make sure that you have a Python version compatible with the interpreter set in the `pants.toml` file.

The repo has a VSCode devcontainer configuration that ensures a compatible Python is available.
You need [Docker](https://www.docker.com) installed, and [VSCode](https://code.visualstudio.com) with Dev Containers enabled.
For this follow the [Dev Containers tutorial](https://code.visualstudio.com/docs/devcontainers/tutorial) to the point of "Check Installation".

## Building a distribution

Once pants is installed, the command 

```bash
pants package nacc-common::
```

will then build sdist and wheel distributions in the `dist` directory.

> The version number on the distribution files is set in the `nacc-common/BUILD` file.


## Making a release

1. Format the code with the command
   
   ```bash
   pants fix ::
   ```

   and commit any changes.

2. Ensure the repository passes the checks

   ```bash
   pants lint ::
   pants check ::
   ```

   and fix any issues and commit the changes.

3. Update the version number in `nacc_common/BUILD`.
   (This isn't strictly necessary, because the build script uses the tag version.)

4. Create and push the release tag

   ```bash
   export VERSION=v<current-version>
   git tag -a "$VERSION" -m "NACC Common Package $VERSION"
   git push --tags
   ```

   The `<current-version>` should use semantic versioning.
   For instance, it should have the form 1.1.2, meaning the tag will look like `v1.1.2`.

   The build GitHub action will create a new release with the tag as the version number.

