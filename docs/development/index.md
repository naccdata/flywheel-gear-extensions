# Development Guide

This is the development guide for the NACC flywheel gear extensions repo.

This document deals with working with existing gears.
To add new code see the [Adding a New Gear](#adding-a-new-gear)

## Contents
- [Development Guide](#development-guide)
  - [Contents](#contents)
  - [Getting Started](#getting-started)
    - [Basic environment](#basic-environment)
    - [Setting up build tool](#setting-up-build-tool)
    - [Setting virtual environment](#setting-virtual-environment)
  - [Repository structure](#repository-structure)
  - [Gear basics](#gear-basics)
  - [Working with a gear](#working-with-a-gear)
    - [Validating the manifest](#validating-the-manifest)
    - [Building a gear](#building-a-gear)
    - [Publishing a gear](#publishing-a-gear)
    - [Running a gear locally](#running-a-gear-locally)
      - [Basic configuration](#basic-configuration)
      - [Gear-specific configuration](#gear-specific-configuration)
      - [Environment Variables](#environment-variables)
      - [Run the gear](#run-the-gear)
  - [Adding a new gear](#adding-a-new-gear)
  - [Adding common code](#adding-common-code)
  - [Adding new dependencies](#adding-new-dependencies)
  - [Working with code](#working-with-code)
  - [Documenting and versioning](#documenting-and-versioning)


## Getting Started

### Basic environment

This repository can be used within a VS Code devcontainer using a python3 environment with the Flywheel cli installed.
To use it you will need to install VSCode, Docker, and [enable dev containers within VSCode](https://code.visualstudio.com/docs/devcontainers/containers).
Then open the repository in VS Code and start the container.

Because the build tool comes with its own Python interpreter, you may be able to work without the devcontainer.
But, if you don't use the devcontainer you will at least need to install the FW cli and be sure it is on your path.
Information on installing the `fw-beta` CLI can be found [here](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/).

### Setting up build tool

The build is managed using [Pants](https://www.pantsbuild.org).

Pants is installed in the devcontainer.
You can double check that it is available by running the command `pants version`.
If pants hasn't been run before the command will bootstrap the pants environment.

> If at any point you get an error that the pants command is not found, run the command
>
> ```bash
> bash get-pants.sh
> ```
>
> and the commands in this document should work.

At this point, you should be able to run the commands

- `pants version`, and
- `fw-beta --version`

without error.

### Setting virtual environment 

You need to export the virtual environment to enable VSCode access to the python dependencies:

   ```bash
   bash bin/set-venv.sh
   ```

You may need to reopen the repository in VSCode for it to catch the virtual environment.

This script creates a new `python-default.lock` file if it does not exist.
If you update requirements.txt, you need to update dependencies using

   ```bash
   pants generate-lockfiles
   ```

and then export the environment again.

Pants details may change, so if you run into any warnings/errors, consult the [instructions for setting up an IDE](https://www.pantsbuild.org/docs/setting-up-an-ide).

## Repository structure

The repository is setup to manage a set of gears with a common library.
The gears are located in the `gear` directory, and the library in the `common` directory.

```bash
.
├── bin                 # utility scripts
├── common              # shared code
├── docs                # documentation
├── gear
├── mypy-stubs          # type stubs for flywheel SDK
├── dist                # Directory containing distributions built by Pants
├── mypy.ini            # init file for mypy type checking
├── pants               # Pants script
├── pants.toml          # Pants configuration
├── python-default.lock # dependency lock file
├── requirements.txt    # Dependencies for full repo
├── BUILD               # Build declaration of python dependencies
├── LICENSE
└── README.md
```

[To update this structure, use `tree -L 1` and revise so that this matches that output.]

## Gear basics

A gear is a Docker container that has an entrypoint script and a manifest describing the gear, but in particular the input and output of the script.

Each gear directory in this repository looks like

```bash
.
├── src
│   ├── docker              # gear configuration
│   │   ├── BUILD           # - build file for gear
│   │   ├── Dockerfile      # - Docker configuration for gear
│   │   └── manifest.json   # - gear manifest
│   └── python              # script configuration
│       └── app_package     # app specific directory name
│           ├── BUILD       # - build file for script
│           ├── main.py     # - main function for script
│           └── run.py      # - entry point script 
└── test
  └── python              # script tests
```

The key parts being the manifest and script files.
The scripts are inspired by Flywheel's [template project](https://gitlab.com/flywheel-io/scientific-solutions/gears/templates/skeleton).
(Flywheel's template assumes one Gear per repository, which doesn't work for a monorepo.)
In that template, the Gear has two scripts `run.py` and `main.py` (or, rather, a file with a name specific to the app).
The `run.py` script manages the environment, and the `main.py` does the computation.


The `BUILD` files are configuration files for the pants build system.

See the [Gear Details](gear-details.md) for more information about how the script and manifest correspond.


## Working with a gear

Most actions on gears use the Flywheel CLI.
The repo is setup to use the [`fw-beta` CLI tool](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/).
(If you are working within the VSCode devcontainer, `fw` is an alias for `fw-beta`.)


### Validating the manifest

Validate the manifest with the command

```bash
fw-beta gear --validate gear/<project-dir>/src/docker/manifest.json
```

### Building a gear

The build is managed using [Pants](https://www.pantsbuild.org), and the gear can be built with the following command:

```bash
# to force rebuild use the --no-local-cache flag
pants package src/docker::
```

If you are building on macOS and get a permissions error for a cache file, you can set write permissions for the file in the error and rerun the package command.
This error seems to be a bug related to the VirtioFS of the Docker virtual machine.
A suggested alternative from pants is to setting the file sharing to gRPC FUSE.
This setting is Docker Desktop under Settings/General/Virtual Machine Options.

If you are building/running on macOS with an Apple Silicon chip, building a docker image with the correct architecture is a bit more involved. The following was added to the root BUILD file to support this, so should also handle all the gear builds, but you can update/change how its done for your specific gear.

```
file(name="linux_x86_py312", source="linux_x86_py312.json")

__defaults__({
  pex_binary: dict(complete_platforms=["//:linux_x86_py312"]),
  docker_image: dict(build_platform=["linux/amd64"]),
})
```

`docker_image`'s `build_platform` [sets the target platform(s) for the docker image](https://www.pantsbuild.org/dev/reference/targets/docker_image#build_platform), whereas `pex_binary`'s `complete_platforms` similarly [specifies the platforms the built PEX should be compatible with](https://www.pantsbuild.org/stable/reference/targets/pex_binary#complete_platforms). The latter pulls from the `linux_x86_py312.json` file living in the root of the repo, which is pulled into the root's BUILD file.

### Publishing a gear

An important detail in publishing a gear is that Flywheel wont let you overwrite a previous version of a gear.
So, the image tag needs to be incremented in order to upload a modified version of the gear.

The steps for publishing a project as a gear are

1. If this is an updated version, increment the image tag in both `gear/<project-dir>/src/docker/BUILD` and `gear/<project-dir>/src/docker/manifest.json`.
   The tags in these files need to match.

2. Change into the project directory

   ```bash
   cd gear/<project-dir>
   ```

   Otherwise, precede the paths in commands below with this path.

3. Create the docker image (see the previous section [Building a gear](#building-a-gear) for more details).

   ```bash
   pants package src/docker::
   ```

   > Using `fw-beta gear build` will build the image incorrectly because `fw-beta` is unaware of the need to pull the pex file from `gear/<project-dir>/src/python`.

4. Login to the FW instance using `fw-beta login` and your API key.

5. [Upload the gear (the image and manifest) to Flywheel](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/upload/)

   ```bash
   fw-beta gear upload src/docker
   ```

   > Do not use the `pants publish` command. This command is meant to push an image to an image repository such as dockerhub, and cannot be used to upload a gear to Flywheel.

   If you get a message that `Gear already exists`, start over at the first step.

### Running a gear locally

Before you run the following be sure that `gear/<project-dir>/src/docker/.gitignore` has a line `config.json`.

#### Basic configuration

The following steps are generalized in `bin/set-up-gear-for-local-run.sh` to automate some of the set up. Assumes the script is being run from the root directory due to local paths.

```bash
./bin/set-up-gear-for-local-run.sh <project-dir> <FW_API_KEY> [FW path]
```

1. Change into the project directory

   ```bash
   cd gear/<project-dir>
   ```
 
2. Use defaults from the manifest

   ```bash
   fw-beta gear config --new src/docker
   ```

3. set api key

   ```bash
   fw-beta gear config -i api_key=$FW_API_KEY src/docker
   ```

4. Set destination for output

   ```bash
   fw-beta gear config -d <FW path> src/docker
   ```

The destination should be the path for a Flywheel container.
For instance, if the gear has no output, could use the admin project: `nacc/project-admin`.

#### Gear-specific configuration

<i>To see what values need to be set</i>, use the command

```bash
fw-beta gear config --show <project-dir>/src/docker
```

>Defaults should already be set in `config.json` for any config or input keys that have them in the manifest.
You may need to set these for your local run, which may be easier to do by editing the `config.json` file directly.

<i>For any config values that need a value</i> use the command
   
```bash
fw-beta gear config -c <key-value-assignment> <project-dir>/src/docker
```

where `<key-value-assignment>` should be of the form `key=value` using a key from the manifest.

<i>To set input values</i>, the command is similar except use the `-i` option instead of `-c`.

```bash
fw-beta gear config -i <key-value-assignment> <project-dir>/src/docker
```

where `<key-value-assignment>` should be of the form `key=value` using a key from the manifest.

> If a parameter value has a complex type, it may be difficult to convince your command shell to pass the value correctly. In this case, it can be easier to give a dummy value and edit the `config.json` afterward.

> Similarly, If you want to use a file that already exists in Flywheel (which you will probably want to if your gear pulls metadata from Flywheel such as the project context or file.info) it is easiest to set the input value using a dummy file and replace the file metadata manually. At minimum this means ensuring `file_id` is set, which you can look up with the Flywheel SDK.

Consult `fw-beta gear config --help` for details on the command.

#### Environment Variables

Flywheel CLI version >= 0.19.0 is required to pass environment variables through to Docker.

Environment variables can be passed to the docker run command using pass-through arguments ([docs](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/run/#pass-through-arguments)):

```bash
fw-beta gear run tmp/gear/<gear-structure> -- -e xx=yy
```

Or, if using a .env file:

```bash
fw-beta gear run tmp/gear/<gear-structure> -- --env-file .env
```

>Note the templating script creates a project `.env` file automatically, so you may want to specify a different development file i.e. `.env.local` to store secrets. 

#### Run the gear

Once the values in the `config.json` are as needed, and any environment variables set, you need to "prepare" the gear which creates the work environment

```bash
fw-beta gear run -p <project-dir>/src/docker
```

this will build a file structure in `tmp/gear` using the image name.
You need to use this directory in the run command.

Then [run the gear](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/run/)  with the command

```bash
fw-beta gear run tmp/gear/<gear-structure>
```

where `<gear-structure>` is the directory indicated by the "prepare" command.

As of `fw-beta` version 0.18.0 you can also pass docker arguments directly by using `--` followed by the args. See [Flywheel's usage docs](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/run/#usage) for more information.

If you are running on macOS with Apple Silicon, you will also need to specify the correct platform for docker run. This can be done by either explicitly passing it through the `fw-beta` command or setting the default docker platform flag:

```bash
# needs fw-beta 0.18.0+
fw-beta gear run <project-dir>/src/docker -- --platform=linux/amd64

# OR set the environment variable flag
export DOCKER_DEFAULT_PLATFORM=linux/amd64
```

## Adding a new gear

Within the VS Code devcontainer, run

```bash
pipx install cookiecutter
```

If you are not using the devcontainer, see the [cookiecutter docs](https://cookiecutter.readthedocs.io/en/2.5.0/README.html) for installation.

Run cookiecutter from the root directory of the monorepo

```bash
cookiecutter templates/gear --output-dir gear/
```

You will then be prompted to instantiate the gear.
Type `enter` to accept the default value, or provide a new value.

```
  [1/9] gear_name (Gear Name): Junk Gear
  [2/9] gear_description (A NACC gear for Flywheel): A junk gear for trying this out
  [3/9] package_name (junk-gear): 
  [4/9] module_name (junk_gear): 
  [5/9] app_name (junk_gear_app): junk_app
  [6/9] class_name (JunkGear): JunkGearExecution
  [7/9] image_tag (0.0.1):
  [8/9] author (NACC):
  [9/9] maintainer (NACC <nacchelp@uw.edu>):
```

This will create a directory with the structure

```bash
junk_gear
├── src
│   ├── docker
│   │   ├── BUILD
│   │   ├── Dockerfile
│   │   └── manifest.json
│   └── python
│       └── junk_app
│           ├── BUILD
│           ├── main.py
│           └── run.py
└── test
    └── python
```

Because this directory is generated by templating, it may not be configured how you want.
The following are details you might want to check.

1. The `python_sources` name argument in `src/python/junk_app/BUILD`.
2. The Docker image name in the `src/docker/BUILD` and `src/docker/manifest.json` files, which need to match.
   
To complete the gear, you will need to 

1. Change the `config`, `inputs`, and `outputs` in the `manifest.json` file to describe the interface of the gear.
2. Change `run.py` to pull the `config`, `inputs` and `outputs` arguments described in the `manifest.json`.
3. Modify `main.py` so that it performs the computation of the gear.
   
Generally, `run.py` should handle gathering any inputs, and `main.py` should handle the computation.
The `common` directory includes common code that may be used across the gears.

Additionally, you should also document your gear, which can also be generated using a cookiecutter template:

```bash
cookiecutter templates/docs --output-dir docs/
```

which will create the following directory structure:

```bash
junk_gear
├── CHANGELOG.md
└── index.md
```

The `index.md` should describe your gear as well as the expected inputs and outputs/results, whereas the Changelog should keep track of gear versions. See [Documenting and versioning](#documenting-and-versioning) for more information.

## Adding common code

If you need to add a file to the common library, either place it in an existing subdirectory for the package that makes the most sense, or create a directory for a new package.

```bash
cookiecutter templates/common --output-dir common/src/python/
```

You will then be prompted to instantiate the package

```bash
  [1/2] library_name (Library Name): Junk Library
  [2/2] package_name (junk_library): 
```

This will add a new package structure in the directory `common/src/python/junk_library`:

```bash
common/src/python/junk_library/
├── BUILD
├── __init__.py
└── junk_library.py
```

To implement tests, you should create a corresponding directory `common/test/python/junk_library` containing the pytest files.

## Adding new dependencies

If you add new python dependencies

1. Edit `requirements.txt` in the top directory and add your new dependencies.
2. Regenerate the lock file

    ```bash
    pants generate-lockfiles
    ```

## Working with code

1. Format everything

    ```bash
    pants fix ::
    ```

2. Format just the common subproject

    ```bash
    pants fix common::
    ```

3. Lint

    ```bash
    pants lint ::
    ```

4. Run tests for the common subproject

    ```bash
    pants test common::
    ```

5. Run type checker for the common subproject

    ```bash
    pants check common::
    ```

## Documenting and versioning

All gear documentation and version tracking is stored under `docs/<gear-name>`, each with at minimum an `index.md` (for documentation) and a `CHANGELOG.md` (for tracking gear versions), and should be added for every new gear. The documentation only needs to be updated if new updates fundamentally change or deprecate previously documented features. The Changelog on the other hand should be updated consistently whenever any notable changes or bugfixes are added.

The Changelogs loosely follow the convention described in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the gears all follow semantic versioning. All working changes should be added under the **Unreleased** header, and if a PR is associated with the change, the PR should be linked as well. 

Releases and version bumping are currently done manually. When releasing a new version of the gear, ensure the following have been updated:

* Increment the gear's image tag in the following files:
    * `src/docker/BUILD`: the `image_tags` field 
    * `src/docker/manifest.json`: the `version` and `custom/gear-builder/image` fields
* In the `CHANGELOG.md`, move all changes under the **Unreleased** header to a new header under the new release version
    * Right now it'll be a chicken and egg problem, but if you can try to also link the corresponding commit to the release version header

See [this commit](https://github.com/naccdata/flywheel-gear-extensions/commit/fa3ff5ab5218282299b9c67665beacb90f5d8244) for an example of updating the version and image tags in the code.
