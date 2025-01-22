# Hello World Gear

The following tutorial outlines developing and running a basic gear in the context of NACC's Flywheel environment.

**Please do this tutorial on a separate branch and do NOT push your hello-world gears to main.**

## Set Up

Before we begin, please ensure you have access to NACC's Sandbox Flywheel instance ([nacc.flywheel.io](https://naccdata.flywheel.io/)), as well as read-write permissions to the [hello-world](TODO) project this tutorial will take place in. If you do not have access, reach out to the NACC Tech Team or [nacchelp@uw.edu](mailto:nacchelp@uw.edu).

> While not strictly necessary for this tutorial, if you want to actually upload the gear to Flywheel you will also need site-wide admin access - if you do not require site-level admin access otherwise, you can use a version of this gear already uploaded to Flywheel.

Additionally, it is advised to do gear development in the VS Code devcontainer environment, otherwise you may run into build issues (developing on MacOS with Apple Silicon in particular is known to be finicky about this). You can follow the steps in the [Getting Started](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md#getting-started) guide.

> Even if you opt out of using the VS Code devcontainer, you will still at minimum need [Pants](https://www.pantsbuild.org/) installed in your environment in order to build the gears.

While this tutorial will go through each component explicitly, it will echo a lot of the documentation already provided in the [Development Guide](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/development/index.md) which is a great general guide for gear development. Flywheel's [Gear Development Guide](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_1_developing_gears/) is also a great resource, particularly in regards to Flywheel-specific nuances.

# Hello World

In this tutorial we will write a basic gear that reads an input file containing a name, and writes an output file saying "Hello \[name\]!" along with information about the project we are running the gear in. In doing so, it will cover:

1. How a gear is created and set up in the context of NACC development
2. How to interact with Flywheel through the gear, including permissions and the Gear Bot, as well as reading/writing files
    1. This includes the file's metadata, which is heavily used in NACC pipelines
3. How to run a gear, both locally and through Flywheel
4. How to set up gear rules for automatic gear executions

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

## Configuration, Inputs, and Outputs

We will start by defining our gear's inputs and configuration values which are defined in the `manifest.json`. See [Flywheel's manifest documentation](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_5_the_manifest/) for more information. For the purposes of this tutorial, you can simply think of the manifest as where we define our **inputs** and **configuration values**, and lives under `src/docker/manifest.json`.

The cookiecutter template will have already set up a basic one for you; update the `inputs` and `config` sections of the manifest to look like the following:

```json
...
    "inputs": {
        "api-key": {
            "base": "api-key"
        },
        "input_file": {
            "description": "Hello World's input text file",
            "base": "file",
            "type": {
                "enum": [
                    "text"
                ]
            }
        }
    },
    "config": {
        "apikey_path_prefix": {
            "description": "The instance specific AWS parameter path prefix for apikey",
            "type": "string",
            "default": "/prod/flywheel/gearbot"
        },
        "output_filename": {
        	"description": "The output text file to write to",
        	"type": "string",
        	"default": "hello-world-output.txt"
        }
    },
...
```

Notice how we left in `api-key` and `apikey_path_prefix` - these are included in every gear we write.

The `api-key` corresponds to an user's Flywheel API key. `apikey_path_prefix` is similar - it tells the gear where in the AWS parameter store to grab the gear bot's API key. NACC's Flywheel instances are configured to provide the environment variables with AWS credentials necessary for the gear/gear bot to access AWS resources*, including said parameter store. See the [Gear Bot documentation](./gear-bot.md) for more information.

> \* One important nuance is that a new gear will not automatically get these AWS environment variables passed - Flywheel needs to add it to the NACC credentials condor. The easiest way is to send [Flywheel a support ticket](https://support.flywheel.io/hc/en-us/requests/new) and ask for the gear(s) "to be added to the credentials condor". This `hello-world` gear we are about to write is already on the list, so you do not have to worry about that for this tutorial.

Flywheel and its gears are file-based, so any dynamic input value should come from an input file. Configuration parameters on the other hand usually remain relatively static within a given context; for example setting `apikey_path_prefix` to either `/sandbox/flywheel/gearbot` or `/prod/flywheel/gearbot`. This is especially true if the gear is intended to be automatically triggered via [Gear Rules](https://docs.flywheel.io/user/compute/gears/user_gear_rules/), which we will talk about in more detail later in this tutorial.

Outputs are defined a little less explicitly - essentially, _any_ file saved to the `output` directory in Flywheel's hierarchy will be saved under the corresponding acquisitions if it's an utility gear, or in the separate analysis container if an analysis gear. See [The Flywheel Environment](https://docs.flywheel.io/Developer_Guides/dev_gear_building_tutorial_part_3_the_flywheel_environment/) for more information.

Within NACC, however, we tend to write files at all levels of the hierarchy - in this tutorial we will write to the project level. These must be _explicitly_ uploaded within your gear, which is why we have set the `output_filename` as a configuration value as opposed to an actual file. Either way, we usually "parameterize" the output file by specifying the output filename, to avoid having it hardcoded within the gear itself.

## Developing the Gear

### run.py

Next we will define the `run.py`, which you can think of as the **entrypoint** to the gear (we will gloss over the specifics, but in a nutshell the Pants environment creates a binary executable `.pex` with this entrypoint which the Docker image/gear ends up calling). 

Navigate to `src/python/run.py` where a template has been set up. You'll notice there is an executable `main` which sets up the GearEngine. This GearEngine has two jobs: to instantiate itself with the parameter store (defined using the AWS credential environment variables mentioned earlier), and to run the Visitor class defined in the same file. Your job is to define the Visitor and its `run` method, which comes in two parts:

1. Define the `create` method. This works in conjunction with the `__init__` method and is generally where you pull configuration values from. This is done through the `GearToolkitContext`, which you can learn more about [here](https://flywheel-io.gitlab.io/public/gear-toolkit/flywheel_gear_toolkit/context/). This context is primarily how we handle reading in inputs/configuration values as well as writing output tags and metadata, but is generally useful for other things as well (you can directly access [Flywheel's SDK client](https://flywheel-io.gitlab.io/product/backend/sdk/tags/19.5.0/python/index.html) through this context).

```python
class HelloWorldVisitor(GearExecutionEnvironment):
    """Visitor for the Hello World gear."""

    def __init__(self,
                 file_input: InputFileWrapper,
                 output_filename: str):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__output_filename = output_filename

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'HelloWorld':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        output_filename = context.config.get('output_filename', None)
        if not output_filename:
            raise GearExecutionError("Output filename not defined")

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        return HelloWorldVisitor(
            client=client,
            file_input=file_input,
            output_filename=output_filename)
```

* `client` is how we interact with the Flywheel SDK as the GearBot user. It uses the `context` to pull `apikey_path_prefix` from the configuration values in order to find the Gear Bot's API key in the `parameter_store`. You can also use a `ContextClient` which is just a normal client, but typically within NACC you will need Gear Bot permissions anyways
    * Behind the scenes, this client is a wrapper around the `GearToolkitContext`'s client
* `context.config` allows you to access the configuration values like a normal Python dict; we pull out `output_filename` and ensure it's set, if not throw a GearExecutionError
* Grabbing file inputs is done through the `InputFileWrapper`, which takes the specified file from the context and wraps it with useful methods and properties

The above are used to create a `HelloWorldVisitor`, which implements the abstract `GearExecutionEnvironment`. It uses the client to create a `FlywheelProxy` object, which will be our primary means of dealing with anything related to Flywheel.

2. Now let's look at the visitor's `run` method:

```python
from hello_world_app.main import run

    def run(self, context: GearToolkitContext) -> None:
        try:
            file_id = self.__file_input.file_id
            file = self.proxy.get_file(file_id)
            project = file.parents.project
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        project = ProjectAdaptor(project=project, proxy=self.proxy)

        success = run(proxy=self.proxy,
                      input_file=input_file)

        context.metadata.add_file_tags(file=self.__file_input.file_input,
                                       tags='finished-processing')
        context.metadata.update_file_metadata(file=self.output_filename,
                                              dummy_metadata='value1')
        context.metadata.add_qc_result(file=self.output_filename,
                                       name='hello-world-qc',
                                       state='PASS' if success else 'FAIL',
                                       data={'dummydata': 'value2'})

```

The `proxy` is our primary means of interacting with Flywheel, in particular looking up and grabbing data; it differs from `context` in that `context` is more about this specific execution (e.g. inputs and outputs), but `proxy` is more like using the Flywheel SDK for general use.

The try block is locating the actual file and project contexts from Flywheel using the file's ID, and throwing a `GearExecutionError` if the file does not exist. We then wrap project around a `ProjectAdaptor`, which wraps the raw project context into a wrapper with useful properties and methods.

We then execute the main `run`, which was imported from `hello_world_app.main`. We will fill this out in the next section, but for now we assume it returns whether or not the process succeeded.

Finally, we run some post-processing, namely adding tags to our original file input, as well as updating its file metadata. It also adds QC results, which is a distinct type of metadata.

### main.py

## Gear Rules


Another nuance that we won't get into here in depth is that gear rules are often chained together using different metadata elements of the the input and output files; using the file name (by matching a certain extension/regex) or the file's tags in particular are usually the common ways to chain gear triggers. For example consider the following set of gears and their corresponding gear rules: Gear A is triggered by any CSV file, and writes out a JSON file with the `A-COMPLETED` tag at the project level. We define a Gear Rule to trigger Gear B based on this, e.g. it looks for a JSON file with the `A-COMPLETED` tag is written at the project-level. This results in a mini-pipeline of Gear A -> Gear B.

However, one must also be careful when multiple gears are involved - you may accidentally trigger an unrelated gear rule if your triggers are not specific enough, although this could also be intentionally done to create more complicated DAG-like pipelines. Either way, using both the file name _and_ custom tags will often provide enough granularity for your gear chains.