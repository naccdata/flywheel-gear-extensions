# Development Guide

This is the development guide for the NACC flywheel gear extensions repo.

## Repository structure

```bash
.
├── bin                 # utility scripts
├── common              # shared code
│   ├── src
│   └── test
├── directory_pull      # gear script to pull users from directory
│   ├── src
│   └── test
├── docs                # documentation
│   ├── development
│   ├── directory_pull
│   ├── index.md
│   ├── project_management
│   ├── push_template
│   └── user_management

├── mypy-stubs          # type stubs for flywheel SDK
│   └── src
├── project_management  # gear script for managing NACC projects
│   ├── data
│   ├── src
│   └── test
├── push_template       # gear script to push template projects
│   ├── src
│   └── test
├── user_management     # gear script for managing project users
│   ├── directory
│   ├── src
│   └── test
├── dist                # Directory containing distributions built by Pants
├── mypy.ini
├── pants               # Pants script
├── pants.toml          # Pants configuration
├── python-default.lock # dependency lock file
├── requirements.txt    # Dependencies for full repo
├── BUILD               # Build declaration of python dependencies
├── LICENSE
└── README.md
```

[To update this structure, use `tree -L 2` and select missing chunks for inclusion.]

## Getting Started

### Basic environment

This repository can be used within a VS Code devcontainer using a python3 environment with the Flywheel cli installed.
To use it you will need to install VSCode, Docker, and enable dev containers within VSCode.
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
> bash bin/get-pants.sh
> ```
>
> and the commands in this document should work.

At this point, you should be able to run the commands

- `pants version`, and
- `fw-beta --version`

without error.

## Working within VSCode

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

## Gear project organization

### Gear project directory structure

Each gear project will have a directory structure like this

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

A project might include other subdirectories, and the directory `src/python/app_package` should have a name specific to the app.
For instance, the `project_management` directory looks like

```bash
project_management/
├── data
│   └── test-project.yaml
├── src
│   ├── docker
│   │   ├── BUILD
│   │   ├── Dockerfile
│   │   └── manifest.json
│   └── python
│       └── project_app
│           ├── BUILD
│           ├── __init__.py
│           ├── main.py
│           └── run.py
└── test
    └── python
```

where the `app_package` directory is named `project_app`.

Each [build file](https://www.pantsbuild.org/docs/targets) contains metadata about the code and indicates build sources and targets.

For instance, the `project_management/src/python/project_app/BUILD` file contains

   ```python
   python_sources(name="project_app", )

   pex_binary(name="bin", entry_point="run.py")
   ```

which indicates the python directory contains the sources for the `project_app`, and has a build target named `bin` with the `run.py` script as the entrypoint.
(There is no requirement that the sources name and the subdirectory name match.)

And `project_management/src/docker/BUILD` contains

   ```python
   file(name="manifest", source="manifest.json")

   docker_image(name="project-management",
               source="Dockerfile",
               dependencies=[":manifest", "project_management/src/python:bin"],
               image_tags=["0.0.1", "latest"])
   ```

which describes a Docker image target that depends on the manifest file, and the pex target in the python directory.

### Gear scripts

The scripts are inspired by Flwheel's [template project](https://gitlab.com/flywheel-io/scientific-solutions/gears/templates/skeleton).
(Flywheel's template assumes one Gear per repository, which doesn't work for a monorepo.)
In that template, the Gear has two scripts `run.py` and `main.py` (or, rather, a file with a name specific to the app).
The `run.py` script manages the environment, and the `main.py` does the computation.

Each `run.py` script will have this structure.

```python
def main():
    with GearToolkitContext() as gear_context:
        gear_context.init_logging()
        ... # get arguments from gear context (refs manifest file)
    
    ... # gather any information based on arguments
    run(...) # call run method from main.py
```

The `GearToolkitContext` parses command-line arguments and sets them within the context.
Extra command-line arguments given when the script is run are added to the context.
However, any checks that would be enforced by an argument parser are not available, and have to be written explicitly.

The `main.py` script defines a `run` method that performs the computation.
Most of the work is done by calling code from the `common` subdirectory.

### On API Keys

Most gears will require an API key with the most common scenario being using the user's API key.
In this case, `api-key` should be included in the `inputs` section of the manifest, and then the client can be pulled from the `GearToolkitContext` as

```python
...
    with GearToolkitContext() as gear_context:
        ...
        client = gear_context.client
