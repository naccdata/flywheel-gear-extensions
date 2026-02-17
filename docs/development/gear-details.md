# Gear project organization

## Gear project directory structure

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

## Gear scripts

The scripts are inspired by Flywheel's [template project](https://gitlab.com/flywheel-io/scientific-solutions/gears/templates/skeleton).
(Flywheel's template assumes one Gear per repository, which doesn't work for a monorepo.)
In that template, the Gear has two scripts `run.py` and `main.py` (or, rather, a file with a name specific to the app).
The `run.py` script manages the environment, and the `main.py` does the computation.

Each `run.py` script will have this structure.

```python
def main():
    with GearContext() as gear_context:
        gear_context.init_logging()
        ... # get arguments from gear context (refs manifest file)
    
    ... # gather any information based on arguments
    run(...) # call run method from main.py
```

The `GearContext` parses command-line arguments and sets them within the context.
Extra command-line arguments given when the script is run are added to the context.
However, any checks that would be enforced by an argument parser are not available, and have to be written explicitly.

The `main.py` script defines a `run` method that performs the computation.
Most of the work is done by calling code from the `common` subdirectory.

## On API Keys

Most gears will require an API key with the most common scenario being using the user's API key.
In this case, `api-key` should be included in the `inputs` section of the manifest, and then the client can be pulled from the `GearContext` as

```python
...
    with GearContext() as gear_context:
        ...
        client = gear_context.client
...
```

An alternate scenario is to use the gear bot API key.
NACC's Flywheel instance is configured to provide environment variables with 
AWS credentials for accessing the gear bot key in the parameter store.
This is done with `inputs.parameter_store.get_parameter_store()`.

## Dockerfile

The Dockerfile sets up the Gear's working environment

   ```docker
   FROM python:3.12

   ENV BASE_DIR=/flywheel/v0
   RUN mkdir -p ${BASE_DIR}/input

   WORKDIR ${BASE_DIR}

   COPY project_management/src/docker/manifest.json ${BASE_DIR}
   COPY project_management.src.python/bin.pex /bin/run

   ENTRYPOINT [ "/bin/run" ]
   ```

The key details are setting up the `/flywheel/v0` directory with the manifest file, and copying the binary pex file into the image with it set as the entrypoint for the container.

## Gear manifest

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

   Running `package` on `project_management/src/docker` builds two images `naccdata/project-management:0.0.1` and `naccdata/project-management:latest`.
   (Note that the `naccdata/` prefix to the repository name is set in `pants.toml`.)

   The manifest file needs to match these image details in three ways.
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