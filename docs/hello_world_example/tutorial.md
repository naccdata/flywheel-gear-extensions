# Hello World Gear

The following tutorial outlines developing and running a basic gear in the context of NACC's Flywheel environment.

**Please do this tutorial on a separate branch and do NOT push your hello-world gears to main.**

## Set Up

Before we begin, please ensure you have access to NACC's Sandbox Flywheel instance ([nacc.flywheel.io](https://naccdata.flywheel.io/)), as well as read-write permissions to the [hello-world](https://naccdata.flywheel.io/#/projects/6792d642e6aa584a8b16cf7a) project this tutorial will take place in. If you do not have access, reach out to the NACC Tech Team or [nacchelp@uw.edu](mailto:nacchelp@uw.edu).

> While not strictly necessary for this tutorial, if you want to actually upload the gear to Flywheel you will also need site-wide admin access - if you do not require site-level admin access otherwise, you can use a version of this gear already uploaded to Flywheel.

Additionally, it is advised to do gear development in the VS Code devcontainer environment, otherwise you may run into build issues (developing on MacOS with Apple Silicon in particular is known to be finicky about this). You can follow the steps in the [Getting Started](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md#getting-started) guide.

> Even if you opt out of using the VS Code devcontainer, you will still need [Pants](https://www.pantsbuild.org/) installed in your environment in order to build the gears.

While this tutorial will go through each component explicitly, it will echo a lot of the documentation already provided in the [Development Guide](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md) which is a great general guide for gear development. Flywheel's [Gear Development Guide](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_1_developing_gears/) is also a great resource, particularly in regards to Flywheel-specific nuances.

# Hello World

In this tutorial we will write a basic gear that reads a plain text input file containing a subject label and associated metadata, creates a subject based on that information, and also writes an output file to that subject. Along the way it will grab information about the context the gear it is running in to illustrate navigating through the Flywheel hierarchy. We will then walk through how to execute the gear, both locally and through the UI. 

A complete example of this can be found under `hello_world_example`.

**Please do this tutorial on a separate branch and do NOT push your hello-world gears to main.**

## Creating The Gear

Also see [Adding a New Gear](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md#adding-a-new-gear) in the Development Guide.

Each gear is set up using [cookiecutter](https://cookiecutter.readthedocs.io/en/stable/installation.html) templates. Ensure `cookiecutter` is installed in your environment, and then in the root of the repo run

```bash
cookiecutter templates/gear --output-dir gear/
```

with the following values when prompted (defaults are used for everything except steps 1 and 2)

```bash
[1/9] gear_name (Gear Name): Hello World
[2/9] gear_description (A NACC gear for Flywheel): Hello World tutorial gear
[3/9] package_name (hello-world): 
[4/9] module_name (hello_world): 
[5/9] app_name (hello_world_app): 
[6/9] class_name (HelloWorld): 
[7/9] image_tag (0.0.1): 
[8/9] author (NACC): 
[9/9] maintainer (NACC <nacchelp@uw.edu>): 
```

You will now find your newly-created gear under `gear/hello_world`. The gear components are discussed in detail in [Gear Details](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/gear-details.md).

You will also want to set up the documentation for your gear, which is similarly created with

```bash
cookiecutter templates/docs --output-dir docs/
```

with the following values when prompted (defaults are used for everything except steps 1 and 2)

```bash
[1/3] gear_name (Gear Name): Hello World
[2/3] gear_description (A NACC gear for Flywheel): Hello World tutorial gear documentation
[3/3] module_name (hello_world): 
```

The generated docs can be found under `docs/hello_world`. This creates both an `index.md`, which is the written documentation for your gear, as well as the `CHANGELOG.md` for keeping track of the different versions. While not necessary just for the sake of developing a runnable gear, it is a good idea to keep these two files updated throughout gear iteration, not just for yourself but also your fellow developers. See [Documenting and Versioning](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md#documenting-and-versioning) for more details.

## Setting up the Configurations and Parameters

We will start by defining our gear's inputs and configuration values which are defined in the `manifest.json`. See [Flywheel's manifest documentation](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_5_the_manifest/) for more information on the manifest JSON.

### Manifest

For the current purposes of this tutorial, you can think of the manifest as where we define our **inputs** and **configuration values**, and lives under `src/docker/manifest.json`. The cookiecutter template will have already set up a basic one for you; update the `inputs` and `config` sections of the manifest to look like the following:

```json
    "inputs": {
        "api-key": {
            "base": "api-key"
        },
        "input_file": {
            "description": "The input file containing the name of the subject to create",
            "base": "file",
            "type": {
                "enum": [
                    "source code"
                ]
            }
        }
    },
    "config": {
        "output_filename": {
            "description": "Name of output file to write to",
            "type": "string"
        },
        "local_run": {
            "description": "Whether or not this is a local run",
            "type": "boolean",
            "default": false
        },
        "target_project_id": {
            "description": "Target project ID, must be set to a valid Flywheel project ID if using local_run. Otherwise if set to the empty string, uses the input_file's parent project.",
            "type": "string",
            "default": ""
        },
        "dry_run": {
            "description": "Whether to do a dry run",
            "type": "boolean",
            "default": false
        },
        "apikey_path_prefix": {
            "description": "The instance specific AWS parameter path prefix for apikey",
            "type": "string",
            "default": "/sandbox/flywheel/gearbot"

        }
```

### API Keys

Notice how we left in `api-key` and `apikey_path_prefix` - these are included in every gear we write, and are necessary to ensure the correct user permissions are being used within the given gear context.

The `api-key` corresponds to an user's Flywheel API key. `apikey_path_prefix` is similar - it tells the gear where in the AWS parameter store to grab the gear bot's API key. NACC's Flywheel instances are configured to provide the environment variables with AWS credentials necessary for the gear/gear bot to access AWS resources*, including said parameter store. See the [Gear Bot documentation](./gear-bot.md) for more information.

The Hello World gear does not actually need nor use the Gear Bot, as it is isolated to a single project (`example-center/hello-world`) - however most of the gears _will_ need it, so is left in for demonstration purposes.

> \* One important nuance is that a new gear will not automatically get these AWS environment variables passed - Flywheel needs to add it to the NACC credentials condor. The easiest way is to send [Flywheel a support ticket](https://support.flywheel.io/hc/en-us/requests/new) and ask for the gear(s) "to be added to the credentials condor". This `hello-world` gear we are about to write is already on the list, so you do not have to worry about that for this tutorial.

### Output Files

Flywheel and its gears are file-based, so any dynamic input value should come from an input file. Configuration parameters on the other hand usually remain relatively static within a given context; for example setting `apikey_path_prefix` to either `/sandbox/flywheel/gearbot` or `/prod/flywheel/gearbot`. This is especially true if the gear is intended to be automatically triggered via [Gear Rules](https://docs.flywheel.io/user/compute/gears/user_gear_rules/), which we will talk about in more detail later in this tutorial.

Outputs are defined a little less explicitly - essentially, _any_ file saved to the `output` directory in Flywheel's hierarchy will be saved under the corresponding acquisitions if it's an utility gear, or in the separate analysis container if an analysis gear. See [The Flywheel Environment](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_3_the_flywheel_environment/) for more information.

Within NACC, however, we tend to directly write/upload files at all levels of the hierarchy - in this tutorial we will write a file and attach it to a subject. These must be _explicitly_ uploaded within your gear, which is why we have set the `output_filename` as a configuration value as opposed to an actual file. Either way, we usually "parameterize" the output file by specifying the output filename, to avoid having it hardcoded within the gear itself.

### Local Runs

Running a gear that locally is a bit tricky especially if you want to modify data, since local files don't have the container and metadata information associated with them the same way Flywheel containers and files do. Both the `local_run` and `target_project_id` variables will be used throughout the gear to get around that limitation.

## Developing the Gear

### run.py

Next we will define the `run.py`, which you can think of as the **entrypoint** to the gear (we will gloss over the specifics, but in a nutshell the Pants environment creates a binary executable `.pex` with this entrypoint which the Docker image/gear ends up calling). 

Navigate to `src/python/run.py` where a template has been set up. At the bottom you'll notice there is an executable `main` which sets up the [GearEngine](../common/src/gear_execution/gear_execution.py). This `GearEngine` sets up the `GearToolKitContext` (discussed in a moment) and runs the `HelloWorldVisitor`.

The commented out code showcases creating the `GearEngine` with a parameter store, which is required if using the Gear Bot. 

```python
def main():
    """Main method for Hello World."""
    GearEngine().run(gear_type=HelloWorldVisitor)

    # if using the Gear Bot
    # GearEngine.create_with_parameter_store().run(
    #     gear_type=HelloWorldVisitor)

if __name__ == "__main__":
    main()

```

Your job is to define the `HelloWorldVisitor` and its `run` method, which comes in two parts:

1. Define the `create` method. This works in conjunction with the `__init__` method and is generally where you pull configuration values from. This is done through the `GearToolkitContext`, which you can learn more about [here](https://flywheel-io.gitlab.io/public/gear-toolkit/flywheel_gear_toolkit/context/). This context is primarily how we handle reading in inputs/configuration values along with adding custom information, but is generally useful for other things as well (you can directly access [Flywheel's SDK client](https://flywheel-io.gitlab.io/product/backend/sdk/tags/19.5.0/python/index.html) through this context).

```python
class HelloWorldVisitor(GearExecutionEnvironment):
    """Visitor for the Hello World gear."""

    def __init__(self,
                 client: ClientWrapper,
                 input_file: InputFileWrapper,
                 target_project_id: str,
                 output_filename: str,
                 local_run: bool = False):
        super().__init__(client=client)

        if local_run and not target_project_id:
            raise ValueError("If local run is set to true, a "
                             "target project ID must be provided")

        self.__input_file = input_file
        self.__target_project_id = target_project_id
        self.__output_filename = output_filename
        self.__local_run = local_run

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'HelloWorldVisitor':
        """Creates a HelloWorldVisitor object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)

        # # Gear Bot version
        # client = GearBotClient.create(context=context,
        #                               parameter_store=parameter_store)

        output_filename = context.config.get('output_filename', None)
        target_project_id = context.config.get('target_project_id', None)
        local_run = context.config.get('local_run', False)

        if not output_filename:
            raise GearExecutionError("Output filename not defined")



        input_file = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        return HelloWorldVisitor(client=client,
                                 input_file=input_file,
                                 target_project_id=target_project_id,
                                 output_filename=output_filename,
                                 local_run=local_run)
```

* `client` is what interacts with Flywheel. You can also use a `ContextClient` will just use your API key (`api-key`), or the commented out version uses `GearBotClient` which uses the Gear Bot API Key, pulled from `apikey_path_prefix`, and is usually what is used for the majority of our NACC gears
    * Behind the scenes, this client is a wrapper around the `GearToolkitContext`'s client
    * Using the Gear Bot requires the correct AWS environment variables set up, which will be discussed more when we get to running the gear
* `context.config` allows you to access the configuration values like a normal Python dict; we pull out `output_filename` and ensure it's set, if not throw a GearExecutionError. Similarly we extract `target_project_id` and `local_run`, setting defaults if not defined
* Grabbing file inputs is done by creating an `InputFileWrapper`, which takes the specified file from the context and wraps it with useful methods and properties

The above are used to create a `HelloWorldVisitor`, which implements the abstract `GearExecutionEnvironment`. It uses the client to create a [FlywheelProxy](../common/src/python/flywheel_adaptor/flywheel_proxy.py) object, which will be our primary means of dealing with anything related to Flywheel.

2. Now let's look at the visitor's `run` method:

```python
from hello_world_app.main import run

    def run(self, context: GearToolkitContext) -> None:
        """Run the Hello World gear."""

        # if target project ID is not set, try to grab it from the
        # input file's parent
        try:
            if not self.__target_project_id:
                file_id = self.__input_file.file_id
                file = self.proxy.get_file(file_id)
                project = self.proxy.get_project_by_id(file.parents.project)
            else:
                project = self.proxy.get_project_by_id(self.__target_project_id)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file and/or project: {error}') from error

        project = ProjectAdaptor(project=project, proxy=self.proxy)
        log.info(f"Running in group {project.group}, project {project.label}")

        run(proxy=self.proxy,
            context=context,
            project=project,
            input_file=self.__input_file,
            output_filename=self.__output_filename,
            local_run=self.__local_run)
```

The `proxy` is our primary means of interacting with Flywheel, in particular looking up and grabbing data; it differs from `context` in that `context` is more about this specific execution whreas `proxy` is used for looking up things that already exist in Flywheel.

The try block is locating the actual file and project contexts from Flywheel using the file's ID, and throwing a `GearExecutionError` if the file does not exist (if doing a local run, we just directly pass the project ID). We then wrap project around a `ProjectAdaptor`, which wraps the raw project context into a wrapper with useful properties and methods.

We then execute the main `run`, which was imported from `hello_world_app.main`, which we will fill out in the next section.

### main.py

The next file we will look at `main.py`, which can be considered the main execution of your gear. This is where the actual "work" you want your gear to do should happen. In this case we have a single `run` method, but your gear could develop into a more detailed Python module.

The main thing to keep in mind is that this is a monorepo, and a lot of common code has already been extracted under `common/src/python`. It is advised to use the common code as much as possible.

The primary ones to use are the Flywheel adaptors, e.g. wrappers around Flywheel containers. We have already used `FlywheelProxy` and `ProjectAdaptor`, which is a proxy for the Flywheel client and adaptor for a Flywheel project, respectively. There are also adaptors for the Group (`GroupAdaptor`) and Subject ([SubjectAdaptor](../common/src/python/flywheel_adaptor/subject_adaptor.py))) containers, the latter of which we will use in this gear.

Our `main.run` method takes in the following parameters:

```python
def run(proxy: FlywheelProxy,
        context: GearToolkitContext,
        project: ProjectAdaptor,
        input_file: InputFileWrapper,
        output_filename: str,
        local_run: bool = False) -> None:
    """Runs the Hello World process.

    Args:
        proxy: the proxy for the Flywheel instance, for
            interacting with Flywheel
        context: GearToolkitContext, for applying custom
            information updates to the input file
        project: The corresponding project of this file
        input_file: InputFileWrapper to read the input file
            from, pulls the subject to create and metadata
            to add
        output_filename: Name of file to write results to
            and attach to the created subject
        local_run: Whether or not this is a local run, may
            block certain actions that cannot be done while
            iterating on a local file
    """
```

Let us walk through each step of our `main.py` logic:

1. Reading the input file. Remember that `input_file` is an `InputFileWrapper`, so the path we are actually opening to read is `input_file.filepath`:

```python
    # 1. read the name from the first line of the input file
    with open(input_file.filepath, mode='r') as fh:
        label = fh.readline().strip()
        tags = parse_string_to_list(fh.readline())
        metadata = fh.readline().strip()
        pass_qc = fh.readline().strip().upper() == 'YES'

    log.info(f"Read name {label} from input file")
    log.info(f"Read tags {tags} from input file")
    log.info(f"Read metadata {metadata} from input file")
```

2. Adding a subject. Using the label we pulled from the input file, we try to create a subject with that label. If a subject with that label already exists, we instead search for that one. In both cases, a `SubjectAdaptor` is returned and we add custom information about the input file we just evaluated, again pulled from the `InputFileWrapper`. The owner is a particular attribute that class does not expose, so we access it through the raw Flywheel entry (`input_file.file_input`).

> This is not very intuitive, but the proxy object always has a `dry_run` property, which is pulled from the same `dry_run` configuration value in the manifest if it exists (which in this case it does). We can use this to implement dry run logic.

```python
    # 2. add subject with label
    timestamp = datetime.now()
    if proxy.dry_run:
        log.info(f"DRY RUN: Would have created new subject with label {label}")
    else:
        log.info(f"Creating subject with label {label}")

        # add custom information to the subject with information about
        # the file it was created from
        subject_metadata = {
            'name': input_file.filename,
            'filepath': input_file.filepath,
            'owner': input_file.file_input['object']['origin']['id'],
            'file_id': input_file.file_id,
            'timestamp': timestamp
        }
        try:
            subject = project.add_subject(label)
            subject.update({"created_by": subject_metadata})
        except ApiException as error:
            log.warning(error)
            subject = project.find_subject(label)
            subject.update({"last_updated_by": subject_metadata})
```

3. Next we look at the project, which was already grabbed in `run.py` and passed as a `ProjectAdaptor`. In this example we grab the project's custom information, and look for the `count` and `entries` fields, and then increment/append to them.

```python
    # 3. get project custom information and increment counter by 1
    # and then also add label to array
    log.info("Grabbing project custom information")
    project_info = project.get_info()
    if project_info.get('count', None) is None:
        project_info['count'] = 0

    if project_info.get('entries', None) is None:
        project_info['entries'] = []

    log.info(f"Previous count: {project_info['count']}")
    log.info(f"Previous entries: {project_info['entries']}")

    if proxy.dry_run:
        log.info("DRY RUN: Would have added to project metadata")
    else:
        log.info("Updating project metadata")
        project_info['count'] += 1
        project_info['entries'].append(label)
        project.update_info(project_info)
```

## Gear Rules

Another nuance that we won't get into here in depth is that gear rules are often chained together using different metadata elements of the the input and output files; using the file name (by matching a certain extension/regex) or the file's tags in particular are usually the common ways to chain gear triggers. For example consider the following set of gears and their corresponding gear rules: Gear A is triggered by any CSV file, and writes out a JSON file with the `A-COMPLETED` tag at the project level. We define a Gear Rule to trigger Gear B based on this, e.g. it looks for a JSON file with the `A-COMPLETED` tag is written at the project-level. This results in a mini-pipeline of Gear A -> Gear B.

However, one must also be careful when multiple gears are involved - you may accidentally trigger an unrelated gear rule if your triggers are not specific enough, although this could also be intentionally done to create more complicated DAG-like pipelines. Either way, using both the file name _and_ custom tags will often provide enough granularity for your gear chains.