...
```

An alternate scenario is to use the gear bot API key.
NACC's Flywheel instance is configured to provide environment variables with 
AWS credentials for accessing the gear bot key in the parameter store.
This is done with `inputs.parameter_store.get_parameter_store()`.

### Dockerfile

The Dockerfile sets up the Gear's working environment

   ```docker
   FROM python:3.10

   ENV BASE_DIR=/flywheel/v0
   RUN mkdir -p ${BASE_DIR}/input

   WORKDIR ${BASE_DIR}

   COPY project_management/src/docker/manifest.json ${BASE_DIR}
   COPY project_management.src.python/bin.pex /bin/run

   ENTRYPOINT [ "/bin/run" ]
   ```

The key details are setting up the `/flywheel/v0` directory with the manifest file, and copying the binary pex file into the image with it set as the entrypoint for the container.

### Gear manifest

The manifest is a JSON file that defines the metadata for the gear.
Look at the FW gear documentation for more detail, but there are three key details and how they relate to other files in the directories for each gear project.

1. The manifest has fields that should correspond to the `docker/BUILD` file.
   This build file defines the Docker image target, which needs to be referenced in the manifest.

   To illustrate, the `docker/BUILD` file for `project_management` defines

   ```python
   docker_image(name="project-management",
             source="Dockerfile",
             dependencies=[":manifest", "project_management/src/python/project_app:bin"],
             image_tags=["0.0.1", "latest"])
   ```

   Running `package` on `projectmanagement/src/docker` builds two images `naccdata/project-management:0.0.1` and `naccdata/project-management:latest`.
   (Note that the `naccdata/` prefix to the repository name is set in `pants.toml`.)

   The mainfest file needs to match these image details in three ways.
   First, the `name` field should correspond to the `docker_image` target name in the build file.
   Second, the `custom.gear-builder.image` should be the full repository name for the image.
   And, third, the `version` field should correspond to tag of the image used in `custom.gear-builder.image`.

   So, for instance, the manifest file for `project_management` has

   ```json
   {
       "name": "project-management",
       ...
       "version": "0.0.1",
       ...
       "custom": {
           "gear-builder": {
               "category": "utility",
               "image": "naccdata/project-management:0.0.1"
           },
           ...
       },
       ...
   }
   ```

2. If the gear takes an input file, this should be named in the `inputs` within the manifest.
   The name has to be used within the `run.py` script to find the file.

   For instance, the project_management gear manifest has

   ```json
   {
    ...
       "inputs": {
           "project_file": {
               "description": "The project YAML file",
               "base": "file",
               "type": {
                   "enum": [
                       "source code"
                   ]
               }
           }
       },
    ...
   }
   ```

3. If the gear requires a user API key, the following needs to be added to the `inputs`:

```json
{
 ...
    "inputs": {
        ...
        "api-key": {
            "base": "api-key"
        }
        ...
    }
 ...
}
```

4. Any other arguments to the  script collected in `run.py` should be given in the `config` of the manifest

   For instance, the project_management manifest file has

   ```json
   {
    ...
       "config": {
           "dry_run": {
               "description": "Whether to do a dry run",
               "type": "boolean",
               "default": false
           },
           "admin_group": {
               "description": "Name of the admin group",
               "type": "string",
               "default": "nacc"
           },
           "new_only": {
               "description": "Only create projects for centers tagged as new",
               "type": "boolean",
               "default": false
           }
       },
    ...
   }
   ```

5. The manifest indicates how to run the script.
   For this we need to know that the Dockerfile places the pex file in `/bin/run`.
   So, the gear is executed as `/bin/run`, which is indicated in the manifest as

   ```json
   {
    ...
       "command": "/bin/run"
   }
   ```

### Gear documentation

In addition to the project directory, each gear has a directory in `docs` that contains an `index.md` file.

## Adding a new gear

The `bin/new_gear.sh` script will set up the directories for a new gear.
The script takes the project name (and assumes snakecase)

```bash
bash bin/new_gear.sh zebra_management
```

This will create a directory with the name given and the structure

```bash
zebra_management
├── src
│   ├── docker
│   │   ├── BUILD
│   │   ├── Dockerfile
│   │   └── manifest.json
│   └── python
│       └── zebra_app
│           ├── BUILD
│           ├── main.py
    │       └── run.py
└── test
    └── python
