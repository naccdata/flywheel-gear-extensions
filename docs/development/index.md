# Development Guide 

## Directory structure

```bash
.
├── common              # shared code
│   ├── src
│   └── test
├── project_management  # script for managing NACC projects
│   ├── data
│   ├── src
│   └── test
├── user_management     # script for managing project users
│   ├── directory
│   ├── src
│   └── test
├── dist                # Directory containing distributions built by Pants
├── pants               # Pants script
├── pants.toml          # Pants configuration
├── python-default.lock # dependency lock file
├── requirements.txt    # Dependencies for full repo
├── BUILD               # Build declaration of python dependencies
├── LICENSE
└── README.md
```

## Care and feeding

### Adding new project

To add a new project

1. Create directory structure
    ```bash
    bash bin/new_gear.sh <new-project-name>
    ```
2. Add configuration for new code/directories
    ```bash
    ./pants tailor ::
    ```

### Adding new dependencies

If you add new python dependencies

1. Edit requirements.txt and add your new dependencies
2. Update dependencies (after editing requirements.txt)
    ```bash
    ./pants generate-lockfiles
    ```

### Working with code

1. Format everything
    ```bash
    ./pants fmt ::
    ```

2. Format just the common subproject
    ```bash
    ./pants fmt common::
    ```

3. Lint
    ```bash
    ./pants lint ::
    ```

4. Run tests for common subproject
    ```bash
    ./pants test common::
    ```

5. Run the create project script (The `--` is required before the arguments)
    ```bash
    ./pants run project_management/src/python/run.py --  project_management/data/test-project.yaml
    ```
    or
    ```bash
    ./pants run project_management/src/python:bin --  project_management/data/test-project.yaml
    ```

> Scripts will expect that `FW_API_KEY` is set.
> Do this by using `export FW_API_KEY=XXXXXX` using your FW key at the command line.
> Do not set the environment variable in the pants configuration, or otherwise commit your key into the repo.

### Working with docker images

1. Create docker image
    ```bash
    ./pants package project_management/src/docker::
    ```

2. Run docker image
    ```bash
    ./pants run project_management/src/docker::
    ```

Note: don't use `./pants publish` with Gears, need to use the `fw gear` commands to push to the FW instance instead.

### Working with a gear

For `fw gear` commands to work properly, the manifest.json file needs to be in the current working directory.
So, start by changing to ing docker directory where manifest.json is located.
For instance,

    ```bash
    cd project_management/src/docker
    ```

At which point you can use the [fw gear local](https://docs.flywheel.io/hc/en-us/articles/360037690613-Gear-Building-Tutorial-Part-2e-Gear-Testing-Debugging-Uploading) commands.

## Working within VSCode

This repository is setup with a VSCode devcontainer. 
To use it you will need to install VSCode, Docker, and enable dev containers within VSCode.
When you open the repository within the devcontainer, the environment is a python3 container, with the flywheel cli installed.

To enable VSCode access to the python dependencies, follow the [instructions for setting up an IDE](https://www.pantsbuild.org/docs/setting-up-an-ide).