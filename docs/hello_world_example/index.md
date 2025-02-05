# Hello World Gear

Gear for the tutorial for writing of NACC-specific gear. This documentation along with the corresponding [CHANGELOG](./CHANGELOG.md) are provided as a guide for writing your own documentation.

[See the full tutorial here.](./tutorial.md)

* [Logic](#logic)
* [Inputs](#inputs)
* [Outputs](#outputs)

## Logic

This gear illustrates how to navigate through and interact with the Flywheel hierarchy as well as associated files. It runs the following steps:

1. Reads a plain text file as the input. Assumes it has exactly 4 lines with the following values:
    1. The label to say hello to and create a subject for
    2. Comma-deliminated list of tags to add to the output file
    3. Data to add under the `dummy_metadata` key in the output file's custom information
    4. `NO` to fail the QC and `YES` to pass it and attach that result to the input file's metadata (if not a local run)
2. Creates a subject with the label provided by the input file and adds
    `created_by` to the subject's custom information
    1. If a subject with that label already exists, finds the subject and instead adds `last_updated_by` to the subject's custom information
3. Grabs the project's metadata. Increments both a count and adds the subject label to a list
4. Write data to an output file that is then attached to the subject. The data being written includes information about the project and subject
5. Update tags and metadata to both the input and output files

The above can be adjusted to explore your own use cases.

## Inputs

The gear takes a single plain text file under the name `input_file` which is expected to contain exactly four lines as described above. This file will also be used to trigger the gear when set up as a gear rule.

`src/data/input_file.txt` provides an example of that, with the following contents. 

```
YourSubjectLabelHere
dummy-tag1,dummytag2
dummy-metadata-value
YES
```

It also takes an `api-key`, which is the user's Flywheel API key.

It then takes the following configuration values:

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `output_filename` | N/A | Required field. Name of the output file to write to and attach to the subject |
| `local_run` | `false` | Whether or not this is a local run |
| `target_project_id` | `""` | Target project ID, must be set to a valid Flywheel project ID if using local_run. Otherwise if set to the empty string, uses the input_file's parent project. |
| `dry_run` | `false` | Whether or not this is a dry run. If set to true, will not write any data to Flywheel but log the expected behavior. |
| `apikey_path_prefix` | `/sandbox/flywheel/gearbot` | The instance specific AWS parameter path prefix for the Gear Bot's API Key. While we are not actually using the Gear Bot in this tutorial, most gears will, so this configuration is left in for demonstration purposes. |

## Outputs

The gear _itself_ does not explicitly have an output, but instead attaches an output file to the subject created by the gear. The output file will contain the content similar to the following based on the `input_file`:

```
Hello YourSubjectLabelHere!
You were created or updated at 2025-02-05 18:21:25.812570
Your ID is 67a3a29c868e52bc602f2af5
This is the URL of the site instance: https://naccdata.flywheel.io
And this is your project's information:
Project ID: 6792d642e6aa584a8b16cf7a
Label: hello-world
Group: example-center
```

`YourSubjectLabelHere` comes from `input_file`. Similarly, the file will have the tags `dummy-tag1` and `dummytag2` attached to it, along with `{dummy_metadata: dummy-metadata-value}` stored under the file's custom information.

If the input file is a Flywheel file (e.g. not a local run), it will also apply the `hello-world-processed` tag to it and add a `hello-world-qc` result based on the `YES/NO` value provided by `input_file`.