```

Make the following changes:

1. Check the `BUILD` files and make sure the target and dependency names match what you expect.

   You may want to edit the `python_sources` name argument in `zebra_management/src/python/zebra_app/BUILD` to set a new app name.
   By default it will pick the prefix before the underscore, so the default app name for a gear named `zebra_management` will be `zebra_app`.
   Similarly, the Docker image will be named `zebra-management`, replacing the underscore with a hyphen.
   If you want to change this, you'll need to change the image name in both the `docker/BUILD` and `docker/manifest.json` files.

2. Edit the `manifest.json` file

   At the top level, change the `name`, `label`, `description`, `version`, `author`.
   Under `custom.gear-builder` update `image` with the information from the `docker/BUILD` file.
   Then make any changes needed for the command line arguments to `inputs` and `config`.
   By default the script will use the prefix before the underscore to name the file key for `inputs`, and for a project named `zebra_management` will use `zebra_file` as the key in the manifest and the `run.py` script.
   Make sure these details should match up with the information used by your `run.py` script to get parameters.

To complete the gear, you will likely need to make changes to `run.py` and the `main` scripts.
In `run.py`, add anything that needs to be done gathering information from the environment, and the main script will do the actual computation mostly using code from the `common` directory.
There may be exceptions to this scheme.
For instance, the `directory_pull` script uses `run.py` without a main script because it behaves differently depending on whether it is run as a gear.

## Adding common code

If you need to add a file to the common library, either place it in an existing subdirectory for the package that makes the most sense, or create a directory for a new package.

If you need to create a new package structure, add the subdirectory with the code, add an `__init__.py` file, and then run `pants tailor ::`.
Then change the new `BUILD` file so that it contains the line `python_sources(name="lib")`

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
    pants fmt ::
    ```

2. Format just the common subproject

    ```bash
    pants fmt common::
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

6. Run the project management script (The `--` is required before the arguments)

    ```bash
    pants run project_management/src/python/run.py --  --no-gear project_management/data/test-project.yaml
    ```

    or

    ```bash
    pants run project_management/src/python:bin --  --no-gear project_management/data/test-project.yaml
    ```

    > Scripts will expect that `FW_API_KEY` is set.
    > Do this by using `export FW_API_KEY=XXXXXX` using your FW key at the command line.
    > Do not set the environment variable in the pants configuration, or otherwise commit your key into the repo.

## Working with a gear

Most actions on gears use the Flywheel CLI.
The repo is setup to use the [`fw-beta` CLI tool](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/).
(If you are working within the VSCode devcontainer, `fw` is an alias for `fw-beta`.)


### Validating the manifest

Validate the manifest with the command

```bash
fw-beta gear --validate <project-dir>/src/docker/manifest.json
```

### Publishing a gear

An important detail in publishing a gear is that Flywheel wont let you overwrite a previous version of a gear.
So, the image tag needs to be incremented in order to upload a modified version of the gear.

The steps for publishing a project as a gear are

1. If this is an updated version, increment the image tag in both `<project-dir>/src/docker/BUILD` and `<project-dir>/src/docker/manifest.json`.
   The tags in these files need to match.

2. Create docker image

   ```bash
   pants package <project-dir>/src/docker::
   ```

   > Using `fw-beta gear build` will build the image incorrectly because `fw-beta` is unaware of the need to pull the pex file from `<project-dir>/src/python`.

3. Login to the FW instance using `fw-beta login` and your API key.

4. [Upload the gear (the image and manifest) to Flywheel](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/upload/)

   ```bash
   fw-beta gear upload <project-dir>/src/docker
   ```

   > The `pants publish` command is meant to push an image to an image repository such as dockerhub, and cannot be used to upload a gear to Flywheel.

   If you get a message that `Gear already exists`, start over at the first step.

### Running a gear locally

Before you run the following be sure that `<project-dir>/src/docker/.gitignore` has a line `config.json`.

First [configure](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/config/) the gear:

1. Use defaults from the manifest

   ```bash
   fw-beta gear config --create <project-dir>/src/docker
   ```

2. set api key

   ```
   fw-beta gear config -i api_key=$FW_API_KEY <project-dir>/src/docker
   ```

3. Set destination for output

   ```bash
   fw-beta gear config -d <FW path> <project-dir>/src/docker
   ```

   The destination should be the path for a Flywheel container.
   For instance, if the gear has no output, could use the admin project: `nacc/project-admin` .

Then to [run the gear](https://flywheel-io.gitlab.io/tools/app/cli/fw-beta/gear/run/)  use the command

```bash
fw-beta gear run <project-dir>/src/docker
```

