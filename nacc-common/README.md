# nacc-common Python package

Defines the nacc-common package (formerly part of data-platform-demos)

This is a package of utilities that can be used by centers accessing the NACC Data Platform to pull information about submissions.
The package is based on the `flywheel-sdk` package.
We encourage using these functions to avoid situations where data organization might be changed.

Distributions can be accessed via each [release](https://github.com/naccdata/nacc-common/releases) on GitHub.

## Using the package

You can use the release directly by referencing the release files in your package manager.
For instance, adding the following line to `requirements.txt` for use with [pip](https://pip.pypa.io/en/stable/topics/vcs-support/#git)

```text
nacc-common@ https://github.com/naccdata/nacc-common/releases/download/v1.1.2/nacc_common-1.1.2-py3-none-any.whl
```

will include the 1.1.1 release of the package (as a wheel distribution) as a dependency.
The format of the URL stays consistent, so to use a newer version of the package replace the version number.

Most package managers use a similar format to add packages directly from GitHub.

## Developer guide

### Setup

This repository is setup to use [pants](pantsbuild.org) for developing and building the distributions.

Install pants with the command

```bash
bash get-pants.sh
```

You will need to make sure that you have a Python version compatible with the interpreter set in the `pants.toml` file.

The repo has a VSCode devcontainer configuration that ensures a compatible Python is available.
You need [Docker](https://www.docker.com) installed, and [VSCode](https://code.visualstudio.com) with Dev Containers enabled.
For this follow the [Dev Containers tutorial](https://code.visualstudio.com/docs/devcontainers/tutorial) to the point of "Check Installation".

### Building a distribution

Once pants is installed, the command 

```bash
pants package nacc_common::
```

will then build sdist and wheel distributions in the `dist` directory.

> The version number on the distribution files is set in the `nacc_common/BUILD` file.


### Installing a distribution

The built wheel can be installed into a Python environment using pip. It is recommended to use a virtual environment or Docker image as opposed to your machine's local environment, especially if you are running something other than Python 3.12 as required by these demos.

```bash
# replace <version> with the version that was built
pip3 install nacc_common-<version>-py3-none-any.whl
```

### Making a release

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




